"""
Phase 1 — NES + SUSB Combined Industry Coverage Comparator

Combines US Census SUSB 2022 (employer firms) and NES 2023 (non-employer
establishments) to produce a total business universe denominator, then
recomputes industry coverage ratios against our dataset.

Motivation: SUSB only counts firms with W-2 payroll. Non-employers
(~30M sole proprietors, freelancers, self-employed) are in NES. Sectors
like Information, Arts, and Education are over-represented in our dataset
relative to SUSB alone because our source platform captures individual
operators that SUSB misses.

Output: appends combined coverage section to data/processed/baseline_audit.md
"""

import duckdb
import logging
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

SUSB_CSV = "data/raw/us_state_6digitnaics_2022.csv"
NES_TXT = "data/raw/nonemp23st.txt"
PARQUET = "data/processed/us_companies.parquet"
AUDIT_MD = "data/processed/baseline_audit.md"
MAPPING_CACHE = "data/processed/industry_naics_mapping.json"

# All NAICS sector codes (must match industry_mapper.py)
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

# NES doesn't publish 2-digit header rows for sectors that span NAICS ranges.
# Map each SUSB sector code → list of 2-digit prefixes to sum from NES 3-digit rows.
# Sectors with a direct 2-digit NES row use a single-element list.
NES_SECTOR_MAP = {
    "11": ["11"], "21": ["21"], "22": ["22"], "23": ["23"],
    "31-33": ["31", "32", "33"],
    "42": ["42"],
    "44-45": ["44", "45"],
    "48-49": ["48", "49"],
    "51": ["51"], "52": ["52"], "53": ["53"], "54": ["54"],
    "55": [],           # Management of Companies — no non-employer category
    "56": ["56"], "61": ["61"], "62": ["62"], "71": ["71"], "72": ["72"], "81": ["81"],
    "99": [],           # Unclassified — no NES equivalent
}

# Sectors with direct 2-digit NES rows vs. those requiring 3-digit prefix sums
NES_DIRECT_2DIGIT = {"11","21","22","23","42","51","52","53","54","56","61","62","71","72","81"}


def load_susb_national_totals(path: str) -> pd.DataFrame:
    """Return NAICS-sector-level national firm totals from SUSB (State='00')."""
    raw = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    raw.columns = [c.replace("\n", " ").strip() for c in raw.columns]
    national = raw[
        (raw["State"] == "00") &
        (raw["Enterprise Size"] == "01: Total") &
        (raw["NAICS"].isin(NAICS_SECTORS.keys()))
    ].copy()
    national["susb_firms"] = national["Firms"].str.replace(",", "", regex=False).astype(int)
    return national[["NAICS", "susb_firms"]].rename(columns={"NAICS": "naics_code"}).reset_index(drop=True)


def load_nes_national_totals(path: str) -> pd.DataFrame:
    """
    Return NES non-employer establishment counts per NAICS sector, aggregated
    to national totals. Range sectors (31-33, 44-45, 48-49) are summed from
    3-digit rows; all others use the 2-digit summary row directly.
    """
    nes = pd.read_csv(path, dtype=str)
    nes["ESTAB"] = pd.to_numeric(nes["ESTAB"], errors="coerce").fillna(0)

    rows = []
    for naics_code, prefixes in NES_SECTOR_MAP.items():
        if not prefixes:
            rows.append({"naics_code": naics_code, "nes_nonemployers": 0})
            continue

        if len(prefixes) == 1 and prefixes[0] in NES_DIRECT_2DIGIT:
            # Use the 2-digit summary row — sum across all state rows
            total = nes[(nes["LFO"] == "-") & (nes["NAICS"] == prefixes[0])]["ESTAB"].sum()
        else:
            # Sum 3-digit rows whose first 2 chars match any prefix
            mask = (
                (nes["LFO"] == "-") &
                (nes["NAICS"].str.len() == 3) &
                nes["NAICS"].str[:2].isin(prefixes)
            )
            total = nes[mask]["ESTAB"].sum()

        rows.append({"naics_code": naics_code, "nes_nonemployers": int(total)})

    return pd.DataFrame(rows)


def load_our_naics_counts(parquet: str, mapping_cache: str) -> pd.DataFrame:
    """Load pre-computed label→NAICS mapping and count our records per sector."""
    import json

    if not Path(mapping_cache).exists():
        raise FileNotFoundError(
            f"Mapping cache not found: {mapping_cache}. Run src/industry_mapper.py first."
        )
    with open(mapping_cache) as f:
        label_to_naics = json.load(f)

    valid_codes = set(NAICS_SECTORS.keys())

    def _map(label: str) -> str:
        code = label_to_naics.get(label, "99")
        return code if code in valid_codes else "99"

    con = duckdb.connect()
    df = con.execute(f"""
        SELECT COALESCE(industry, '(null)') AS industry, COUNT(*) AS n
        FROM read_parquet('{parquet}')
        WHERE state IS NOT NULL
        GROUP BY industry
    """).df()
    con.close()

    df["naics_code"] = df["industry"].apply(_map)
    grouped = (
        df.groupby("naics_code")["n"]
        .sum()
        .reset_index()
        .rename(columns={"n": "our_records"})
    )
    return grouped


def build_combined_coverage(
    susb: pd.DataFrame,
    nes: pd.DataFrame,
    ours: pd.DataFrame,
) -> pd.DataFrame:
    merged = susb.merge(nes, on="naics_code", how="left")
    merged["nes_nonemployers"] = merged["nes_nonemployers"].fillna(0).astype(int)
    merged = merged.merge(ours, on="naics_code", how="left")
    merged["our_records"] = merged["our_records"].fillna(0).astype(int)

    merged["combined_universe"] = merged["susb_firms"] + merged["nes_nonemployers"]
    merged["coverage_ratio"] = merged["our_records"] / merged["combined_universe"]
    merged["coverage_pct"] = (merged["coverage_ratio"] * 100).round(1)
    merged["susb_only_pct"] = (merged["our_records"] / merged["susb_firms"] * 100).round(1)
    merged["gap_tier"] = merged["coverage_ratio"].apply(_gap_tier)
    merged["naics_desc"] = merged["naics_code"].map(NAICS_SECTORS)

    return merged[[
        "naics_code", "naics_desc", "our_records", "susb_firms",
        "nes_nonemployers", "combined_universe", "susb_only_pct",
        "coverage_pct", "gap_tier",
    ]].sort_values("coverage_pct")


def _gap_tier(ratio: float) -> str:
    if ratio < 0.10:
        return "HIGH_GAP"
    if ratio < 0.30:
        return "MODERATE_GAP"
    return "ADEQUATE"


def format_markdown_table(df: pd.DataFrame) -> str:
    rows = [
        "| NAICS | Sector | Our Records | SUSB Firms | NES Non-Emp | Combined | SUSB-Only % | Combined % | Gap Tier |",
        "|-------|--------|-------------|------------|-------------|----------|-------------|------------|----------|",
    ]
    for _, r in df.iterrows():
        rows.append(
            f"| {r.naics_code} | {r.naics_desc} | {r.our_records:,} | "
            f"{r.susb_firms:,} | {r.nes_nonemployers:,} | {r.combined_universe:,} | "
            f"{r.susb_only_pct}% | {r.coverage_pct}% | {r.gap_tier} |"
        )
    return "\n".join(rows)


def build_summary(df: pd.DataFrame) -> str:
    counts = df["gap_tier"].value_counts()
    high = counts.get("HIGH_GAP", 0)
    moderate = counts.get("MODERATE_GAP", 0)
    adequate = counts.get("ADEQUATE", 0)

    reclassified = df[df["susb_only_pct"] > 100][["naics_desc", "susb_only_pct", "coverage_pct"]].copy()
    recl_notes = "; ".join(
        f"{r.naics_desc} ({r.susb_only_pct}% → {r.coverage_pct}%)"
        for _, r in reclassified.iterrows()
    )

    return (
        f"Combined SUSB 2022 employer firms + NES 2023 non-employer establishments as universe denominator. "
        f"Coverage: {high} HIGH_GAP (<10%), {moderate} MODERATE_GAP (10–30%), {adequate} ADEQUATE (>30%). "
        f"Sectors that were over-indexed vs. SUSB alone, now adjusted: {recl_notes or 'none'}. "
        f"**Limitations**: SUSB 2022 and NES 2023 are different vintages — directional only. "
        f"NES counts legal establishments; our dataset may count individual practitioners. "
        f"Management of Companies (NAICS 55) and Unclassified (99) have no NES equivalent — "
        f"ratios for those sectors are unchanged from SUSB-only comparison."
    )


def append_to_audit(df: pd.DataFrame, audit_path: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    section = f"""
---

## SUSB + NES Combined Industry Coverage Gap Analysis

_Generated: {ts} | Sources: SUSB 2022 + NES 2023 national totals vs `us_companies.parquet`_

{build_summary(df)}

{format_markdown_table(df)}
"""
    with open(audit_path, "a") as f:
        f.write(section)
    log.info(f"Appended combined coverage section to {audit_path}")


def run(
    susb_path: str = SUSB_CSV,
    nes_path: str = NES_TXT,
    parquet_path: str = PARQUET,
    audit_path: str = AUDIT_MD,
    mapping_cache: str = MAPPING_CACHE,
) -> pd.DataFrame:
    for p in [susb_path, nes_path, parquet_path, mapping_cache]:
        if not Path(p).exists():
            raise FileNotFoundError(f"Required file not found: {p}")

    log.info("Loading SUSB national totals (employer firms)...")
    susb = load_susb_national_totals(susb_path)
    log.info(f"  {len(susb)} sectors | {susb['susb_firms'].sum():,} total employer firms")

    log.info("Loading NES national totals (non-employer establishments)...")
    nes = load_nes_national_totals(nes_path)
    log.info(f"  {len(nes)} sectors | {nes['nes_nonemployers'].sum():,} total non-employers")

    log.info("Loading our NAICS-level record counts...")
    ours = load_our_naics_counts(parquet_path, mapping_cache)

    log.info("Building combined coverage table...")
    coverage = build_combined_coverage(susb, nes, ours)

    log.info("\n" + "=" * 90)
    log.info("  COMBINED SUSB + NES INDUSTRY COVERAGE")
    log.info("=" * 90)
    log.info(coverage.to_string(index=False))
    log.info("=" * 90)
    log.info(build_summary(coverage))

    append_to_audit(coverage, audit_path)
    return coverage


if __name__ == "__main__":
    run()
