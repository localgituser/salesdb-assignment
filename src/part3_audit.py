"""
Part 3 Audit — Enrichment Baseline (11+ employees only)

Why this script exists:
  Part 3 prioritises enrichment gaps — missing or incorrect field values on
  existing records. To do that honestly, we must first exclude the 1–10
  employee (micro) cohort from the analysis for four reasons:

    1. Data quality: micro records have the highest null rates across every
       field (website null 24.7% vs ≤25% for 11+; industry null 7% vs ≤5%).
    2. Entity churn: sole traders and micro businesses fail at 35–45% within
       5 years. Records with size='1-10' AND founded>=2015 AND website IS NULL
       AND type IS NULL are high-probability stale entities (HIGH_CHURN_RISK
       flag from Part 1, §5b). Enriching them wastes tokens and pollutes output.
    3. Web presence: micro businesses are disproportionately offline. A 24.7%
       website null rate means roughly 1-in-4 micro records can't be enriched
       via web search even in principle — the company simply has no website.
    4. Sales priority: Firmable's B2B ICP targets companies with 11+ employees.
       Micro records represent almost zero direct revenue for Sales Intelligence
       customers running ABM or outbound sequences.

  Effective working set for Part 3 onwards: size NOT IN ('1-10') AND size IS NOT NULL
  (1,491,060 records after state normalisation in part0_companies_clean.parquet)

Outputs:
  - Console: summary tables for review
  - data/processed/part3_enrichment_baseline.json: machine-readable numbers
    referenced by docs/part3-commercial.md

Run: python src/part3_audit.py
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

PARQUET = "data/processed/part0_companies_clean.parquet"
OUTPUT = "data/processed/part3_enrichment_baseline.json"

PLATFORM_DOMAINS = [
    "yelp.com", "facebook.com", "instagram.com", "linkedin.com", "twitter.com",
    "linktr.ee", "bit.ly", "hub.biz", "wixsite.com", "weebly.com",
    "wordpress.com", "squarespace.com", "google.com", "amazon.com", "youtube.com",
]

INDUSTRY_DUPLICATE_PAIRS = [
    ("it services and it consulting", "information technology & services"),
    ("wellness and fitness services", "health, wellness & fitness"),
    ("non-profit organizations", "non-profit organization management"),
]

SIZE_ORDER = ["11-50", "51-200", "201-500", "501-1K", "1K-5K", "5K-10K", "10K+"]


def run(conn: duckdb.DuckDBPyConnection) -> dict:
    results = {}

    # ── 0. Scope breakdown ────────────────────────────────────────────────────
    logger.info("Querying scope breakdown...")
    scope = conn.execute(f"""
        SELECT
          COUNT(*)                                                       AS total,
          SUM(CASE WHEN size = '1-10'                          THEN 1 ELSE 0 END) AS micro,
          SUM(CASE WHEN size NOT IN ('1-10') AND size IS NOT NULL THEN 1 ELSE 0 END) AS eleven_plus,
          SUM(CASE WHEN size IS NULL                           THEN 1 ELSE 0 END) AS size_null
        FROM read_parquet('{PARQUET}')
        WHERE state IS NOT NULL
    """).fetchone()
    results["scope"] = {
        "total_valid_state": scope[0],
        "micro_1_10": scope[1],
        "eleven_plus_known_size": scope[2],
        "size_null": scope[3],
    }
    print("\n=== SCOPE BREAKDOWN ===")
    print(f"  Total (valid state):     {scope[0]:>10,}")
    print(f"  Micro (1–10):            {scope[1]:>10,}  ({100*scope[1]/scope[0]:.1f}%)")
    print(f"  11+ known size:          {scope[2]:>10,}  ({100*scope[2]/scope[0]:.1f}%)")
    print(f"  Size NULL (excluded):    {scope[3]:>10,}  ({100*scope[3]/scope[0]:.1f}%)")

    # ── 1. Fill rates by size band (11+ only) ─────────────────────────────────
    logger.info("Querying fill rates by size band (11+)...")
    size_case = " ".join(
        f"WHEN '{s}' THEN {i}" for i, s in enumerate(SIZE_ORDER, 1)
    )
    rows = conn.execute(f"""
        SELECT
          size,
          COUNT(*)                                                              AS records,
          SUM(CASE WHEN website  IS NULL THEN 1 ELSE 0 END)                   AS website_missing,
          ROUND(100.0 * SUM(CASE WHEN website  IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS website_fill_pct,
          SUM(CASE WHEN industry IS NULL THEN 1 ELSE 0 END)                   AS industry_missing,
          ROUND(100.0 * SUM(CASE WHEN industry IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS industry_fill_pct
        FROM read_parquet('{PARQUET}')
        WHERE state IS NOT NULL
          AND size NOT IN ('1-10')
          AND size IS NOT NULL
        GROUP BY size
        ORDER BY CASE size {size_case} END
    """).fetchall()

    print("\n=== FILL RATES BY SIZE BAND (11+ only) ===")
    print(f"{'Size':<12} {'Records':>10} {'Website Fill':>14} {'Website Miss':>14} {'Ind. Fill':>11} {'Ind. Miss':>11}")
    print("-" * 78)
    fill_by_band = []
    for r in rows:
        size, recs, w_miss, w_fill, i_miss, i_fill = r
        print(f"{size:<12} {recs:>10,} {w_fill:>13.2f}% {w_miss:>13,}  {i_fill:>10.2f}% {i_miss:>10,}")
        fill_by_band.append({
            "size": size, "records": recs,
            "website_fill_pct": w_fill, "website_missing": w_miss,
            "industry_fill_pct": i_fill, "industry_missing": i_miss,
        })
    results["fill_by_size_band"] = fill_by_band

    # ── 2. Aggregate 11+ fill rates ───────────────────────────────────────────
    logger.info("Querying aggregate 11+ fill rates...")
    agg = conn.execute(f"""
        SELECT
          COUNT(*)                                                              AS total,
          SUM(CASE WHEN website  IS NULL THEN 1 ELSE 0 END)                   AS website_missing,
          ROUND(100.0 * SUM(CASE WHEN website  IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS website_fill_pct,
          SUM(CASE WHEN industry IS NULL THEN 1 ELSE 0 END)                   AS industry_missing,
          ROUND(100.0 * SUM(CASE WHEN industry IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS industry_fill_pct
        FROM read_parquet('{PARQUET}')
        WHERE state IS NOT NULL
          AND size NOT IN ('1-10')
          AND size IS NOT NULL
    """).fetchone()
    results["aggregate_11plus"] = {
        "total_records": agg[0],
        "website_missing_raw_null": agg[1],
        "website_fill_pct": agg[2],
        "industry_missing": agg[3],
        "industry_fill_pct": agg[4],
    }
    print("\n=== AGGREGATE 11+ FILL RATES ===")
    print(f"  Total 11+ records:       {agg[0]:>10,}")
    print(f"  Website fill:            {agg[2]:>9.2f}%  ({agg[1]:,} missing)")
    print(f"  Industry fill:           {agg[4]:>9.2f}%  ({agg[3]:,} missing)")

    # ── 3. Platform URLs in 11+ band ──────────────────────────────────────────
    logger.info("Querying platform URL counts by segment...")
    domain_list = ", ".join(f"'{d}'" for d in PLATFORM_DOMAINS)
    platform_rows = conn.execute(f"""
        SELECT
          CASE
            WHEN size = '1-10'   THEN 'micro_1-10'
            WHEN size IS NULL     THEN 'size_null'
            ELSE '11+'
          END AS segment,
          COUNT(*) AS platform_url_count
        FROM read_parquet('{PARQUET}')
        WHERE state IS NOT NULL
          AND website IS NOT NULL
          AND (
            regexp_extract(lower(website), 'https?://(?:www[.])?([^/]+)', 1) IN ({domain_list})
            OR regexp_extract(lower(website), '^(?:www[.])?([^/]+)', 1) IN ({domain_list})
          )
        GROUP BY 1
        ORDER BY 2 DESC
    """).fetchall()
    platform_by_segment = {r[0]: r[1] for r in platform_rows}
    results["platform_urls_by_segment"] = platform_by_segment
    platform_11plus = platform_by_segment.get("11+", 0)
    print("\n=== PLATFORM URLs BY SEGMENT ===")
    for seg, cnt in platform_by_segment.items():
        print(f"  {seg:<15}: {cnt:>7,}")
    print(f"\n  True website gap (11+) = {agg[1]:,} raw null + {platform_11plus:,} platform URLs = {agg[1]+platform_11plus:,}")
    results["aggregate_11plus"]["website_true_gap"] = agg[1] + platform_11plus

    # ── 4. Industry semantic duplicates (11+ only) ────────────────────────────
    logger.info("Querying industry semantic duplicate pairs (11+)...")
    print("\n=== INDUSTRY SEMANTIC DUPLICATES (11+ only) ===")
    dup_results = []
    total_dup = 0
    for a, b in INDUSTRY_DUPLICATE_PAIRS:
        row = conn.execute(f"""
            SELECT
              SUM(CASE WHEN lower(industry) = '{a}' THEN 1 ELSE 0 END) AS label_a,
              SUM(CASE WHEN lower(industry) = '{b}' THEN 1 ELSE 0 END) AS label_b,
              SUM(CASE WHEN lower(industry) IN ('{a}', '{b}') THEN 1 ELSE 0 END) AS combined
            FROM read_parquet('{PARQUET}')
            WHERE state IS NOT NULL
              AND size NOT IN ('1-10')
              AND size IS NOT NULL
        """).fetchone()
        label_a, label_b, combined = row
        total_dup += combined
        dup_results.append({"label_a": a, "label_b": b, "count_a": label_a, "count_b": label_b, "combined": combined})
        print(f"  '{a}': {label_a:,}")
        print(f"  '{b}': {label_b:,}")
        print(f"  → combined: {combined:,}\n")
    results["industry_semantic_duplicates"] = {
        "pairs": dup_results,
        "total_affected_records": total_dup,
    }
    total_industry_quality_gap = agg[3] + total_dup
    results["aggregate_11plus"]["industry_quality_gap_total"] = total_industry_quality_gap
    print(f"  Total industry quality gap: {agg[3]:,} missing + {total_dup:,} split = {total_industry_quality_gap:,}")

    # ── 5. Worst 10 states by website fill (11+) ──────────────────────────────
    logger.info("Querying worst states by website fill (11+)...")
    state_rows = conn.execute(f"""
        SELECT
          state,
          COUNT(*) AS records,
          ROUND(100.0 * SUM(CASE WHEN website  IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS website_fill_pct,
          ROUND(100.0 * SUM(CASE WHEN industry IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS industry_fill_pct
        FROM read_parquet('{PARQUET}')
        WHERE state IS NOT NULL
          AND size NOT IN ('1-10')
          AND size IS NOT NULL
        GROUP BY state
        HAVING COUNT(*) >= 5000
        ORDER BY website_fill_pct ASC
        LIMIT 10
    """).fetchall()
    print("\n=== WORST 10 STATES — WEBSITE FILL (11+ only, min 5K records) ===")
    print(f"{'State':<22} {'Records':>8} {'Website Fill':>13} {'Industry Fill':>14}")
    print("-" * 62)
    worst_states = []
    for r in state_rows:
        state, recs, w_fill, i_fill = r
        print(f"{state:<22} {recs:>8,} {w_fill:>12.1f}% {i_fill:>13.1f}%")
        worst_states.append({"state": state, "records": recs, "website_fill_pct": w_fill, "industry_fill_pct": i_fill})
    results["worst_states_website_fill_11plus"] = worst_states

    return results


def main():
    if not Path(PARQUET).exists():
        logger.error(f"Parquet file not found: {PARQUET}. Run Part 0 first.")
        sys.exit(1)

    conn = duckdb.connect()
    results = run(conn)

    results["meta"] = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "source_file": PARQUET,
        "scope_filter": "state IS NOT NULL AND size NOT IN ('1-10') AND size IS NOT NULL",
        "script": "src/part3_audit.py",
    }

    output_path = Path(OUTPUT)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Saved enrichment baseline to {OUTPUT}")
    print(f"\n✓ Written to {OUTPUT}")


if __name__ == "__main__":
    main()
