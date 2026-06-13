"""
Phase 1.6 — Deterministic Gap Detection

Computes our_count / SUSB_count per state×industry cell to produce a ranked
list of coverage gaps. Pure Python/SQL — no LLM calls. Phase 2 consumes the
output JSON and adds LLM reasoning on top.

Filters applied:
  - Records with null state are excluded from cross-tab denominators.
    They are logged separately as state_unknown_high_value.
  - Tier C states (our_records < TIER_B_MIN) are excluded from gap candidates.
  - Records missing industry stay in the denominator (they ARE the gap signal).

Output: data/processed/gap_candidates.json
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from src.config import CONFIG

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

SUSB_CSV = "data/raw/us_state_6digitnaics_2022.csv"
CLEAN_PARQUET = "data/processed/us_companies_clean.parquet"
MAPPING_CACHE = "data/processed/industry_naics_mapping.json"
OUTPUT_JSON = "data/processed/gap_candidates.json"

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

# High-value size bands for null-state logging
HIGH_VALUE_BANDS = ("51-200", "201-500", "501-1K", "1K-5K", "5K-10K", "10K+")


def load_susb_state_sector(path: str) -> pd.DataFrame:
    """Return one row per (state_name, naics_code) with SUSB employer firm count."""
    raw = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    raw.columns = [c.replace("\n", " ").strip() for c in raw.columns]

    sector_codes = set(NAICS_SECTORS.keys()) - {"99"}  # 99 has no SUSB equivalent

    df = raw[
        (raw["State"] != "00") &
        (raw["Enterprise Size"] == "01: Total") &
        (raw["NAICS"].isin(sector_codes))
    ].copy()

    df["susb_firms"] = df["Firms"].str.replace(",", "", regex=False).astype(int)
    df = df.rename(columns={"State Name": "state", "NAICS": "naics_code"})
    return df[["state", "naics_code", "susb_firms"]].reset_index(drop=True)


def load_industry_mapping(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def load_our_state_counts(parquet: str) -> pd.DataFrame:
    """Total our record count per state (for state tier calculation)."""
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT state, COUNT(*) AS total_records
        FROM read_parquet('{parquet}')
        WHERE state IS NOT NULL
        GROUP BY state
    """).df()
    con.close()
    return df


def load_our_state_industry_counts(parquet: str, label_to_naics: dict) -> pd.DataFrame:
    """
    Count our records per state × NAICS sector.

    Maps free-text industry labels → NAICS sector codes using the cached mapping.
    Industry IS NULL → '99'. Industry with no mapping → '99'.
    """
    con = duckdb.connect()
    raw = con.execute(f"""
        SELECT state, COALESCE(industry, '(null)') AS industry, COUNT(*) AS n
        FROM read_parquet('{parquet}')
        WHERE state IS NOT NULL
        GROUP BY state, industry
    """).df()
    con.close()

    valid = set(NAICS_SECTORS.keys())

    def _map(label: str) -> str:
        if label == "(null)":
            return "99"
        code = label_to_naics.get(label.lower(), "99")
        return code if code in valid else "99"

    raw["naics_code"] = raw["industry"].apply(_map)
    grouped = (
        raw.groupby(["state", "naics_code"])["n"]
        .sum()
        .reset_index()
        .rename(columns={"n": "our_records"})
    )
    return grouped


def load_null_state_high_value(parquet: str) -> dict:
    """
    Return count of mid-market and enterprise records with null state post-cleanup.
    These are excluded from state-level gap ratios but logged as a separate finding.
    """
    bands_sql = ", ".join(f"'{b}'" for b in HIGH_VALUE_BANDS)
    con = duckdb.connect()
    total_null = con.execute(f"""
        SELECT COUNT(*) FROM read_parquet('{parquet}') WHERE state IS NULL
    """).fetchone()[0]

    breakdown = con.execute(f"""
        SELECT size, COUNT(*) AS n
        FROM read_parquet('{parquet}')
        WHERE state IS NULL AND size IN ({bands_sql})
        GROUP BY size
        ORDER BY n DESC
    """).df()
    con.close()

    size_dict = dict(zip(breakdown["size"], breakdown["n"].astype(int)))
    hv_total = sum(size_dict.values())
    return {"total_null_state": int(total_null), "hv_count": hv_total, "size_breakdown": size_dict}


def build_cross_tab(
    susb: pd.DataFrame,
    ours_by_state_sector: pd.DataFrame,
    state_totals: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge SUSB and our counts; compute coverage ratio and gap tier per cell.
    Excludes Tier C states.
    """
    # Attach state tier
    state_totals["state_tier"] = state_totals["total_records"].apply(
        CONFIG.geography_tiering.tier
    )

    merged = susb.merge(ours_by_state_sector, on=["state", "naics_code"], how="left")
    merged["our_records"] = merged["our_records"].fillna(0).astype(int)
    merged = merged.merge(state_totals[["state", "state_tier"]], on="state", how="left")

    # Drop Tier C states and states not in our dataset
    merged = merged[merged["state_tier"].isin(["A", "B"])].copy()

    merged["coverage_ratio"] = merged["our_records"] / merged["susb_firms"]
    merged["coverage_pct"] = (merged["coverage_ratio"] * 100).round(2)
    merged["gap_tier"] = merged["coverage_ratio"].apply(CONFIG.gap_tiers.classify)
    merged["naics_desc"] = merged["naics_code"].map(NAICS_SECTORS)

    return merged[[
        "state", "naics_code", "naics_desc", "our_records",
        "susb_firms", "coverage_ratio", "coverage_pct",
        "gap_tier", "state_tier",
    ]].sort_values(["gap_tier", "coverage_pct"]).reset_index(drop=True)


def build_gap_id(state: str, naics_code: str) -> str:
    return f"{state.replace(' ', '_')}_{naics_code.replace('-', '_')}"


def cross_tab_to_records(df: pd.DataFrame) -> list:
    records = []
    for _, r in df.iterrows():
        records.append({
            "gap_id": build_gap_id(r.state, r.naics_code),
            "state": r.state,
            "naics_code": r.naics_code,
            "naics_desc": r.naics_desc,
            "our_records": int(r.our_records),
            "susb_firms": int(r.susb_firms),
            "coverage_ratio": round(float(r.coverage_ratio), 4),
            "coverage_pct": float(r.coverage_pct),
            "gap_tier": r.gap_tier,
            "state_tier": r.state_tier,
        })
    return records


def build_summary(df: pd.DataFrame, gap_cells: list) -> dict:
    tier_counts = df["gap_tier"].value_counts().to_dict()
    state_tier_counts = df["state_tier"].value_counts().to_dict()

    # Top sectors by HIGH_GAP frequency
    high_gap = df[df["gap_tier"] == "HIGH_GAP"]
    top_high_gap_sectors = (
        high_gap.groupby("naics_desc")["state"]
        .count()
        .sort_values(ascending=False)
        .head(5)
        .reset_index()
        .rename(columns={"state": "state_count"})
        .to_dict(orient="records")
    )

    return {
        "states_analyzed": int(df["state"].nunique()),
        "sectors_analyzed": int(df["naics_code"].nunique()),
        "total_cells": len(df),
        "tier_a_states": int(state_tier_counts.get("A", 0) / df["naics_code"].nunique()),
        "tier_b_states": int(state_tier_counts.get("B", 0) / df["naics_code"].nunique()),
        "high_gap_cells": int(tier_counts.get("HIGH_GAP", 0)),
        "moderate_gap_cells": int(tier_counts.get("MODERATE_GAP", 0)),
        "adequate_cells": int(tier_counts.get("ADEQUATE", 0)),
        "gap_candidates_count": len(gap_cells),
        "top_high_gap_sectors": top_high_gap_sectors,
    }


def run(
    susb_path: str = SUSB_CSV,
    parquet_path: str = CLEAN_PARQUET,
    mapping_path: str = MAPPING_CACHE,
    output_path: str = OUTPUT_JSON,
) -> dict:
    for p in [susb_path, parquet_path, mapping_path]:
        if not Path(p).exists():
            raise FileNotFoundError(f"Required file not found: {p}")

    log.info("Loading SUSB state×sector data...")
    susb = load_susb_state_sector(susb_path)
    log.info(f"  {len(susb)} state×sector cells from SUSB")

    log.info("Loading industry label→NAICS mapping...")
    label_to_naics = load_industry_mapping(mapping_path)
    log.info(f"  {len(label_to_naics)} industry labels mapped")

    log.info("Counting our records by state×sector...")
    ours = load_our_state_industry_counts(parquet_path, label_to_naics)
    log.info(f"  {ours['our_records'].sum():,} total records with valid state")

    log.info("Counting our records by state (for tier assignment)...")
    state_totals = load_our_state_counts(parquet_path)

    log.info("Querying null-state high-value residue...")
    null_state_info = load_null_state_high_value(parquet_path)
    log.info(
        f"  Null-state total: {null_state_info['total_null_state']:,} | "
        f"High-value (51+): {null_state_info['hv_count']:,}"
    )

    log.info("Building state×industry cross-tab...")
    cross_tab = build_cross_tab(susb, ours, state_totals)
    log.info(f"  {len(cross_tab)} cells after Tier C exclusion")

    # Gap candidates: HIGH_GAP and MODERATE_GAP only
    gap_df = cross_tab[cross_tab["gap_tier"].isin(["HIGH_GAP", "MODERATE_GAP"])]
    gap_cells = cross_tab_to_records(gap_df)
    all_cells = cross_tab_to_records(cross_tab)

    log.info(f"  Gap candidates: {len(gap_cells)} cells ({len(gap_df[gap_df['gap_tier']=='HIGH_GAP'])} HIGH, {len(gap_df[gap_df['gap_tier']=='MODERATE_GAP'])} MODERATE)")

    summary = build_summary(cross_tab, gap_cells)

    output = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_parquet": parquet_path,
            "susb_vintage": 2022,
            "total_records_with_state": int(ours["our_records"].sum()),
            "total_records_null_state": null_state_info["total_null_state"],
            "excluded_state_tiers": ["C"],
            "gap_tier_thresholds": {
                "HIGH_GAP_max_ratio": CONFIG.gap_tiers.high_gap_max,
                "MODERATE_GAP_max_ratio": CONFIG.gap_tiers.moderate_gap_max,
            },
        },
        "state_unknown_high_value": {
            "gap_id": "state_unknown_high_value",
            "description": (
                "Mid-market and enterprise records (size 51+) with null state post-cleanup. "
                "Excluded from state×industry gap ratios because state is a required grouping key. "
                "Should be included in Phase 4 enrichment without a state filter."
            ),
            "total_null_state_records": null_state_info["total_null_state"],
            "mid_market_enterprise_count": null_state_info["hv_count"],
            "size_breakdown": null_state_info["size_breakdown"],
            "gap_tier": "state_unknown",
            "phase4_treatment": "include_in_enrichment_without_state_filter",
        },
        "summary": summary,
        "gap_candidates": gap_cells,
        "all_cells": all_cells,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    log.info(f"Written: {output_path}")

    log.info("\n" + "=" * 70)
    log.info("  PHASE 1.6 GAP DETECTION SUMMARY")
    log.info("=" * 70)
    log.info(f"  States analyzed: {summary['states_analyzed']} (Tier A: {summary['tier_a_states']}, Tier B: {summary['tier_b_states']})")
    log.info(f"  Sectors analyzed: {summary['sectors_analyzed']}")
    log.info(f"  Gap candidates: {summary['gap_candidates_count']} ({summary['high_gap_cells']} HIGH_GAP, {summary['moderate_gap_cells']} MODERATE_GAP)")
    log.info(f"  Null-state high-value residue: {null_state_info['hv_count']:,} records logged as state_unknown_high_value")
    if summary["top_high_gap_sectors"]:
        log.info("  Top HIGH_GAP sectors (by state count):")
        for s in summary["top_high_gap_sectors"]:
            log.info(f"    {s['naics_desc']}: {s['state_count']} states")
    log.info("=" * 70)

    return output


if __name__ == "__main__":
    run()
