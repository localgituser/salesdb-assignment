"""Sanity check script for dataset."""
import duckdb
import pandas as pd

conn = duckdb.connect()
conn.execute("CREATE TABLE companies AS SELECT * FROM read_parquet('data/processed/us_companies.parquet')")

# Check state distribution
print("=" * 60)
print("STATE DISTRIBUTION")
print("=" * 60)
states_df = conn.execute("""
    SELECT state, COUNT(*) as count
    FROM companies
    WHERE state IS NOT NULL
    GROUP BY state
    ORDER BY count DESC
    LIMIT 20
""").fetch_df()

print("\nTop 20 states by record count:")
print(states_df.to_string(index=False))

# Check total distinct states
all_states = conn.execute("""
    SELECT COUNT(DISTINCT state) as count FROM companies WHERE state IS NOT NULL
""").fetchone()

print(f"\n⚠ Total distinct state values: {all_states[0]:,}")
print("   (Expected: ~50 US states/territories, found way more)")

# Industry distribution
print("\n" + "=" * 60)
print("INDUSTRY DISTRIBUTION")
print("=" * 60)
industries = conn.execute("""
    SELECT industry, COUNT(*) as count
    FROM companies
    WHERE industry IS NOT NULL
    GROUP BY industry
    ORDER BY count DESC
    LIMIT 15
""").fetch_df()

print("\nTop 15 industries:")
print(industries.to_string(index=False))

# Size distribution
print("\n" + "=" * 60)
print("SIZE DISTRIBUTION")
print("=" * 60)
sizes = conn.execute("""
    SELECT size, COUNT(*) as count
    FROM companies
    WHERE size IS NOT NULL
    GROUP BY size
    ORDER BY count DESC
""").fetch_df()

print("\nCompany sizes:")
print(sizes.to_string(index=False))

# Website format sample
print("\n" + "=" * 60)
print("SAMPLE WEBSITE FORMATS")
print("=" * 60)
websites = conn.execute("""
    SELECT DISTINCT website
    FROM companies
    WHERE website IS NOT NULL
    LIMIT 10
""").fetch_df()

print("\nSample websites:")
for i, row in websites.iterrows():
    print(f"  {row['website']}")
