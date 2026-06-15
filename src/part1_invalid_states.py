"""
Analyze medium-to-large companies (50+ employees) with invalid or null state values.
Helps decide whether cleaning up these records is worth the effort.

Total dataset: ~4.25M records
Known non-US records: ~44,880
Known null-state records: ~97,912
"""

import duckdb
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

PARQUET = "data/processed/part0_companies.parquet"

VALID_STATES = [
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

STATE_LIST = ", ".join(f"'{s}'" for s in VALID_STATES)

TOTAL_RECORDS = 4_306_855
MED_LARGE_SIZES = "('51-200', '201-500', '1K-5K', '5K-10K', '10K+')"

SQL_COVERAGE = f"""
SELECT
    COUNT(*)                                                              AS total_raw,
    SUM(CASE WHEN state IN ({STATE_LIST})          THEN 1 END)           AS valid_state,
    SUM(CASE WHEN state IS NULL                    THEN 1 END)           AS null_state,
    SUM(CASE WHEN state IS NOT NULL
              AND state NOT IN ({STATE_LIST})       THEN 1 END)          AS invalid_state,
    ROUND(SUM(CASE WHEN state IS NULL OR
                        (state IS NOT NULL AND state NOT IN ({STATE_LIST}))
                   THEN 1 END) * 100.0 / COUNT(*), 3)                   AS pct_excluded
FROM read_parquet('{PARQUET}')
"""

SQL_PER_TIER = f"""
WITH med_large AS (
    SELECT
        size,
        (state IS NULL
         OR (state IS NOT NULL AND state NOT IN ({STATE_LIST}))) AS bad_state
    FROM read_parquet('{PARQUET}')
    WHERE size IN {MED_LARGE_SIZES}
),
per_tier AS (
    SELECT
        size,
        COUNT(*)                                          AS total_in_size_tier,
        SUM(bad_state::INT)                               AS excluded_count,
        ROUND(SUM(bad_state::INT) * 100.0 / COUNT(*), 3) AS pct_of_size_tier,
        CASE size
            WHEN '51-200'  THEN 1
            WHEN '201-500' THEN 2
            WHEN '1K-5K'   THEN 3
            WHEN '5K-10K'  THEN 4
            WHEN '10K+'    THEN 5
        END AS sort_key
    FROM med_large
    GROUP BY size

    UNION ALL

    SELECT
        'TOTAL (51+)',
        COUNT(*),
        SUM(bad_state::INT),
        ROUND(SUM(bad_state::INT) * 100.0 / COUNT(*), 3),
        6
    FROM med_large
)
SELECT size, total_in_size_tier, excluded_count, pct_of_size_tier
FROM per_tier
ORDER BY sort_key
"""

SQL_SAMPLE_INVALID = f"""
SELECT state, COUNT(*) AS records
FROM read_parquet('{PARQUET}')
WHERE state IS NOT NULL
  AND state NOT IN ({STATE_LIST})
GROUP BY state
ORDER BY records DESC
LIMIT 15
"""


def main():
    if not Path(PARQUET).exists():
        raise FileNotFoundError(f"Parquet not found: {PARQUET}")

    con = duckdb.connect()

    log.info("=" * 60)
    log.info("  OVERALL COVERAGE (null + invalid state)")
    log.info("=" * 60)
    df_cov = con.execute(SQL_COVERAGE).df()
    print(df_cov.to_string(index=False))

    excluded = int(df_cov["null_state"].iloc[0]) + int(df_cov["invalid_state"].iloc[0])
    pct = excluded / TOTAL_RECORDS * 100
    log.info(f"\n  → {excluded:,} records excluded ({pct:.2f}% of {TOTAL_RECORDS:,} total)")

    log.info("\n" + "=" * 60)
    log.info("  MEDIUM-TO-LARGE COMPANIES — excluded by size tier")
    log.info("  (null OR invalid state, size >= 51 employees)")
    log.info("=" * 60)
    df_tier = con.execute(SQL_PER_TIER).df()
    print(df_tier.to_string(index=False))

    total_row = df_tier[df_tier["size"] == "TOTAL (51+)"]
    if not total_row.empty:
        pct_total = float(total_row["pct_of_size_tier"].iloc[0])
        excl = int(total_row["excluded_count"].iloc[0])
        tier_total = int(total_row["total_in_size_tier"].iloc[0])
        log.info(f"\n  → {excl:,} of {tier_total:,} mid-to-large records excluded ({pct_total:.3f}%)")
        if pct_total < 1.0:
            log.info("  ✓ Safe to deprioritize: excluded records are <1% of mid-to-large universe.")
        else:
            log.info("  ✗ Non-trivial exclusion: consider rescuing these records.")

    log.info("\n" + "=" * 60)
    log.info("  TOP INVALID STATE VALUES (non-null, non-US)")
    log.info("=" * 60)
    df_sample = con.execute(SQL_SAMPLE_INVALID).df()
    print(df_sample.to_string(index=False))

    con.close()


if __name__ == "__main__":
    main()
