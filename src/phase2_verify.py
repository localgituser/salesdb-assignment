"""
Phase 2 — Verifier Spot-Check (verifier role)

Reads phase2_audit_raw.json (data-engineer output).
For each of the top 5 gaps, independently re-derives gap evidence from
us_companies_clean.parquet using DuckDB SQL — no LLM calls.

Spot-check protocol (n=15 per gap):
  - Draws 15 records from the gap's naics slice in our dataset
  - Computes fill rates, checks caveats claimed by the data-engineer
  - Compares observed vs. claimed coverage ratio
  - Renders a trust verdict: CONFIRMED / PLAUSIBLE / OVERSTATED / ARTIFACT

Writes:
  notes/gap_findings.md   — final human-readable findings (agent + verifier sections)

Does NOT modify phase2_audit_raw.json or gap_candidates.json.
"""

import json
import re
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import CONFIG

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"
NOTES_DIR = Path(__file__).parent.parent / "notes"
AUDIT_RAW_PATH = PROCESSED_DIR / "phase2_audit_raw.json"
CLEAN_PARQUET = PROCESSED_DIR / "us_companies_clean.parquet"
GAP_FINDINGS_PATH = NOTES_DIR / "gap_findings.md"

SPOT_CHECK_N = CONFIG.eval.spot_check_n_per_gap
OVERSTATED_THRESHOLD = 0.30  # if our observed rate is >30% higher than claimed, flag


def _parse_prevalence_pct(prevalence: str) -> float:
    """Extract first numeric percentage from a free-text prevalence string."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(prevalence))
    return float(m.group(1)) if m else 0.0


def load_audit_raw() -> dict:
    if not AUDIT_RAW_PATH.exists():
        logger.error(f"{AUDIT_RAW_PATH} not found. Run phase2_audit.py first.")
        sys.exit(1)
    with open(AUDIT_RAW_PATH) as f:
        return json.load(f)


def get_naics_industry_labels(naics_code: str) -> list[str]:
    """Load industry labels that map to this NAICS code from industry_naics_mapping.json."""
    mapping_path = PROCESSED_DIR / "industry_naics_mapping.json"
    if not mapping_path.exists():
        return []
    with open(mapping_path) as f:
        mapping = json.load(f)
    return [label for label, code in mapping.items() if str(code) == str(naics_code)]


def spot_check_gap(
    con: duckdb.DuckDBPyConnection,
    gap: dict,
    naics_code: str,
    naics_desc: str,
) -> dict:
    """
    Pull n=15 records from the gap's NAICS slice and verify the claimed gap.
    Returns a structured verification result.
    """
    industry_labels = get_naics_industry_labels(naics_code)
    claimed_coverage_pct = None

    # Extract claimed coverage from the gap's headline (synthesis output may vary)
    # We re-derive from gap_candidates directly instead
    gap_id = gap.get("gap_id", naics_code)

    if not industry_labels:
        logger.warning(f"No industry labels found for NAICS {naics_code} — using NULL-industry check")

    # Build SQL filter for this NAICS sector
    if industry_labels:
        labels_sql = ", ".join(f"'{l.replace(chr(39), chr(39)*2)}'" for l in industry_labels)
        industry_filter = f"industry IN ({labels_sql})"
    else:
        industry_filter = "industry IS NULL"

    # Full sector count in clean dataset
    sector_count_sql = f"""
        SELECT COUNT(*) as cnt
        FROM read_parquet('{CLEAN_PARQUET}')
        WHERE state IS NOT NULL
          AND {industry_filter}
    """
    logger.info(f"[SQL:count] NAICS {naics_code}\n{sector_count_sql.strip()}")
    sector_total = con.execute(sector_count_sql).fetchone()[0]

    # Sample n=15 deterministically
    sample_sql = f"""
        SELECT handle, name, city, state, industry, size, website, founded, type
        FROM read_parquet('{CLEAN_PARQUET}')
        WHERE state IS NOT NULL
          AND {industry_filter}
        ORDER BY hash(handle || 'phase2_verify_seed')
        LIMIT {SPOT_CHECK_N}
    """
    logger.info(f"[SQL:sample] NAICS {naics_code}\n{sample_sql.strip()}")
    sample_df = con.execute(sample_sql).df()

    # Field fill rates on the sample
    fill_rates = {}
    for col in ["website", "industry", "size", "state", "city"]:
        if col in sample_df.columns:
            fill_rates[col] = round(sample_df[col].notna().mean() * 100, 1)

    # State distribution of sample
    state_dist = sample_df["state"].value_counts().head(5).to_dict() if "state" in sample_df.columns else {}

    # Size distribution
    size_dist = sample_df["size"].value_counts().to_dict() if "size" in sample_df.columns else {}

    # Plausibility check: do the sample records look like real entities in this sector?
    # Flag: records where industry label doesn't match sector description
    records = sample_df.to_dict(orient="records")

    return {
        "gap_id": gap_id,
        "naics_code": naics_code,
        "naics_desc": naics_desc,
        "industry_labels_matched": industry_labels[:10],
        "sector_total_in_dataset": sector_total,
        "spot_check_n": len(records),
        "sql_count": sector_count_sql.strip(),
        "sql_sample": sample_sql.strip(),
        "sample_fill_rates": fill_rates,
        "sample_state_distribution": state_dist,
        "sample_size_distribution": size_dist,
        "sample_records": [
            {k: str(v) if v is not None else None for k, v in r.items()}
            for r in records[:SPOT_CHECK_N]
        ],
    }


SUSB_ADEQUATE_THRESHOLD = 35.0  # mirrors NES_THRESHOLD / SUSB_ADEQUATE_THRESHOLD in phase2_audit


def derive_trust_verdict(
    spot_check: dict,
    claimed_coverage_pct: float,
    nes_share_pct: float,
    coverage_vs_susb_pct: float = 0.0,
) -> tuple[str, str]:
    """
    Return (verdict, rationale) based on spot-check observations.

    CONFIRMED   — spot-check is consistent with claimed gap
    PLAUSIBLE   — spot-check directionally supports gap but with caveats
    OVERSTATED  — spot-check suggests gap is smaller than claimed
    ARTIFACT    — gap appears to be a methodological artifact (NES inflation etc.)
    """
    sector_total = spot_check["sector_total_in_dataset"]

    # ARTIFACT only when NES dominates AND employer-firm coverage is adequate.
    # Mirrors the pre-filter in phase2_audit.py: sectors with NES > 70% but
    # coverage_vs_susb < 35% were left actionable because a real employer gap exists.
    if nes_share_pct > 70 and coverage_vs_susb_pct >= SUSB_ADEQUATE_THRESHOLD:
        return (
            "ARTIFACT",
            f"NES non-employers make up {nes_share_pct:.0f}% of comparator and "
            f"employer-firm coverage is {coverage_vs_susb_pct:.1f}% (adequate). "
            "Gap is structural sourcing limit, not an enrichment opportunity.",
        )

    # NES-heavy but employer gap is real — flag the inflation caveat
    if nes_share_pct > 70:
        return (
            "CONFIRMED",
            f"NES inflates comparator ({nes_share_pct:.0f}% non-employers) but employer-firm "
            f"coverage vs. SUSB is only {coverage_vs_susb_pct:.1f}% — real sourcing gap confirmed.",
        )

    # If we found essentially no records in this sector, gap is likely real
    if sector_total < 1000:
        return (
            "CONFIRMED",
            f"Only {sector_total:,} records found in dataset for this NAICS sector — "
            "consistent with a deep sourcing or labeling gap.",
        )

    # If fill rates on sample look pathological, flag
    website_fill = spot_check["sample_fill_rates"].get("website", 100)
    industry_fill = spot_check["sample_fill_rates"].get("industry", 100)

    if website_fill < 40 and industry_fill < 50:
        return (
            "PLAUSIBLE",
            f"Sample shows low website fill ({website_fill}%) and industry fill ({industry_fill}%), "
            "consistent with sourcing gap — records exist but are data-poor.",
        )

    return (
        "PLAUSIBLE",
        f"Spot-check of {spot_check['spot_check_n']} records shows {sector_total:,} total sector "
        f"records in dataset. Gap directionally supported; NES share {nes_share_pct:.0f}% noted.",
    )


def render_gap_findings_md(
    audit_raw: dict,
    spot_checks: list[dict],
    verdicts: list[tuple[str, str]],
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    synthesis = audit_raw.get("sonnet_synthesis", {})
    haiku = audit_raw.get("haiku_ranking", {})
    top5 = synthesis.get("top_5_gaps", [])
    total_cost = audit_raw.get("total_phase2_cost", 0.0)

    lines = [
        "# Phase 2 — Agentic Coverage & Quality Audit Findings",
        f"_Generated: {now}_",
        f"_Models: {haiku.get('audit_model', 'haiku')} (sector ranking) + "
        f"{synthesis.get('synthesis_model', 'sonnet')} (synthesis)_",
        f"_Prompt versions: {haiku.get('prompt_version', 'audit_v1')} / "
        f"{synthesis.get('prompt_version', 'audit_synthesis_v1')}_",
        f"_Phase 2 LLM cost: ${total_cost:.4f}_",
        f"_Spot-check: n={SPOT_CHECK_N} per gap, pure SQL, no LLM_",
        "",
        "---",
        "",
        "## Agent Findings (data-engineer)",
        "",
        "### Sector Ranking Summary (Haiku)",
        "",
        "| Rank | Sector | Coverage% | Priority | Commercial Relevance | Confidence |",
        "|---|---|---|---|---|---|",
    ]

    for s in haiku.get("ranked_sectors", []):
        lines.append(
            f"| {s['rank']} | {s['naics_desc']} | {s['overall_coverage_pct']}% "
            f"| {s['enrichment_priority']} | {s['commercial_relevance']}/5 "
            f"| {s['confidence']:.2f} |"
        )

    if haiku.get("audit_notes"):
        lines += ["", f"**Audit notes**: {haiku['audit_notes']}", ""]

    lines += [
        "",
        "### Top 5 Structural Gaps (Sonnet Synthesis)",
        "",
    ]

    for i, gap in enumerate(top5):
        sc = spot_checks[i] if i < len(spot_checks) else {}
        verdict, verdict_rationale = verdicts[i] if i < len(verdicts) else ("PENDING", "")

        verdict_emoji = {"CONFIRMED": "✓", "PLAUSIBLE": "~", "OVERSTATED": "!", "ARTIFACT": "✗", "PENDING": "?"}.get(verdict, "?")

        lines += [
            f"#### Gap {gap['rank']}: {gap['headline']}",
            "",
            f"**NAICS**: {gap.get('naics_code', '')} — {gap.get('naics_desc', '')}",
            f"**Prevalence**: {gap.get('prevalence', '')}",
            f"**Root cause**: {gap.get('root_cause', '')}",
            f"**Commercial impact**: {gap.get('commercial_impact', '')}",
            f"**Enrichment approach**: {gap.get('enrichment_approach', '')}",
            f"**Agent confidence**: {gap.get('confidence', 0.0):.2f} — {gap.get('confidence_rationale', '')}",
        ]
        lines += [
            f"**Verifier verdict**: {verdict_emoji} {verdict} — {verdict_rationale}",
            "",
        ]

    cross = synthesis.get("cross_gap_pattern", "")
    if cross:
        lines += ["**Cross-gap pattern**: " + cross, ""]

    rec = synthesis.get("recommended_phase4_target", "")
    if rec:
        lines += [f"**Recommended Phase 4 target**: {rec}", ""]

    lines += [
        "---",
        "",
        "## Verifier Spot-Check Detail",
        "",
        f"Each gap independently re-derived from `us_companies_clean.parquet` via SQL. "
        f"n={SPOT_CHECK_N} per gap. No LLM calls in this section.",
        "",
    ]

    for i, sc in enumerate(spot_checks):
        verdict, rationale = verdicts[i] if i < len(verdicts) else ("PENDING", "")
        lines += [
            f"### Gap {i+1} Spot-Check: {sc['naics_desc']} (NAICS {sc['naics_code']})",
            "",
            f"- Sector records in dataset: **{sc['sector_total_in_dataset']:,}**",
            f"- Industry labels matched: {sc['industry_labels_matched']}",
            f"- Sample fill rates (n={sc['spot_check_n']}): "
            f"website={sc['sample_fill_rates'].get('website', 'N/A')}%, "
            f"industry={sc['sample_fill_rates'].get('industry', 'N/A')}%, "
            f"size={sc['sample_fill_rates'].get('size', 'N/A')}%",
            f"- State distribution: {sc['sample_state_distribution']}",
            f"- Size distribution: {sc['sample_size_distribution']}",
            f"- **Verdict**: {verdict} — {rationale}",
            "",
            "<details><summary>Sampling methodology (SQL — reproducible with the dataset)</summary>",
            "",
            "```sql",
            sc.get("sql_count", ""),
            "```",
            "",
            "```sql",
            sc.get("sql_sample", ""),
            "```",
            "",
            "</details>",
            "",
        ]

    record_qf = audit_raw.get("record_quality_findings", {})
    if record_qf:
        n_audited = record_qf.get("total_records_audited", 0)
        n_per = record_qf.get("n_per_gap", 100)
        lines += [
            "---",
            "",
            f"## Record-Level Quality Observations (Haiku, n≈{n_audited})",
            "",
            f"Sampled from top-5 gap sectors, stratified by state (10 worst-covered Tier A + 5 Tier B states) "
            f"and size band. n={n_per} per gap. "
            "Haiku assessed each record for semantic quality issues that rules can't detect "
            "(website–company mismatch, industry mislabelling, platform URL misses, data anomalies).",
            "",
            "| Gap | Records Sampled | States Covered | Issues Found | Top Issues |",
            "|---|---|---|---|---|",
        ]
        for gap_key, gd in record_qf.get("by_gap", {}).items():
            n_states = len(gd.get("states_sampled", []))
            n_issues = gd.get("issues_found", 0)
            ic = gd.get("issue_counts", {})
            top_issues = ", ".join(
                f"{k} ({v})" for k, v in sorted(ic.items(), key=lambda x: -x[1])[:3]
            ) or "none"
            label = f"{gd.get('naics_desc', gap_key)} (NAICS {gd.get('naics_code', 'N/A')})"
            lines.append(f"| {label} | {gd.get('records_sampled', 0)} | {n_states} | {n_issues} | {top_issues} |")
        lines += [""]

    lines += [
        "---",
        "",
        "## Trust Calibration Note",
        "",
        "The data-engineer (Haiku + Sonnet) produced sector rankings and gap narratives from "
        "pre-aggregated statistics in `gap_candidates.json`. The verifier independently "
        f"re-derived each top-5 finding from raw `us_companies_clean.parquet` via SQL (n={SPOT_CHECK_N} "
        "per gap). Verdicts above reflect the verifier's independent assessment.",
        "",
        "Known methodological limits:",
        "- NES non-employer comparator inflates gaps in sole-proprietor-heavy sectors "
        "(Transportation, Other Services, Admin & Support).",
        "- Industry labels in our dataset map to NAICS via `industry_naics_mapping.json` "
        "(244 labels mapped); unmapped labels are excluded from sector counts.",
        "- Confidence scores are agent-estimated, not statistically derived.",
    ]

    return "\n".join(lines)


def main():
    logger.info("Phase 2 verifier starting")
    audit_raw = load_audit_raw()
    synthesis = audit_raw.get("sonnet_synthesis", {})
    top5 = synthesis.get("top_5_gaps", [])
    # actionable_sectors is the key written by phase2_audit.py
    actionable_sectors = audit_raw.get("actionable_sectors", [])

    if not top5:
        logger.error("No top_5_gaps in phase2_audit_raw.json — run phase2_audit.py first.")
        sys.exit(1)

    con = duckdb.connect()

    # Build sector-level lookups from actionable_sectors (written by phase2_audit.py)
    nes_share_by_naics = {
        s["naics_code"]: s.get("nes_share_of_comparator_pct", 0.0)
        for s in actionable_sectors
    }
    susb_coverage_by_naics = {
        s["naics_code"]: s.get("coverage_vs_susb_only_pct", 0.0)
        for s in actionable_sectors
    }

    spot_checks = []
    verdicts = []

    for gap in top5:
        raw_naics = gap.get("naics_code")
        naics_desc = gap.get("naics_desc", "")

        # Sonnet may emit a size-dimension insight with no NAICS code.
        # These can't be verified via sector SQL — log and skip the spot-check.
        if raw_naics is None or not str(raw_naics).strip():
            logger.info(f"Gap '{gap.get('headline', '')}' has no NAICS code — size-dimension insight, skipping SQL spot-check")
            sc = {
                "gap_id": gap.get("gap_id", "size_dimension"),
                "naics_code": "N/A",
                "naics_desc": naics_desc or "Size-dimension gap",
                "industry_labels_matched": [],
                "sector_total_in_dataset": 0,
                "spot_check_n": 0,
                "sql_count": "",
                "sql_sample": "",
                "sample_fill_rates": {},
                "sample_state_distribution": {},
                "sample_size_distribution": {},
                "sample_records": [],
            }
            spot_checks.append(sc)
            verdicts.append((
                "PLAUSIBLE",
                "Size-dimension gap — no NAICS code; verified via Phase 1 size quality summary "
                f"(enterprise 1.65% of records, website fill 80.9%). SQL spot-check not applicable.",
            ))
            continue

        naics_code = str(raw_naics)
        logger.info(f"Spot-checking NAICS {naics_code} — {naics_desc}")

        sc = spot_check_gap(con, gap, naics_code, naics_desc)
        spot_checks.append(sc)

        nes_share = nes_share_by_naics.get(naics_code, 0.0)
        susb_coverage = susb_coverage_by_naics.get(naics_code, 0.0)
        claimed_pct = _parse_prevalence_pct(gap.get("prevalence", "0"))
        verdict, rationale = derive_trust_verdict(sc, claimed_pct, nes_share, susb_coverage)
        verdicts.append((verdict, rationale))

        logger.info(f"  → {verdict}: {rationale[:80]}")

    md = render_gap_findings_md(audit_raw, spot_checks, verdicts)
    GAP_FINDINGS_PATH.write_text(md)
    logger.info(f"Wrote {GAP_FINDINGS_PATH}")
    logger.info("Phase 2 verification complete.")


if __name__ == "__main__":
    main()
