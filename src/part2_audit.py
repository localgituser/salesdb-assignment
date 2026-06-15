"""
Part 2 — Agentic Coverage & Quality Audit (data-engineer role)

Reads gap_candidates.json + queries us_companies_clean.parquet, then calls:
  1. Haiku  — commercial relevance + enrichment approach for actionable sectors
              (NES-dominated SOURCING_LIMIT sectors pre-filtered deterministically)
  2. Sonnet — top-5 narrative synthesis across industry + size dimensions
  3. Haiku  — record-level semantic quality audit (n=100 per gap, stratified by
              state tier × size band; detects website mismatches, industry mislabels,
              platform URL misses, and data anomalies that rules can't catch)

If part2_audit_raw.json already exists with haiku_ranking + sonnet_synthesis,
steps 1 and 2 are skipped (idempotent) and only the record audit is re-run.

Writes:
  data/processed/part2_audit_raw.json    — raw LLM outputs + all pre-computed summaries
  data/processed/observability.jsonl     — per-call trace entries
  data/processed/cost_tracking.json      — running total update

Does NOT write gap_findings.md — that is the verifier's job after spot-checking.
"""

import json
import sys
import time
import logging
from collections import defaultdict
from pathlib import Path

import duckdb
import anthropic

from src.shared.config import CONFIG
from src.shared.observability import ObservabilityLogger

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PART = "part_2"
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_COST_PER_M_IN = 0.80
HAIKU_COST_PER_M_OUT = 4.00
SONNET_COST_PER_M_IN = 3.00
SONNET_COST_PER_M_OUT = 15.00

# SOURCING_LIMIT pre-filter — two conditions must both hold:
#   1. NES non-employers make up >70% of the comparator (NES_share > NES_THRESHOLD)
#   2. Coverage vs. SUSB employer firms alone is adequate (>= SUSB_ADEQUATE_THRESHOLD)
# Condition 2 prevents dropping sectors like Construction or Retail where NES inflates
# the denominator but a real employer-firm sourcing gap still exists underneath.
NES_THRESHOLD = 0.70
SUSB_ADEQUATE_THRESHOLD = 0.35

PART2_BUDGET = CONFIG.budget.per_part_usd.get("part_2", 3.0)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"
CLEAN_PARQUET = PROCESSED_DIR / "us_companies_clean.parquet"
GAP_CANDIDATES_PATH = PROCESSED_DIR / "gap_candidates.json"
AUDIT_RAW_PATH = PROCESSED_DIR / "part2_audit_raw.json"


def load_gap_candidates() -> dict:
    with open(GAP_CANDIDATES_PATH) as f:
        return json.load(f)


def build_sector_summary(all_cells: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Aggregate cell-level gap data to sector level.
    Returns (actionable_sectors, sourcing_limit_sectors).
    Sectors where NES > NES_SOURCING_LIMIT_THRESHOLD are classified as SOURCING_LIMIT
    deterministically — no LLM needed for these.
    """
    sectors: dict = defaultdict(lambda: {
        "HIGH_GAP": 0, "MODERATE_GAP": 0, "ADEQUATE": 0,
        "ratios": [], "naics_code": "",
        "total_our_records": 0, "total_comparator": 0,
        "total_susb": 0, "total_nes": 0,
    })

    for cell in all_cells:
        s = cell["naics_desc"]
        t = cell.get("tier", "ADEQUATE")
        sectors[s][t] = sectors[s].get(t, 0) + 1
        sectors[s]["ratios"].append(cell["coverage_ratio"])
        sectors[s]["naics_code"] = cell["naics_code"]
        sectors[s]["total_our_records"] += cell["our_records"]
        sectors[s]["total_comparator"] += cell["comparator_records"]
        sectors[s]["total_susb"] += cell.get("susb_firms", 0)
        sectors[s]["total_nes"] += cell.get("nes_nonemployers", 0)

    actionable, sourcing_limits = [], []
    for naics_desc, st in sectors.items():
        ratios = sorted(st["ratios"])
        median_ratio = ratios[len(ratios) // 2]
        overall_ratio = (
            st["total_our_records"] / st["total_comparator"]
            if st["total_comparator"] > 0 else 0.0
        )
        nes_share = (
            st["total_nes"] / st["total_comparator"]
            if st["total_comparator"] > 0 else 0.0
        )
        entry = {
            "naics_code": st["naics_code"],
            "naics_desc": naics_desc,
            "states_analyzed": len(st["ratios"]),
            "high_gap_states": st.get("HIGH_GAP", 0),
            "moderate_gap_states": st.get("MODERATE_GAP", 0),
            "adequate_states": st.get("ADEQUATE", 0),
            "median_coverage_pct": round(median_ratio * 100, 2),
            "overall_coverage_pct": round(overall_ratio * 100, 2),
            "nes_share_of_comparator_pct": round(nes_share * 100, 1),
            "our_records": st["total_our_records"],
            "comparator_total": st["total_comparator"],
        }
        # Compute coverage vs. SUSB employer firms only (strip NES from denominator)
        susb_only = st["total_susb"]
        coverage_vs_susb = (
            st["total_our_records"] / susb_only if susb_only > 0 else 1.0
        )
        entry["coverage_vs_susb_only_pct"] = round(coverage_vs_susb * 100, 1)

        is_nes_heavy = nes_share >= NES_THRESHOLD
        is_susb_adequate = coverage_vs_susb >= SUSB_ADEQUATE_THRESHOLD

        if is_nes_heavy and is_susb_adequate:
            entry["pre_classified"] = "SOURCING_LIMIT"
            entry["pre_classified_reason"] = (
                f"NES non-employers are {entry['nes_share_of_comparator_pct']}% of comparator "
                f"and coverage vs. SUSB employer firms alone is {entry['coverage_vs_susb_only_pct']}% "
                f"(>= {SUSB_ADEQUATE_THRESHOLD*100:.0f}% adequate threshold). "
                "Gap is driven by sole-proprietor absence, not employer-firm under-coverage."
            )
            sourcing_limits.append(entry)
        else:
            if is_nes_heavy:
                entry["note"] = (
                    f"NES-heavy ({entry['nes_share_of_comparator_pct']}% NES) but "
                    f"coverage vs. SUSB employer firms is only {entry['coverage_vs_susb_only_pct']}% "
                    "— real employer-firm gap underneath the NES inflation."
                )
            actionable.append(entry)

    actionable.sort(key=lambda x: x["overall_coverage_pct"])
    return actionable, sourcing_limits


def build_size_quality_summary(con: duckdb.DuckDBPyConnection) -> dict:
    """
    Query us_companies_clean.parquet for size-dimension quality metrics.
    Returns structured summary for the Haiku prompt.
    """
    segment_sql = f"""
        SELECT
            CASE
                WHEN size IN ('501-1K','1K-5K','5K-10K','10K+') THEN 'enterprise_500plus'
                WHEN size IN ('51-200','201-500')                THEN 'mid_market_51_500'
                WHEN size = '11-50'                             THEN 'smb_11_50'
                WHEN size = '1-10'                              THEN 'micro_1_10'
                ELSE 'size_unknown'
            END as segment,
            COUNT(*)                                                              as records,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2)                  as pct_of_total,
            ROUND(AVG(CASE WHEN website IS NOT NULL THEN 1.0 ELSE 0 END)*100, 1) as website_fill_pct,
            ROUND(AVG(CASE WHEN industry IS NOT NULL THEN 1.0 ELSE 0 END)*100, 1) as industry_fill_pct
        FROM read_parquet('{CLEAN_PARQUET}')
        WHERE state IS NOT NULL
        GROUP BY 1
        ORDER BY records DESC
    """
    seg_rows = con.execute(segment_sql).df().to_dict(orient="records")

    # Worst industry × size combos for website fill (high-record cells only, non-government)
    cross_sql = f"""
        SELECT
            size              as size_band,
            industry          as industry_label,
            COUNT(*)          as records,
            ROUND(AVG(CASE WHEN website IS NOT NULL THEN 1.0 ELSE 0 END)*100, 1) as website_fill_pct
        FROM read_parquet('{CLEAN_PARQUET}')
        WHERE state IS NOT NULL
          AND size IS NOT NULL
          AND industry IS NOT NULL
          AND industry NOT IN ('higher education','government administration',
                               'primary and secondary education','law enforcement',
                               'education administration programs')
        GROUP BY size, industry
        HAVING COUNT(*) > 2000
        ORDER BY website_fill_pct ASC
        LIMIT 8
    """
    cross_rows = con.execute(cross_sql).df().to_dict(orient="records")

    return {
        "segments": seg_rows,
        "worst_website_fill_by_size_x_industry": cross_rows,
        "note": (
            "Enterprise (500+) is 1.65% of records — sourcing gap vs. B2B importance, "
            "not a fill-rate gap (website fill 80.9%). "
            "size_unknown segment (4.5% of records) has 46.8% industry fill — "
            "highest enrichment density of any segment."
        ),
    }


def compute_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    if "haiku" in model:
        return (input_tokens * HAIKU_COST_PER_M_IN + output_tokens * HAIKU_COST_PER_M_OUT) / 1_000_000
    return (input_tokens * SONNET_COST_PER_M_IN + output_tokens * SONNET_COST_PER_M_OUT) / 1_000_000


def render_prompt(template_path: Path, **kwargs) -> str:
    text = template_path.read_text()
    for key, value in kwargs.items():
        placeholder = "{{" + key.upper() + "}}"
        text = text.replace(placeholder, value)
    return text


def call_llm(
    client: anthropic.Anthropic,
    obs: ObservabilityLogger,
    model: str,
    prompt: str,
    prompt_version: str,
    metadata: dict,
) -> tuple[str, dict]:
    """Call LLM, log to observability, return (text_response, usage_dict)."""
    budget_used = obs.get_phase_cost(PART)
    if budget_used >= PART2_BUDGET:
        logger.error(f"Part 2 budget exhausted (${budget_used:.4f} >= ${PART2_BUDGET}). Aborting.")
        sys.exit(1)

    t0 = time.time()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = int((time.time() - t0) * 1000)

    text = response.content[0].text.strip()
    # Strip markdown code fences if the model wrapped its JSON output
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0].strip()
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    cost = compute_cost(usage["input_tokens"], usage["output_tokens"], model)

    try:
        json.loads(text)
        outcome = "success"
    except json.JSONDecodeError:
        outcome = "invalid_json"
        logger.warning(f"LLM returned non-JSON for {prompt_version}")

    obs.log_call(
        phase=PART,
        model=model,
        tokens=usage["input_tokens"] + usage["output_tokens"],
        cost=cost,
        prompt_version=prompt_version,
        outcome=outcome,
        metadata={**metadata, "latency_ms": latency_ms, **usage},
    )
    logger.info(
        f"{model} {prompt_version}: {usage['input_tokens']}in/{usage['output_tokens']}out "
        f"${cost:.4f} {latency_ms}ms → {outcome}"
    )
    return text, usage


def build_top5_sector_detail(gap_candidates: list[dict], top5_codes: list[str]) -> list[dict]:
    """Collect all gap candidates for the top 5 NAICS codes for Sonnet synthesis."""
    code_set = set(top5_codes)
    by_code: dict = defaultdict(list)
    for c in gap_candidates:
        if c["naics_code"] in code_set:
            by_code[c["naics_code"]].append({
                "state": c["state"],
                "state_tier": c["state_tier"],
                "our_records": c["our_records"],
                "coverage_pct": c["coverage_pct"],
                "tier": c["tier"],
                "caveats": c.get("caveats", []),
            })
    result = []
    for code in top5_codes:
        cells = by_code.get(code, [])
        result.append({
            "naics_code": code,
            "cell_count": len(cells),
            "cells": cells,
        })
    return result


INDUSTRY_MAPPING_PATH = PROCESSED_DIR / "industry_naics_mapping.json"
RECORD_AUDIT_N = CONFIG.eval.record_audit_n_per_gap
RECORD_AUDIT_BATCH = 10
EXCLUDED_TERRITORIES = set(CONFIG.market.excluded_territories)


def load_naics_labels() -> dict:
    """Load industry_naics_mapping.json and invert to {naics_code: [labels]}."""
    if not INDUSTRY_MAPPING_PATH.exists():
        return {}
    with open(INDUSTRY_MAPPING_PATH) as f:
        mapping = json.load(f)
    result: dict = defaultdict(list)
    for label, code in mapping.items():
        result[str(code)].append(label)
    return dict(result)


def get_worst_covered_states(
    all_cells: list[dict], naics_code: str, state_tier: str, n: int
) -> list[str]:
    """Return up to n states with lowest coverage_pct for this naics_code + state_tier."""
    cells = [
        c for c in all_cells
        if str(c.get("naics_code", "")) == naics_code
        and c.get("state_tier") == state_tier
        and c.get("state") not in EXCLUDED_TERRITORIES
    ]
    cells.sort(key=lambda x: x.get("coverage_pct", 100.0))
    return [c["state"] for c in cells[:n]]


def _labels_sql(labels: list[str]) -> str:
    escaped = [l.replace("'", "''") for l in labels]
    return ", ".join(f"'{l}'" for l in escaped)


def build_record_quality_sample(
    con: duckdb.DuckDBPyConnection,
    all_cells: list[dict],
    naics_labels: dict,
    top5_gaps: list[dict],
    n_per_gap: int = RECORD_AUDIT_N,
) -> dict:
    """
    Draw a stratified sample (sector × state tier × size band) for each top-5 gap.
    Stratification: 10 worst-covered Tier A states + 5 worst-covered Tier B states,
    natural size distribution within each cell, enterprise minimum n=2 per gap.
    Returns {gap_key: {"records": [...], "naics_code": ..., "naics_desc": ...}}.
    """
    PARQUET = str(CLEAN_PARQUET)
    samples: dict = {}
    food_labels = naics_labels.get("72", [])  # Accommodation & Food Services

    for gap in top5_gaps:
        naics_code = gap.get("naics_code")
        rank = gap.get("rank", 0)
        naics_desc = gap.get("naics_desc", "")
        gap_key = f"rank_{rank}_{naics_code or 'size_dim'}"

        if naics_code is None:
            # Gap 4: enterprise size-dimension — any sector, size 500+
            sql = f"""
                SELECT handle, name, website, industry, size, city, state
                FROM read_parquet('{PARQUET}')
                WHERE state IS NOT NULL
                  AND size IN ('501-1K','1K-5K','5K-10K','10K+')
                  AND NOT (website IS NULL AND industry IS NULL)
                ORDER BY hash(handle || 'record_audit_v1_seed')
                LIMIT {n_per_gap}
            """
        elif "micro" in naics_desc.lower():
            # Gap 5: micro transport + restaurant cross-dimension
            transport = naics_labels.get(str(naics_code), [])
            all_labels = list(set(transport + food_labels))
            worst_states = (
                get_worst_covered_states(all_cells, str(naics_code), "A", 8)
                + get_worst_covered_states(all_cells, str(naics_code), "B", 4)
            )
            state_list = _labels_sql(worst_states) if worst_states else "''"
            lsql = _labels_sql(all_labels) if all_labels else "''"
            sql = f"""
                SELECT handle, name, website, industry, size, city, state
                FROM read_parquet('{PARQUET}')
                WHERE state IN ({state_list})
                  AND industry IN ({lsql})
                  AND size = '1-10'
                  AND NOT (website IS NULL AND industry IS NULL)
                ORDER BY hash(handle || 'record_audit_v1_seed')
                LIMIT {n_per_gap}
            """
        else:
            # Standard sector gap — stratified by worst-covered states
            labels = naics_labels.get(str(naics_code), [])
            industry_filter = f"industry IN ({_labels_sql(labels)})" if labels else "industry IS NULL"
            worst_a = get_worst_covered_states(all_cells, str(naics_code), "A", 10)
            worst_b = get_worst_covered_states(all_cells, str(naics_code), "B", 5)
            all_states = worst_a + worst_b
            state_list = _labels_sql(all_states) if all_states else "''"

            # Draw main sample from worst-covered states
            main_sql = f"""
                SELECT handle, name, website, industry, size, city, state
                FROM read_parquet('{PARQUET}')
                WHERE state IN ({state_list})
                  AND {industry_filter}
                  AND NOT (website IS NULL AND industry IS NULL)
                ORDER BY hash(handle || 'record_audit_v1_seed')
                LIMIT {n_per_gap - 2}
            """
            # Ensure at least 2 enterprise records per gap (oversampled — enterprise is 1.65% of dataset)
            enterprise_sql = f"""
                SELECT handle, name, website, industry, size, city, state
                FROM read_parquet('{PARQUET}')
                WHERE {industry_filter}
                  AND size IN ('501-1K','1K-5K','5K-10K','10K+')
                  AND NOT (website IS NULL AND industry IS NULL)
                ORDER BY hash(handle || 'record_audit_v1_seed')
                LIMIT 2
            """
            main_df = con.execute(main_sql).df()
            ent_df = con.execute(enterprise_sql).df()
            # Combine, dedup by handle
            import pandas as pd
            combined = pd.concat([main_df, ent_df]).drop_duplicates(subset=["handle"])
            records = combined.head(n_per_gap).to_dict(orient="records")
            samples[gap_key] = {
                "records": [{k: str(v) if v is not None else None for k, v in r.items()} for r in records],
                "naics_code": naics_code,
                "naics_desc": naics_desc,
                "states_sampled": list(set(r["state"] for r in records if r.get("state"))),
            }
            logger.info(f"[record_sample] {gap_key}: {len(records)} records from {len(samples[gap_key]['states_sampled'])} states")
            continue

        df = con.execute(sql).df()
        records = df.head(n_per_gap).to_dict(orient="records")
        samples[gap_key] = {
            "records": [{k: str(v) if v is not None else None for k, v in r.items()} for r in records],
            "naics_code": naics_code,
            "naics_desc": naics_desc,
            "states_sampled": list(set(r["state"] for r in records if r.get("state"))),
        }
        logger.info(f"[record_sample] {gap_key}: {len(records)} records from {len(samples[gap_key]['states_sampled'])} states")

    return samples


def run_record_quality_audit(
    client: anthropic.Anthropic,
    obs: ObservabilityLogger,
    samples: dict,
) -> dict:
    """
    Run Haiku over each gap sample in batches of RECORD_AUDIT_BATCH records.
    Returns aggregated findings with per-gap issue counts.
    """
    prompt_template = (PROMPTS_DIR / "part2_record_audit_v1.txt").read_text()
    by_gap: dict = {}
    issue_counts_by_gap: dict = {}
    total_records = sum(len(v["records"]) for v in samples.values())
    logger.info(f"Record quality audit: {total_records} records across {len(samples)} gaps")

    for gap_key, gap_data in samples.items():
        records = gap_data["records"]
        gap_findings = []
        issue_counts: dict = defaultdict(int)

        for i in range(0, len(records), RECORD_AUDIT_BATCH):
            batch = records[i:i + RECORD_AUDIT_BATCH]
            prompt = prompt_template.replace("{{RECORDS_JSON}}", json.dumps(batch, indent=2))
            raw, _ = call_llm(
                client, obs, HAIKU_MODEL, prompt,
                prompt_version="part2_record_audit_v1",
                metadata={"gap_key": gap_key, "batch_start": i, "batch_n": len(batch)},
            )
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"record_audit_v1 batch {i} for {gap_key}: non-JSON — skipping batch")
                continue

            for finding in result.get("batch_findings", []):
                gap_findings.append(finding)
                for issue in finding.get("issues", []):
                    if issue != "clean":
                        issue_counts[issue] += 1

        by_gap[gap_key] = {
            "naics_code": gap_data["naics_code"],
            "naics_desc": gap_data["naics_desc"],
            "states_sampled": gap_data["states_sampled"],
            "records_sampled": len(records),
            "issues_found": sum(issue_counts.values()),
            "issue_counts": dict(issue_counts),
            "findings": gap_findings,
        }
        issue_counts_by_gap[gap_key] = dict(issue_counts)
        logger.info(f"  {gap_key}: {len(records)} records, {sum(issue_counts.values())} issues found")

    return {
        "by_gap": by_gap,
        "issue_counts_by_gap": issue_counts_by_gap,
        "total_records_audited": total_records,
        "n_per_gap": RECORD_AUDIT_N,
    }


def main():
    logger.info("Phase 2 audit starting")
    obs = ObservabilityLogger()
    client = anthropic.Anthropic()
    con = duckdb.connect()

    data = load_gap_candidates()
    all_cells = data.get("all_cells", [])
    gap_candidates = data.get("gap_candidates", [])

    if not all_cells:
        logger.error("all_cells missing from gap_candidates.json — cannot build sector summary")
        sys.exit(1)

    # --- Skip sector ranking/synthesis if already run (idempotent) ---
    if AUDIT_RAW_PATH.exists():
        existing = json.loads(AUDIT_RAW_PATH.read_text())
        if existing.get("haiku_ranking") and existing.get("sonnet_synthesis"):
            logger.info(
                f"Found existing {AUDIT_RAW_PATH.name} with sector ranking + synthesis — "
                "skipping LLM calls 1 & 2, proceeding directly to record quality audit"
            )
            haiku_output = existing["haiku_ranking"]
            sonnet_output = existing["sonnet_synthesis"]
            top5_codes = haiku_output.get("top_5_for_synthesis", [])
            top5 = sonnet_output.get("top_5_gaps", [])
            raw_output = existing
            actionable_sectors = existing.get("actionable_sectors", [])
            sourcing_limit_sectors = existing.get("sourcing_limit_sectors", [])
            size_quality = existing.get("size_quality_summary", {})
        else:
            existing = {}
    else:
        existing = {}

    if not existing:
        actionable_sectors, sourcing_limit_sectors = build_sector_summary(all_cells)
        logger.info(
            f"Sector pre-filter: {len(actionable_sectors)} actionable, "
            f"{len(sourcing_limit_sectors)} SOURCING_LIMIT (NES >{NES_THRESHOLD*100:.0f}% + SUSB adequate, skipped)"
        )
        for s in sourcing_limit_sectors:
            logger.info(f"  SOURCING_LIMIT (pre-classified): {s['naics_desc']} "
                        f"({s['nes_share_of_comparator_pct']}% NES)")

        size_quality = build_size_quality_summary(con)
        logger.info("Built size quality summary from parquet")

        # --- Call 1: Haiku — commercial relevance + enrichment approach ---
        haiku_prompt = render_prompt(
            PROMPTS_DIR / "part2_audit_v1.txt",
            actionable_sectors_json=json.dumps(actionable_sectors, indent=2),
            size_quality_json=json.dumps(size_quality, indent=2),
            sourcing_limit_sectors_json=json.dumps(
                [{"naics_desc": s["naics_desc"], "naics_code": s["naics_code"],
                  "nes_share_pct": s["nes_share_of_comparator_pct"],
                  "overall_coverage_pct": s["overall_coverage_pct"]}
                 for s in sourcing_limit_sectors],
                indent=2,
            ),
        )
        haiku_raw, _ = call_llm(
            client, obs, HAIKU_MODEL, haiku_prompt,
            prompt_version="part2_audit_v1",
            metadata={"actionable_sector_count": len(actionable_sectors),
                      "sourcing_limit_count": len(sourcing_limit_sectors)},
        )
        try:
            haiku_output = json.loads(haiku_raw)
        except json.JSONDecodeError:
            logger.error("Haiku returned invalid JSON. Aborting.")
            sys.exit(1)

        top5_codes = haiku_output.get("top_5_for_synthesis", [])
        logger.info(f"Haiku top 5 for synthesis: {top5_codes}")

        # --- Call 2: Sonnet — top-5 narrative synthesis ---
        top5_detail = build_top5_sector_detail(gap_candidates, top5_codes)
        sonnet_prompt = render_prompt(
            PROMPTS_DIR / "part2_audit_synthesis_v1.txt",
            haiku_rankings_json=json.dumps(haiku_output, indent=2),
            top5_sector_detail_json=json.dumps(top5_detail, indent=2),
            size_quality_json=json.dumps(size_quality, indent=2),
        )
        sonnet_raw, _ = call_llm(
            client, obs, SONNET_MODEL, sonnet_prompt,
            prompt_version="part2_audit_synthesis_v1",
            metadata={"top5_codes": top5_codes},
        )
        try:
            sonnet_output = json.loads(sonnet_raw)
        except json.JSONDecodeError:
            logger.error("Sonnet returned invalid JSON. Aborting.")
            sys.exit(1)

        top5 = sonnet_output.get("top_5_gaps", [])
        raw_output = {
            "phase": PART,
            "actionable_sectors": actionable_sectors,
            "sourcing_limit_sectors": sourcing_limit_sectors,
            "size_quality_summary": size_quality,
            "haiku_ranking": haiku_output,
            "sonnet_synthesis": sonnet_output,
        }

    # --- Call 3: Haiku — record-level semantic quality audit ---
    naics_labels = load_naics_labels()
    record_samples = build_record_quality_sample(con, all_cells, naics_labels, top5)
    record_quality = run_record_quality_audit(client, obs, record_samples)

    raw_output["record_quality_findings"] = record_quality
    raw_output["total_part2_cost"] = obs.get_phase_cost(PART)

    AUDIT_RAW_PATH.write_text(json.dumps(raw_output, indent=2))
    logger.info(f"Wrote {AUDIT_RAW_PATH}")
    logger.info(f"Part 2 total cost: ${obs.get_phase_cost(PART):.4f}")
    logger.info("Part 2 audit complete. Run part2_verify.py next (verifier role).")


if __name__ == "__main__":
    main()
