"""
Data ingestion module for loading 4.25M dataset into DuckDB and exporting to Parquet.
"""

import duckdb
import pandas as pd
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATASET_PATH = "data/raw/companies-2023-q4-sm.csv"
OUTPUT_PARQUET = "data/processed/us_companies.parquet"


def ingest_and_convert():
    """Load CSV into DuckDB, filter to US records, validate, and export to Parquet."""
    logger.info(f"Loading dataset from {DATASET_PATH}")

    # Create DuckDB connection
    conn = duckdb.connect()

    # Load CSV into DuckDB, filtering to US records only (WHERE country_code = 'US')
    logger.info("Reading CSV into DuckDB and filtering to US records...")
    conn.execute(f"""
        CREATE TABLE companies AS
        SELECT * FROM read_csv_auto('{DATASET_PATH}')
        WHERE country_code = 'US'
    """)
    
    # Get schema and record count
    schema = conn.execute("DESCRIBE companies").fetchall()
    record_count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    
    logger.info(f"✓ Loaded {record_count:,} records")
    logger.info(f"✓ Schema ({len(schema)} columns):")
    for col_name, col_type, *_ in schema:
        logger.info(f"  {col_name}: {col_type}")
    
    # Quick data quality check
    logger.info("Data quality snapshot:")
    quality_check = conn.execute("""
        SELECT 
            COUNT(*) as total_records,
            COUNT(DISTINCT state) as distinct_states,
            COUNT(DISTINCT industry) as distinct_industries,
            COUNT(CASE WHEN state IS NOT NULL THEN 1 END) as non_null_state,
            COUNT(CASE WHEN name IS NOT NULL THEN 1 END) as non_null_name,
            COUNT(CASE WHEN website IS NOT NULL THEN 1 END) as non_null_website
        FROM companies
    """).fetchone()
    
    total, states, industries, nn_state, nn_name, nn_website = quality_check
    logger.info(f"  Total records: {total:,}")
    logger.info(f"  Distinct states: {states}")
    logger.info(f"  Distinct industries: {industries}")
    logger.info(f"  Non-null state: {nn_state:,} ({100*nn_state/total:.1f}%)")
    logger.info(f"  Non-null name: {nn_name:,} ({100*nn_name/total:.1f}%)")
    logger.info(f"  Non-null website: {nn_website:,} ({100*nn_website/total:.1f}%)")
    
    # Export to Parquet
    logger.info(f"Exporting to Parquet: {OUTPUT_PARQUET}")
    Path(OUTPUT_PARQUET).parent.mkdir(parents=True, exist_ok=True)
    conn.execute(f"COPY companies TO '{OUTPUT_PARQUET}' (FORMAT PARQUET)")
    
    logger.info(f"✓ Parquet export complete")
    conn.close()
    
    return OUTPUT_PARQUET


if __name__ == "__main__":
    ingest_and_convert()
