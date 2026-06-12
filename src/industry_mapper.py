"""
Phase 1 — SUSB Industry Coverage Mapper

Maps our free-text industry labels to 2-digit NAICS sectors using Claude Haiku,
then computes industry-level coverage ratios against SUSB national firm counts.

Output: appends industry coverage section to data/processed/baseline_audit.md
        saves mapping cache to data/processed/industry_naics_mapping.json
"""

import json
import logging
import os
import sys
import time
import duckdb
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.observability import ObservabilityLogger

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

SUSB_CSV = "data/raw/us_state_6digitnaics_2022.csv"
PARQUET = "data/processed/us_companies.parquet"
AUDIT_MD = "data/processed/baseline_audit.md"
MAPPING_CACHE = "data/processed/industry_naics_mapping.json"

PHASE = "phase_1_industry_map"
PHASE_BUDGET = 1.00  # $1 hard ceiling for this mapping step

MIN_INDUSTRY_COUNT = 500  # exclude rare/noisy labels

PROMPT_VERSION = "industry_map_v1"

# All NAICS sector codes available in SUSB at national & state level
NAICS_SECTORS = {
    "11": "Agriculture, Forestry, Fishing and Hunting",
    "21": "Mining, Quarrying, and Oil and Gas Extraction",
    "22": "Utilities",
    "23": "Construction",
    "31-33": "Manufacturing",
    "42": "Wholesale Trade",
    "44-45": "Retail Trade",
    "48-49": "Transportation and Warehousing",
    "51": "Information",
    "52": "Finance and Insurance",
    "53": "Real Estate and Rental and Leasing",
    "54": "Professional, Scientific, and Technical Services",
    "55": "Management of Companies and Enterprises",
    "56": "Administrative and Support and Waste Management",
    "61": "Educational Services",
    "62": "Health Care and Social Assistance",
    "71": "Arts, Entertainment, and Recreation",
    "72": "Accommodation and Food Services",
    "81": "Other Services (except Public Administration)",
    "99": "Industries not classified",
}

SYSTEM_PROMPT = (
    "You are a NAICS industry classification assistant. Map company industry "
    "labels to 2-digit NAICS sector codes.\n\n"
    "Available sectors:\n"
    + "\n".join(f"{code} - {desc}" for code, desc in NAICS_SECTORS.items())
    + "\n\nReturn ONLY a valid JSON object mapping each input label to its NAICS "
    "sector code string (e.g. \"23\", \"31-33\"). Use \"99\" for ambiguous labels. "
    "No explanation."
)


def get_industry_labels(parquet: str, min_count: int = MIN_INDUSTRY_COUNT) -> list[tuple[str, int]]:
    """Return (industry_label, record_count) for labels meeting min_count threshold."""
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT industry, COUNT(*) AS n
        FROM read_parquet('{parquet}')
        WHERE state IS NOT NULL AND industry IS NOT NULL
        GROUP BY industry
        HAVING COUNT(*) >= {min_count}
        ORDER BY n DESC
    """).df()
    con.close()
    return list(zip(df["industry"], df["n"].astype(int)))


def load_susb_national_totals(path: str) -> pd.DataFrame:
    """Return NAICS-sector-level national firm totals from SUSB (State='00')."""
    raw = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    raw.columns = [c.replace("\n", " ").strip() for c in raw.columns]

    national = raw[
        (raw["State"] == "00") &
        (raw["Enterprise Size"] == "01: Total") &
        (raw["NAICS"].isin(NAICS_SECTORS.keys()))
    ].copy()

    national["susb_firms"] = (
        national["Firms"].str.replace(",", "", regex=False).astype(int)
    )
    national["naics_desc"] = national["NAICS"].map(NAICS_SECTORS)
    return national[["NAICS", "naics_desc", "susb_firms"]].rename(
        columns={"NAICS": "naics_code"}
    ).reset_index(drop=True)


def map_industries_with_llm(
    labels: list[str],
    obs: ObservabilityLogger,
) -> dict[str, str]:
    """
    Call Claude Haiku once to map all labels → NAICS sector codes.
    Returns {label: naics_code}. Logs cost to observability.
    """
    phase_cost = obs.get_phase_cost(PHASE)
    if phase_cost >= PHASE_BUDGET:
        raise RuntimeError(
            f"Phase budget exhausted (${phase_cost:.4f} >= ${PHASE_BUDGET:.2f}). "
            "Delete data/processed/industry_naics_mapping.json to remap."
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)

    user_message = (
        "Map these industry labels to NAICS sector codes:\n\n"
        + json.dumps(labels, indent=2)
        + "\n\nReturn JSON: {\"label\": \"code\", ...}"
    )

    t0 = time.time()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    latency_ms = int((time.time() - t0) * 1000)

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    # Haiku pricing: $0.80/MTok input, $4.00/MTok output
    cost = (input_tokens * 0.80 + output_tokens * 4.00) / 1_000_000

    obs.log_call(
        phase=PHASE,
        model="claude-haiku-4-5-20251001",
        tokens=input_tokens + output_tokens,
        cost=cost,
        prompt_version=PROMPT_VERSION,
        outcome="success",
        metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "labels_mapped": len(labels),
        },
    )
    log.info(
        f"LLM call: {input_tokens} in + {output_tokens} out tokens | "
        f"${cost:.5f} | {latency_ms}ms"
    )

    raw_text = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    return json.loads(raw_text)


def load_or_create_mapping(
    labels: list[str],
    obs: ObservabilityLogger,
    cache_path: str = MAPPING_CACHE,
) -> dict[str, str]:
    """Return cached mapping if available; otherwise call LLM and cache result."""
    if Path(cache_path).exists():
        with open(cache_path) as f:
            cached = json.load(f)
        # If all labels are covered, use cache
        missing = [l for l in labels if l not in cached]
        if not missing:
            log.info(f"Using cached mapping ({len(cached)} labels, {cache_path})")
            return cached
        log.info(f"Cache found but {len(missing)} new labels — calling LLM")
        new_mapping = map_industries_with_llm(missing, obs)
        combined = {**cached, **new_mapping}
    else:
        log.info(f"No cache found — calling LLM for {len(labels)} labels")
        combined = map_industries_with_llm(labels, obs)

    Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(combined, f, indent=2, sort_keys=True)
    log.info(f"Mapping saved to {cache_path}")
    return combined


def build_our_naics_counts(
    parquet: str,
    label_to_naics: dict[str, str],
    min_count: int = MIN_INDUSTRY_COUNT,
) -> pd.DataFrame:
    """
    Assign each record a NAICS code via the mapping, then COUNT by naics_code.
    Records with unmapped labels or nulls are grouped under '99'.
    """
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT COALESCE(industry, '(null)') AS industry, COUNT(*) AS n
        FROM read_parquet('{parquet}')
        WHERE state IS NOT NULL
        GROUP BY industry
    """).df()
    con.close()

    valid_codes = set(NAICS_SECTORS.keys())

    def _map(label: str) -> str:
        code = label_to_naics.get(label, "99")
        return code if code in valid_codes else "99"

    df["naics_code"] = df["industry"].apply(_map)
    grouped = (
        df.groupby("naics_code")["n"]
        .sum()
        .reset_index()
        .rename(columns={"n": "our_records"})
    )
    return grouped


def build_coverage_table(
    susb: pd.DataFrame,
    ours: pd.DataFrame,
) -> pd.DataFrame:
    merged = susb.merge(ours, on="naics_code", how="left")
    merged["our_records"] = merged["our_records"].fillna(0).astype(int)
    merged["coverage_ratio"] = merged["our_records"] / merged["susb_firms"]
    merged["coverage_pct"] = (merged["coverage_ratio"] * 100).round(1)
    merged["gap_tier"] = merged["coverage_ratio"].apply(_gap_tier)
    return merged[
        ["naics_code", "naics_desc", "our_records", "susb_firms", "coverage_pct", "gap_tier"]
    ].sort_values("coverage_pct")


def _gap_tier(ratio: float) -> str:
    if ratio < 0.10:
        return "HIGH_GAP"
    if ratio < 0.30:
        return "MODERATE_GAP"
    return "ADEQUATE"


def format_markdown_table(df: pd.DataFrame) -> str:
    rows = [
        "| NAICS | Sector | Our Records | SUSB Firms | Coverage % | Gap Tier |",
        "|-------|--------|-------------|------------|------------|----------|",
    ]
    for _, r in df.iterrows():
        rows.append(
            f"| {r.naics_code} | {r.naics_desc} | {r.our_records:,} | "
            f"{r.susb_firms:,} | {r.coverage_pct}% | {r.gap_tier} |"
        )
    return "\n".join(rows)


def build_summary(df: pd.DataFrame, label_count: int, obs: ObservabilityLogger) -> str:
    counts = df["gap_tier"].value_counts()
    high = counts.get("HIGH_GAP", 0)
    moderate = counts.get("MODERATE_GAP", 0)
    adequate = counts.get("ADEQUATE", 0)
    phase_cost = obs.get_phase_cost(PHASE)

    high_gap_sectors = df[df["gap_tier"] == "HIGH_GAP"]["naics_desc"].tolist()
    gap_note = (
        f"HIGH_GAP sectors: {', '.join(high_gap_sectors)}."
        if high_gap_sectors
        else "No sectors in HIGH_GAP."
    )

    return (
        f"{label_count} industry labels (≥{MIN_INDUSTRY_COUNT} records each) mapped to "
        f"{len(df)} NAICS sectors via Claude Haiku (${phase_cost:.5f}). "
        f"Coverage: {high} HIGH_GAP (<10%), {moderate} MODERATE_GAP (10–30%), "
        f"{adequate} ADEQUATE (>30%). {gap_note} "
        f"**Limitations**: Mapping is LLM-generated and approximate; labels with ambiguous "
        f"industry scope may be misclassified. Records with null or rare industry labels "
        f"(<{MIN_INDUSTRY_COUNT}) are counted under NAICS 99 (unclassified). "
        f"SUSB national totals use State='00' aggregate (not sum of states). "
        f"Our dataset may contain duplicate records inflating coverage ratios."
    )


def append_to_audit(
    coverage_df: pd.DataFrame,
    label_count: int,
    obs: ObservabilityLogger,
    audit_path: str,
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    section = f"""
---

## SUSB Industry Coverage Gap Analysis

_Generated: {ts} | Source: SUSB 2022 national totals vs `us_companies.parquet` | Model: claude-haiku-4-5-20251001_

{build_summary(coverage_df, label_count, obs)}

{format_markdown_table(coverage_df)}
"""
    with open(audit_path, "a") as f:
        f.write(section)
    log.info(f"Appended industry coverage section to {audit_path}")


def run(
    susb_path: str = SUSB_CSV,
    parquet_path: str = PARQUET,
    audit_path: str = AUDIT_MD,
    cache_path: str = MAPPING_CACHE,
    force_remap: bool = False,
) -> pd.DataFrame:
    for p in [susb_path, parquet_path]:
        if not Path(p).exists():
            raise FileNotFoundError(f"Required file not found: {p}")

    obs = ObservabilityLogger()

    log.info(f"Budget check: ${obs.get_phase_cost(PHASE):.5f} / ${PHASE_BUDGET:.2f} used for {PHASE}")

    log.info(f"Loading industry labels (min_count={MIN_INDUSTRY_COUNT})...")
    label_pairs = get_industry_labels(parquet_path, MIN_INDUSTRY_COUNT)
    labels = [lbl for lbl, _ in label_pairs]
    log.info(f"  {len(labels)} distinct industry labels to map")

    if force_remap and Path(cache_path).exists():
        Path(cache_path).unlink()
        log.info("Cache cleared (force_remap=True)")

    log.info("Mapping labels to NAICS sectors...")
    mapping = load_or_create_mapping(labels, obs, cache_path)

    log.info("Loading SUSB national totals...")
    susb = load_susb_national_totals(susb_path)
    log.info(f"  {len(susb)} NAICS sectors loaded")

    log.info("Computing our NAICS-level record counts...")
    ours = build_our_naics_counts(parquet_path, mapping, MIN_INDUSTRY_COUNT)

    log.info("Building industry coverage table...")
    coverage = build_coverage_table(susb, ours)

    log.info("\n" + "=" * 70)
    log.info("  SUSB INDUSTRY COVERAGE GAP ANALYSIS")
    log.info("=" * 70)
    log.info(coverage.to_string(index=False))
    log.info("=" * 70)
    log.info(build_summary(coverage, len(labels), obs))

    append_to_audit(coverage, len(labels), obs, audit_path)
    return coverage


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-remap", action="store_true",
                        help="Ignore cached mapping and call LLM again")
    args = parser.parse_args()

    # Load .env if present
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    run(force_remap=args.force_remap)
