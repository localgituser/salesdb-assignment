"""
Phase 1 — Baseline Metrics SQL
Produces all tables needed for baseline_audit.md:
  1. Nationwide record counts & coverage
  2. Field-level fill-rate (missingness) — nationwide
  3. Fill-rate by state — website, industry, size (enrichment opportunity map)
  4. Nationwide distributions (industry, size, type)
  5. State-level distributions with tier classification
  6. Data-quality flags (with duplicate summary)
  7. Candidate key analysis

Tier thresholds are calibrated for the ~4.25M US record dataset:
  Tier A: ≥ 50,000 records  (high density — full audit confidence)
  Tier B: 10,000–49,999     (medium density — directional)
  Tier C: < 10,000          (thin coverage — flag only, exclude from ranked gap lists)
"""

import duckdb
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

PARQUET = "data/processed/us_companies.parquet"

US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming", "District of Columbia",
    "Puerto Rico", "Guam", "U.S. Virgin Islands", "American Samoa",
    "Northern Mariana Islands",
]

# Build a SQL literal list for IN clauses
US_STATE_LIST = ", ".join(f"'{s}'" for s in US_STATES)

QUERIES = {

    # ── 1. Record Counts & Coverage ──────────────────────────────────────────
    "record_counts": f"""
        SELECT
            COUNT(*)                                              AS total_raw,
            SUM(CASE WHEN state IN ({US_STATE_LIST}) THEN 1 END) AS us_records,
            SUM(CASE WHEN state IS NULL              THEN 1 END) AS null_state,
            SUM(CASE WHEN state NOT IN ({US_STATE_LIST})
                      AND state IS NOT NULL          THEN 1 END) AS non_us_records,
            ROUND(
                SUM(CASE WHEN state IN ({US_STATE_LIST}) THEN 1 END) * 100.0 / COUNT(*), 2
            )                                                     AS us_pct
        FROM read_parquet('{PARQUET}')
    """,

    # ── 2. Field-Level Fill-Rate (nationwide, US records only) ───────────────
    "fill_rates": f"""
        WITH us AS (
            SELECT * FROM read_parquet('{PARQUET}')
            WHERE state IN ({US_STATE_LIST})
        ),
        totals AS (SELECT COUNT(*) AS n FROM us)
        SELECT
            'handle'   AS field, ROUND(COUNT(handle)   * 100.0 / MAX(n), 2) AS fill_pct FROM us, totals
        UNION ALL SELECT 'name',     ROUND(COUNT(name)     * 100.0 / MAX(n), 2) FROM us, totals
        UNION ALL SELECT 'website',  ROUND(COUNT(website)  * 100.0 / MAX(n), 2) FROM us, totals
        UNION ALL SELECT 'industry', ROUND(COUNT(industry) * 100.0 / MAX(n), 2) FROM us, totals
        UNION ALL SELECT 'size',     ROUND(COUNT(size)     * 100.0 / MAX(n), 2) FROM us, totals
        UNION ALL SELECT 'type',     ROUND(COUNT(type)     * 100.0 / MAX(n), 2) FROM us, totals
        UNION ALL SELECT 'founded',  ROUND(COUNT(founded)  * 100.0 / MAX(n), 2) FROM us, totals
        UNION ALL SELECT 'city',     ROUND(COUNT(city)     * 100.0 / MAX(n), 2) FROM us, totals
        UNION ALL SELECT 'state',    ROUND(COUNT(state)    * 100.0 / MAX(n), 2) FROM us, totals
        ORDER BY fill_pct
    """,

    # ── 3a. Industry Distribution (top 25, US only) ──────────────────────────
    "industry_distribution": f"""
        SELECT
            COALESCE(industry, '(null)') AS industry,
            COUNT(*)                     AS records,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
        FROM read_parquet('{PARQUET}')
        WHERE state IN ({US_STATE_LIST})
        GROUP BY industry
        ORDER BY records DESC
        LIMIT 25
    """,

    # ── 3b. Size Distribution (US only) ──────────────────────────────────────
    "size_distribution": f"""
        SELECT
            COALESCE(size, '(null)') AS size,
            COUNT(*)                 AS records,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
        FROM read_parquet('{PARQUET}')
        WHERE state IN ({US_STATE_LIST})
        GROUP BY size
        ORDER BY records DESC
    """,

    # ── 3c. Company Type Distribution (US only) ──────────────────────────────
    "type_distribution": f"""
        SELECT
            COALESCE(type, '(null)') AS company_type,
            COUNT(*)                 AS records,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
        FROM read_parquet('{PARQUET}')
        WHERE state IN ({US_STATE_LIST})
        GROUP BY type
        ORDER BY records DESC
    """,


    # ── 3d. Fill-Rate by State (enrichment opportunity map) ──────────────────
    # Commercially load-bearing fields only: website, industry, size.
    # Ordered by avg_fill_pct ASC so worst-coverage states surface first.
    "fill_rates_by_state": f"""
        WITH us AS (
            SELECT state, website, industry, size
            FROM read_parquet('{PARQUET}')
            WHERE state IN ({US_STATE_LIST})
        ),
        state_totals AS (
            SELECT state, COUNT(*) AS n FROM us GROUP BY state
        )
        SELECT
            u.state,
            t.n                                                           AS records,
            CASE
                WHEN t.n >= 50000 THEN 'A'
                WHEN t.n >= 10000 THEN 'B'
                ELSE 'C'
            END                                                           AS tier,
            ROUND(COUNT(u.website)  * 100.0 / t.n, 1)                   AS website_fill_pct,
            ROUND(COUNT(u.industry) * 100.0 / t.n, 1)                   AS industry_fill_pct,
            ROUND(COUNT(u.size)     * 100.0 / t.n, 1)                   AS size_fill_pct,
            ROUND(
                (COUNT(u.website) + COUNT(u.industry) + COUNT(u.size)) * 100.0
                / (3.0 * t.n), 1
            )                                                             AS avg_fill_pct
        FROM us u
        JOIN state_totals t ON u.state = t.state
        GROUP BY u.state, t.n
        ORDER BY avg_fill_pct ASC
    """,

    # ── 4. State-Level Distribution with Tier ────────────────────────────────
    "state_tiers": f"""
        SELECT
            state,
            COUNT(*) AS records,
            CASE
                WHEN COUNT(*) >= 50000 THEN 'A'
                WHEN COUNT(*) >= 10000 THEN 'B'
                ELSE 'C'
            END AS tier,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct_of_us
        FROM read_parquet('{PARQUET}')
        WHERE state IN ({US_STATE_LIST})
        GROUP BY state
        ORDER BY records DESC
    """,

    # ── 4b. Tier Summary ─────────────────────────────────────────────────────
    "tier_summary": f"""
        WITH state_counts AS (
            SELECT state, COUNT(*) AS n
            FROM read_parquet('{PARQUET}')
            WHERE state IN ({US_STATE_LIST})
            GROUP BY state
        )
        SELECT
            CASE WHEN n >= 50000 THEN 'A' WHEN n >= 10000 THEN 'B' ELSE 'C' END AS tier,
            COUNT(*) AS states_in_tier,
            SUM(n)   AS total_records,
            MIN(n)   AS min_records,
            MAX(n)   AS max_records
        FROM state_counts
        GROUP BY tier
        ORDER BY tier
    """,

    # ── 5. Data Quality Flags (US records) ───────────────────────────────────
    # All flags are rule-fixable (no LLM needed).
    # duplicate_records = count of records sharing a (name, state) pair with ≥1 other record.
    "quality_flags": f"""
        WITH us AS (
            SELECT * FROM read_parquet('{PARQUET}')
            WHERE state IN ({US_STATE_LIST})
        ),
        name_state_counts AS (
            SELECT LOWER(TRIM(name)) AS norm_name, state, COUNT(*) AS grp
            FROM us
            WHERE name IS NOT NULL AND state IS NOT NULL
            GROUP BY norm_name, state
        ),
        dup_records AS (
            SELECT SUM(grp) AS dup_total
            FROM name_state_counts
            WHERE grp > 1
        )
        SELECT
            COUNT(*)                                                        AS total_us,
            SUM(CASE WHEN website IS NOT NULL
                      AND NOT regexp_matches(website,
                          '^(https?://|www\\.)?.+\\..{{2,}}')  THEN 1 END) AS malformed_website,
            SUM(CASE WHEN founded < 1800
                      AND founded IS NOT NULL               THEN 1 END)    AS suspicious_founded,
            SUM(CASE WHEN founded > 2026
                      AND founded IS NOT NULL               THEN 1 END)    AS future_founded,
            SUM(CASE WHEN LENGTH(TRIM(name)) < 2
                      AND name IS NOT NULL                  THEN 1 END)    AS short_name,
            SUM(CASE WHEN city IS NULL AND state IS NOT NULL THEN 1 END)   AS missing_city,
            MAX(d.dup_total)                                                AS duplicate_records
        FROM us, dup_records d
    """,

    # ── 6. Candidate Key Analysis ─────────────────────────────────────────────
    # 6a: handle uniqueness
    "candidate_key_handle": f"""
        SELECT
            'handle'                                AS candidate_key,
            COUNT(*)                                AS total_us_records,
            COUNT(DISTINCT handle)                  AS distinct_values,
            COUNT(*) - COUNT(DISTINCT handle)       AS duplicates,
            ROUND(
                (COUNT(*) - COUNT(DISTINCT handle)) * 100.0 / COUNT(*), 4
            )                                       AS collision_rate_pct,
            SUM(CASE WHEN handle IS NULL THEN 1 END) AS nulls
        FROM read_parquet('{PARQUET}')
        WHERE state IN ({US_STATE_LIST})
    """,

    # 6b: name+state
    "candidate_key_name_state": f"""
        WITH us AS (
            SELECT * FROM read_parquet('{PARQUET}')
            WHERE state IN ({US_STATE_LIST})
        )
        SELECT
            'name + state'                                      AS candidate_key,
            COUNT(*)                                            AS total_us_records,
            COUNT(DISTINCT (LOWER(TRIM(name)), state))          AS distinct_values,
            COUNT(*) - COUNT(DISTINCT (LOWER(TRIM(name)), state)) AS duplicates,
            ROUND(
                (COUNT(*) - COUNT(DISTINCT (LOWER(TRIM(name)), state))) * 100.0 / COUNT(*), 4
            )                                                   AS collision_rate_pct,
            SUM(CASE WHEN name IS NULL OR state IS NULL THEN 1 END) AS nulls_in_key
        FROM us
    """,

    # 6c: name+domain (extract domain from website)
    # Caveat: records with NULL website contribute (name, NULL) pairs, which each count
    # as distinct — collision_rate_pct will be understated for states with high website missingness.
    # Interpret this key only for records that have a website value.
    "candidate_key_name_domain": f"""
        WITH us AS (
            SELECT
                name,
                website,
                -- strip scheme and www, keep hostname
                regexp_extract(
                    LOWER(COALESCE(website, '')),
                    '(?:https?://)?(?:www\\.)?([^/?#\\s]+)',
                    1
                ) AS domain
            FROM read_parquet('{PARQUET}')
            WHERE state IN ({US_STATE_LIST})
        )
        SELECT
            'name + domain'                                         AS candidate_key,
            COUNT(*)                                                AS total_us_records,
            COUNT(DISTINCT (LOWER(TRIM(name)), NULLIF(domain,''))) AS distinct_values,
            COUNT(*) - COUNT(DISTINCT (LOWER(TRIM(name)), NULLIF(domain,''))) AS duplicates,
            ROUND(
                (COUNT(*) - COUNT(DISTINCT (LOWER(TRIM(name)), NULLIF(domain,'')))) * 100.0 / COUNT(*), 4
            )                                                       AS collision_rate_pct,
            SUM(CASE WHEN name IS NULL OR website IS NULL THEN 1 END) AS nulls_in_key
        FROM us
    """,

    # 6d: show top duplicate (name+state) groups for spot-check
    "duplicate_spot_check": f"""
        SELECT
            LOWER(TRIM(name)) AS norm_name,
            state,
            COUNT(*) AS occurrences
        FROM read_parquet('{PARQUET}')
        WHERE state IN ({US_STATE_LIST})
          AND name IS NOT NULL
        GROUP BY norm_name, state
        HAVING COUNT(*) > 1
        ORDER BY occurrences DESC
        LIMIT 20
    """,
}


def run_all(parquet_path: str = PARQUET) -> dict:
    """Execute all baseline queries; returns dict of {query_name: DataFrame}."""
    if not Path(parquet_path).exists():
        raise FileNotFoundError(f"Parquet not found: {parquet_path}")

    con = duckdb.connect()
    results = {}

    for name, sql in QUERIES.items():
        log.info(f"Running: {name}")
        results[name] = con.execute(sql).df()

    con.close()
    return results


if __name__ == "__main__":
    results = run_all()
    for name, df in results.items():
        print(f"\n{'='*60}")
        print(f"  {name.upper().replace('_', ' ')}")
        print(f"{'='*60}")
        print(df.to_string(index=False))
