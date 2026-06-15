"""
Part 1 — SUSB State Coverage Comparator

Loads US Census SUSB 2022 firm counts by state and compares against our
source dataset to identify under-represented states.

Output: appends a coverage gap table to docs/part0-discovery.md
"""

import duckdb
import logging
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

SUSB_CSV = "data/raw/us_state_6digitnaics_2022.csv"
PARQUET = "data/processed/us_companies.parquet"
AUDIT_MD = "docs/part0-discovery.md"

# FIPS numeric code → full state name (50 states + DC)
FIPS_TO_STATE = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas",
    "06": "California", "08": "Colorado", "09": "Connecticut", "10": "Delaware",
    "11": "District of Columbia", "12": "Florida", "13": "Georgia", "15": "Hawaii",
    "16": "Idaho", "17": "Illinois", "18": "Indiana", "19": "Iowa",
    "20": "Kansas", "21": "Kentucky", "22": "Louisiana", "23": "Maine",
    "24": "Maryland", "25": "Massachusetts", "26": "Michigan", "27": "Minnesota",
    "28": "Mississippi", "29": "Missouri", "30": "Montana", "31": "Nebraska",
    "32": "Nevada", "33": "New Hampshire", "34": "New Jersey", "35": "New Mexico",
    "36": "New York", "37": "North Carolina", "38": "North Dakota", "39": "Ohio",
    "40": "Oklahoma", "41": "Oregon", "42": "Pennsylvania", "44": "Rhode Island",
    "45": "South Carolina", "46": "South Dakota", "47": "Tennessee", "48": "Texas",
    "49": "Utah", "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming",
}

from src.shared.config import CONFIG

TIER_A = CONFIG.geography_tiering.tier_a_min
TIER_B = CONFIG.geography_tiering.tier_b_min


def _gap_tier(ratio: float) -> str:
    return CONFIG.gap_tiers.classify(ratio)


def _sampling_tier(n: int) -> str:
    return CONFIG.geography_tiering.tier(n)


def load_susb_state_totals(path: str) -> pd.DataFrame:
    """Return one row per state with total SUSB firm count."""
    # pandas handles UTF-8 BOM and embedded newlines in column names cleanly
    raw = pd.read_csv(path, encoding="utf-8-sig", dtype=str)

    # Normalise column names: strip embedded newlines injected by the CSV header
    raw.columns = [c.replace("\n", " ").strip() for c in raw.columns]

    filtered = raw[
        (raw["NAICS"] == "--") &
        (raw["Enterprise Size"] == "01: Total") &
        (raw["State"] != "00")
    ].copy()

    filtered["fips"] = filtered["State"].str.zfill(2)
    filtered["susb_firms"] = (
        filtered["Firms"].str.replace(",", "", regex=False).astype(int)
    )
    filtered["state"] = filtered["fips"].map(FIPS_TO_STATE)
    filtered = filtered.dropna(subset=["state"])
    return filtered[["state", "susb_firms"]].sort_values("state").reset_index(drop=True)


def load_our_state_counts(path: str) -> pd.DataFrame:
    """Return one row per state with our record count."""
    state_list = ", ".join(f"'{s}'" for s in FIPS_TO_STATE.values())
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT state, COUNT(*) AS our_records
        FROM read_parquet('{path}')
        WHERE state IN ({state_list})
        GROUP BY state
        ORDER BY state
    """).df()
    con.close()
    return df


def build_coverage_table(susb: pd.DataFrame, ours: pd.DataFrame) -> pd.DataFrame:
    merged = susb.merge(ours, on="state", how="left")
    merged["our_records"] = merged["our_records"].fillna(0).astype(int)
    merged["coverage_ratio"] = merged["our_records"] / merged["susb_firms"]
    merged["coverage_pct"] = (merged["coverage_ratio"] * 100).round(1)
    merged["gap_tier"] = merged["coverage_ratio"].apply(_gap_tier)
    merged["sampling_tier"] = merged["our_records"].apply(_sampling_tier)
    return merged[
        ["state", "our_records", "susb_firms", "coverage_pct", "gap_tier", "sampling_tier"]
    ].sort_values("coverage_pct")


def format_markdown_table(df: pd.DataFrame) -> str:
    rows = []
    rows.append("| State | Our Records | SUSB Firms | Coverage % | Gap Tier | Sampling Tier |")
    rows.append("|-------|-------------|------------|------------|----------|---------------|")
    for _, r in df.iterrows():
        rows.append(
            f"| {r.state} | {r.our_records:,} | {r.susb_firms:,} | {r.coverage_pct}% "
            f"| {r.gap_tier} | {r.sampling_tier} |"
        )
    return "\n".join(rows)


def build_summary(df: pd.DataFrame) -> str:
    counts = df["gap_tier"].value_counts()
    high = counts.get("HIGH_GAP", 0)
    moderate = counts.get("MODERATE_GAP", 0)
    adequate = counts.get("ADEQUATE", 0)

    high_gap_tier_a = df[(df["gap_tier"] == "HIGH_GAP") & (df["sampling_tier"] == "A")]["state"].tolist()
    tier_a_note = (
        f"No Tier A states are in HIGH_GAP."
        if not high_gap_tier_a
        else f"Tier A states with HIGH_GAP (high-volume, under-represented): {', '.join(high_gap_tier_a)}."
    )

    return (
        f"Across {len(df)} states mapped to SUSB: {high} HIGH_GAP (<10% coverage), "
        f"{moderate} MODERATE_GAP (10–30%), {adequate} ADEQUATE (>30%). "
        f"{tier_a_note} "
        f"**Limitations**: SUSB counts legal firms (may be multi-establishment); our data counts records "
        f"(may include duplicates). Ratios are directional signals, not precise deficits. "
        f"SUSB vintage is 2022; our dataset vintage may differ."
    )


def append_to_audit(coverage_df: pd.DataFrame, audit_path: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    section = f"""
---

## SUSB State Coverage Gap Analysis

_Generated: {ts} | Source: US Census SUSB 2022 (`us_state_6digitnaics_2022.csv`) vs `us_companies.parquet`_

{build_summary(coverage_df)}

{format_markdown_table(coverage_df)}
"""
    with open(audit_path, "a") as f:
        f.write(section)
    log.info(f"Appended coverage gap section to {audit_path}")


def run(susb_path: str = SUSB_CSV, parquet_path: str = PARQUET, audit_path: str = AUDIT_MD) -> pd.DataFrame:
    for p in [susb_path, parquet_path]:
        if not Path(p).exists():
            raise FileNotFoundError(f"Required file not found: {p}")

    log.info("Loading SUSB state totals...")
    susb = load_susb_state_totals(susb_path)
    log.info(f"  {len(susb)} states loaded from SUSB")

    log.info("Loading source data state counts...")
    ours = load_our_state_counts(parquet_path)
    log.info(f"  {len(ours)} states found in source data")

    log.info("Building coverage table...")
    coverage = build_coverage_table(susb, ours)

    log.info("\n" + "=" * 70)
    log.info("  SUSB STATE COVERAGE GAP ANALYSIS")
    log.info("=" * 70)
    log.info(coverage.to_string(index=False))
    log.info("=" * 70)
    log.info(build_summary(coverage))

    append_to_audit(coverage, audit_path)
    return coverage


if __name__ == "__main__":
    run()
