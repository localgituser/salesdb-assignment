# Database Reference: US Companies

This project uses a DuckDB database containing a single table named `us_companies`.

## Table Schema: `us_companies`

| Column Name | Data Type | Description / Notes |
| :--- | :--- | :--- |
| `handle` | VARCHAR | Unique identifier/slug for the company |
| `name` | VARCHAR | Full company name |
| `website` | VARCHAR | Company website URL |
| `industry` | VARCHAR | Industry classification |
| `size` | VARCHAR | Employee count range or sizing category |
| `type` | VARCHAR | Entity type (e.g., Public, Private) |
| `founded` | INT64 | Year the company was founded |
| `city` | VARCHAR | Headquarters city |
| `state` | VARCHAR | Headquarters state |
| `country_code` | VARCHAR | ISO country code (typically 'US') |

## Query Writing Rules
- Always query from the `us_companies` table.
- Use DuckDB-compliant SQL syntax.
- If performing text searches on `name` or `industry`, remember to use `ILIKE` for case-insensitive matching.