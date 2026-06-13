"""
Phase 4 PoC enrichment sample builder.

Builds data/processed/sample_audit.parquet — a 300-record stratified sample
across enterprise / mid-market / SMB / micro size bands, with each band
split across the three enrichment-target conditions:
  - missing website
  - missing industry
  - website set to a platform/social/builder URL (effectively NULL)

Excludes (pre-filter, not deferral):
  - size IS NULL records
  - HIGH_CHURN_RISK strict flag (size=1-10 AND founded>=2015
    AND website IS NULL AND type IS NULL)

Run: python src/sampling.py
"""

import logging
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

INPUT_PARQUET = "data/processed/us_companies.parquet"
OUTPUT_PARQUET = "data/processed/sample_audit.parquet"
SEED = 42

SEGMENT_QUOTAS = {
    "enterprise": 60,   # 500+ employees
    "mid_market": 80,   # 51-500
    "smb": 80,          # 11-50
    "micro": 80,        # 1-10, excluding HIGH_CHURN_RISK
}

# Within each segment: missing_website / missing_industry / platform_url
CONDITION_SPLIT = {
    "missing_website": 0.50,
    "missing_industry": 0.30,
    "platform_url": 0.20,
}

# Treat these as effectively NULL websites (per CLAUDE.md platform blocklist).
PLATFORM_HOSTS = [
    "yelp.com", "facebook.com", "instagram.com", "linkedin.com", "twitter.com",
    "linktr.ee", "bit.ly", "wixsite.com", "weebly.com", "wordpress.com",
    "squarespace.com", "google.com", "amazon.com", "youtube.com",
]

SEGMENT_PREDICATE = {
    "enterprise": "size IN ('501-1K','1K-5K','5K-10K','10K+')",
    "mid_market": "size IN ('51-200','201-500')",
    "smb": "size = '11-50'",
    "micro": (
        "size = '1-10' "
        "AND NOT (founded >= 2015 AND website IS NULL AND type IS NULL)"
    ),
}


def _platform_predicate(col: str = "website") -> str:
    """SQL: true if `col` is non-null AND contains any platform host substring."""
    ors = " OR ".join(f"lower({col}) LIKE '%{h}%'" for h in PLATFORM_HOSTS)
    tld = (
        f"lower({col}) LIKE '%.edu%' OR "
        f"lower({col}) LIKE '%.gov%' OR "
        f"lower({col}) LIKE '%.mil%'"
    )
    return f"({col} IS NOT NULL AND ({ors} OR {tld}))"


def _condition_predicate(condition: str) -> str:
    platform = _platform_predicate()
    if condition == "missing_website":
        return f"(website IS NULL AND NOT {platform})"
    if condition == "missing_industry":
        return "industry IS NULL"
    if condition == "platform_url":
        return platform
    raise ValueError(condition)


def _quota_for(segment: str, condition: str) -> int:
    return round(SEGMENT_QUOTAS[segment] * CONDITION_SPLIT[condition])


def build_sample(con: duckdb.DuckDBPyConnection) -> None:
    parts = []
    for segment, seg_pred in SEGMENT_PREDICATE.items():
        for condition in CONDITION_SPLIT:
            n = _quota_for(segment, condition)
            cond_pred = _condition_predicate(condition)
            q = f"""
                SELECT
                    handle, name, website, industry, size, type, founded,
                    city, state, country_code,
                    '{segment}' AS poc_segment,
                    '{condition}' AS poc_condition
                FROM '{INPUT_PARQUET}'
                WHERE state IS NOT NULL
                  AND ({seg_pred})
                  AND ({cond_pred})
                ORDER BY hash(handle || '{SEED}')
                LIMIT {n}
            """
            df = con.execute(q).fetchdf()
            logger.info(
                "segment=%-10s condition=%-17s requested=%d got=%d",
                segment, condition, n, len(df),
            )
            parts.append(df)

    import pandas as pd
    sample = pd.concat(parts, ignore_index=True)
    sample = sample.drop_duplicates(subset=["handle"], keep="first")

    Path(OUTPUT_PARQUET).parent.mkdir(parents=True, exist_ok=True)
    con.register("sample_df", sample)
    con.execute(f"COPY sample_df TO '{OUTPUT_PARQUET}' (FORMAT PARQUET)")

    logger.info("wrote %s (%d unique records)", OUTPUT_PARQUET, len(sample))
    logger.info(
        "segment breakdown:\n%s",
        sample.groupby(["poc_segment", "poc_condition"]).size().to_string(),
    )


if __name__ == "__main__":
    con = duckdb.connect()
    build_sample(con)
