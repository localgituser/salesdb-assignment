# Part 0: Baseline Audit & Data Sanity Check

## Executive Summary

**Dataset**: BigPicture Company Dataset (17.15M records)  
**Coverage**: Global (not US-only as initially assumed)  
**Key Finding**: Critical mismatch with brief's regional US focus

---

## Critical Data Mismatch

### What We Have
- **17.15M total records** across 139,887 distinct "state" values
- **Top 5 regions by count**: England (719K), California (619K), Texas (351K), São Paulo (240K), Maharashtra (206K)
- **Geographic mix**: ~45% global (non-US) companies, ~55% appear to be US-based

### What the Brief Expected
- Regional audit for US-based market coverage  
- Comparable to Census CBP state/industry establishment counts  
- Stratification by US state

### Impact
The dataset is **global by default**. For Part 1+ work to be valid against a US-focused audit, we must:
1. **Filter to US records only** (using state names matching known US states/territories)
2. Re-baseline against US-only counts
3. If applying Census CBP comparator, compare US subset only

---

## Data Quality Snapshot

| Metric | Value | Note |
|--------|-------|------|
| Total records | 17.15M | Includes non-US |
| Distinct "states" | 39,887 | Regions/provinces from 150+ countries |
| Name field fill rate | 100% | ✓ High quality |
| Website field fill rate | 79.5% | Good for enrichment |
| State field fill rate | 71.1% | ~4.96M missing |
| **Estimated US records** | ~9.4M | Rough estimate (TBD after filtering) |

---

## Data Dictionary

| Column | Type | Notes |
|--------|------|-------|
| handle | VARCHAR | Unique identifier |
| name | VARCHAR | Company name (100% populated) |
| website | VARCHAR | Domain/website URL |
| industry | VARCHAR | NAICS-ish or custom taxonomy |
| size | VARCHAR | Bracket: "1-10", "11-50", "51-200", etc. |
| type | VARCHAR | Company type classification |
| founded | BIGINT | Foundation year (timestamp or year) |
| city | VARCHAR | City name |
| state | VARCHAR | State, region, or province |
| country_code | VARCHAR | ISO country code (if populated) |

---

## Industry Distribution (All Records)

Top 10 industries:
1. Construction (683K)
2. IT Services & Consulting (651K)
3. Advertising Services (617K)
4. Business Consulting & Services (508K)
5. Real Estate (471K)
6. Retail (436K)
7. Software Development (406K)
8. Financial Services (356K)
9. Hospitals & Healthcare (303K)
10. Technology, Information & Internet (297K)

**Note**: Industry taxonomies may differ from Census NAICS. Recommend manual audit of top 5 for alignment.

---

## Comparator Strategy

### What We're Using
- **SUSB 2022** (Statistics of U.S. Businesses): employer firms with ≥1 W-2 employee, ~6.5M entities nationally — primary benchmark for company-level coverage
- **NES 2023** (Nonemployer Statistics): sole proprietors and self-employed with no paid employees, ~30.4M entities — captures gig economy and trades operators that SUSB misses
- Combined SUSB + NES denominator: ~36.9M total business universe

### Why Not Census CBP
Census County Business Patterns (CBP) counts **physical establishment locations**, not legal companies. A company with 50 branch offices appears as 50 CBP records but 1 SUSB record. For a company-level dataset audit, CBP would systematically overstate the true universe and make coverage ratios meaningless. SUSB + NES are the correct denominators.

### Gap Tiers (Final)
- **HIGH_GAP** < 10% coverage vs. combined SUSB+NES universe
- **MODERATE_GAP** 10–30%
- **ADEQUATE** > 30%

---

## Next Steps (Part 1)

1. **Filter to US records** (state IN known_us_states or country_code = 'US')
2. **Stratify by state/industry/size** → compute record counts and fill rates
3. **Tier states** A (≥100 records), B (30-99), C (<30)
4. **Document rules vs. LLM split** in enrichment strategy
5. **Output**: `part1_sample_audit.parquet` with aggregated stats

**Budget used so far**: $0  
**Status**: ✓ On track

---

## Observations for Future Work

1. **Global data is a feature, not a bug** — if the pod pivots to international expansion, this becomes an asset
2. **State field encoding** is messy (full names, abbreviations, special chars mix) — Part 1 sampling will surface patterns
3. **Website field** is high-fill (79.5%) and could be leverage for enrichment/verification
4. **Size distribution** is heavily skewed to 1-10 person companies (48.7% of records) — may affect industry comparators

---

## SUSB State Coverage Gap Analysis

_Generated: 2026-06-12 06:29 UTC | Source: US Census SUSB 2022 (`us_state_6digitnaics_2022.csv`) vs `part0_companies.parquet`_

Across 51 states mapped to SUSB: 0 HIGH_GAP (<10% coverage), 0 MODERATE_GAP (10–30%), 51 ADEQUATE (>30%). No Tier A states are in HIGH_GAP. **Limitations**: SUSB counts legal firms (may be multi-establishment); our data counts records (may include duplicates). Ratios are directional signals, not precise deficits. SUSB vintage is 2022; our dataset vintage may differ.

| State | Our Records | SUSB Firms | Coverage % | Gap Tier | Sampling Tier |
|-------|-------------|------------|------------|----------|---------------|
| Montana | 12,685 | 36,155 | 35.1% | ADEQUATE | B |
| South Dakota | 8,534 | 23,788 | 35.9% | ADEQUATE | C |
| North Dakota | 7,517 | 20,090 | 37.4% | ADEQUATE | C |
| Mississippi | 17,301 | 45,506 | 38.0% | ADEQUATE | B |
| Idaho | 19,650 | 48,405 | 40.6% | ADEQUATE | B |
| West Virginia | 10,569 | 25,765 | 41.0% | ADEQUATE | B |
| Arkansas | 23,429 | 53,111 | 44.1% | ADEQUATE | B |
| Nebraska | 20,478 | 45,116 | 45.4% | ADEQUATE | B |
| Kentucky | 32,080 | 68,553 | 46.8% | ADEQUATE | B |
| Oklahoma | 35,484 | 74,866 | 47.4% | ADEQUATE | B |
| Maine | 16,889 | 35,533 | 47.5% | ADEQUATE | B |
| Louisiana | 39,837 | 83,440 | 47.7% | ADEQUATE | B |
| Iowa | 31,249 | 63,956 | 48.9% | ADEQUATE | B |
| South Carolina | 45,982 | 93,372 | 49.2% | ADEQUATE | B |
| Alabama | 39,190 | 78,228 | 50.1% | ADEQUATE | B |
| New Mexico | 17,978 | 35,284 | 51.0% | ADEQUATE | B |
| Alaska | 9,245 | 18,047 | 51.2% | ADEQUATE | C |
| Missouri | 64,537 | 117,985 | 54.7% | ADEQUATE | A |
| Kansas | 32,199 | 58,771 | 54.8% | ADEQUATE | B |
| Utah | 44,321 | 79,175 | 56.0% | ADEQUATE | B |
| Rhode Island | 14,198 | 25,033 | 56.7% | ADEQUATE | B |
| Wyoming | 11,424 | 20,059 | 57.0% | ADEQUATE | B |
| Vermont | 10,225 | 17,855 | 57.3% | ADEQUATE | B |
| North Carolina | 115,134 | 197,185 | 58.4% | ADEQUATE | A |
| Florida | 306,228 | 523,095 | 58.5% | ADEQUATE | A |
| Hawaii | 15,106 | 25,794 | 58.6% | ADEQUATE | B |
| Indiana | 67,249 | 114,309 | 58.8% | ADEQUATE | A |
| Pennsylvania | 141,916 | 234,852 | 60.4% | ADEQUATE | A |
| Wisconsin | 67,453 | 110,613 | 61.0% | ADEQUATE | A |
| Michigan | 108,881 | 177,240 | 61.4% | ADEQUATE | A |
| Nevada | 38,056 | 61,623 | 61.8% | ADEQUATE | B |
| Minnesota | 75,049 | 121,160 | 61.9% | ADEQUATE | A |
| New Jersey | 124,155 | 198,448 | 62.6% | ADEQUATE | A |
| Maryland | 71,005 | 113,492 | 62.6% | ADEQUATE | A |
| Oregon | 62,334 | 99,548 | 62.6% | ADEQUATE | A |
| Virginia | 101,700 | 161,687 | 62.9% | ADEQUATE | A |
| Washington | 104,783 | 165,410 | 63.3% | ADEQUATE | A |
| Illinois | 165,346 | 258,353 | 64.0% | ADEQUATE | A |
| New Hampshire | 20,572 | 31,920 | 64.4% | ADEQUATE | B |
| Arizona | 80,683 | 125,051 | 64.5% | ADEQUATE | A |
| Georgia | 133,221 | 204,057 | 65.3% | ADEQUATE | A |
| Tennessee | 72,102 | 107,606 | 67.0% | ADEQUATE | A |
| New York | 309,011 | 460,514 | 67.1% | ADEQUATE | A |
| Ohio | 127,174 | 187,289 | 67.9% | ADEQUATE | A |
| Connecticut | 48,191 | 70,809 | 68.1% | ADEQUATE | B |
| Texas | 351,297 | 500,456 | 70.2% | ADEQUATE | A |
| Colorado | 105,915 | 150,626 | 70.3% | ADEQUATE | A |
| California | 619,440 | 844,605 | 73.3% | ADEQUATE | A |
| Delaware | 20,061 | 24,245 | 82.7% | ADEQUATE | B |
| Massachusetts | 129,657 | 147,493 | 87.9% | ADEQUATE | A |
| District of Columbia | 17,054 | 19,045 | 89.5% | ADEQUATE | B |

---

## SUSB Industry Coverage Gap Analysis

_Generated: 2026-06-12 06:42 UTC | Source: SUSB 2022 national totals vs `part0_companies.parquet` | Model: claude-haiku-4-5-20251001_

244 industry labels (≥500 records each) mapped to 20 NAICS sectors via Claude Haiku ($0.01208). Coverage: 0 HIGH_GAP (<10%), 5 MODERATE_GAP (10–30%), 15 ADEQUATE (>30%). No sectors in HIGH_GAP. **Limitations**: Mapping is LLM-generated and approximate; labels with ambiguous industry scope may be misclassified. Records with null or rare industry labels (<500) are counted under NAICS 99 (unclassified). SUSB national totals use State='00' aggregate (not sum of states). Our dataset may contain duplicate records inflating coverage ratios.

| NAICS | Sector | Our Records | SUSB Firms | Coverage % | Gap Tier |
|-------|--------|-------------|------------|------------|----------|
| 81 | Other Services (except Public Administration) | 89,652 | 729,236 | 12.3% | MODERATE_GAP |
| 42 | Wholesale Trade | 51,703 | 277,932 | 18.6% | MODERATE_GAP |
| 44-45 | Retail Trade | 170,759 | 645,404 | 26.5% | MODERATE_GAP |
| 72 | Accommodation and Food Services | 160,435 | 574,723 | 27.9% | MODERATE_GAP |
| 23 | Construction | 220,721 | 782,487 | 28.2% | MODERATE_GAP |
| 56 | Administrative and Support and Waste Management | 116,607 | 376,192 | 31.0% | ADEQUATE |
| 55 | Management of Companies and Enterprises | 8,361 | 25,413 | 32.9% | ADEQUATE |
| 48-49 | Transportation and Warehousing | 86,647 | 237,527 | 36.5% | ADEQUATE |
| 53 | Real Estate and Rental and Leasing | 157,772 | 366,557 | 43.0% | ADEQUATE |
| 62 | Health Care and Social Assistance | 338,933 | 693,801 | 48.9% | ADEQUATE |
| 52 | Finance and Insurance | 215,724 | 244,536 | 88.2% | ADEQUATE |
| 54 | Professional, Scientific, and Technical Services | 774,174 | 872,305 | 88.8% | ADEQUATE |
| 11 | Agriculture, Forestry, Fishing and Hunting | 20,886 | 22,599 | 92.4% | ADEQUATE |
| 61 | Educational Services | 149,177 | 103,287 | 144.4% | ADEQUATE |
| 31-33 | Manufacturing | 403,907 | 239,265 | 168.8% | ADEQUATE |
| 71 | Arts, Entertainment, and Recreation | 283,929 | 148,290 | 191.5% | ADEQUATE |
| 22 | Utilities | 15,175 | 6,772 | 224.1% | ADEQUATE |
| 21 | Mining, Quarrying, and Oil and Gas Extraction | 40,480 | 17,341 | 233.4% | ADEQUATE |
| 51 | Information | 339,232 | 89,332 | 379.7% | ADEQUATE |
| 99 | Industries not classified | 564,669 | 8,498 | 6644.7% | ADEQUATE |

---

## SUSB + NES Combined Industry Coverage Gap Analysis

_Generated: 2026-06-12 07:01 UTC | Sources: SUSB 2022 + NES 2023 national totals vs `part0_companies.parquet`_

Combined SUSB 2022 employer firms + NES 2023 non-employer establishments as universe denominator. Coverage: 8 HIGH_GAP (<10%), 6 MODERATE_GAP (10–30%), 6 ADEQUATE (>30%). Sectors that were over-indexed vs. SUSB alone, now adjusted: Educational Services (144.4% → 15.0%); Arts, Entertainment, and Recreation (191.5% → 15.1%); Mining, Quarrying, and Oil and Gas Extraction (233.4% → 46.3%); Utilities (224.1% → 60.9%); Manufacturing (168.8% → 62.5%); Information (379.7% → 69.4%); Industries not classified (6644.7% → 6644.7%). **Limitations**: SUSB 2022 and NES 2023 are different vintages — directional only. NES counts legal establishments; our dataset may count individual practitioners. Management of Companies (NAICS 55) and Unclassified (99) have no NES equivalent — ratios for those sectors are unchanged from SUSB-only comparison.

| NAICS | Sector | Our Records | SUSB Firms | NES Non-Emp | Combined | SUSB-Only % | Combined % | Gap Tier |
|-------|--------|-------------|------------|-------------|----------|-------------|------------|----------|
| 48-49 | Transportation and Warehousing | 86,647 | 237,527 | 4,057,121 | 4,294,648 | 36.5% | 2.0% | HIGH_GAP |
| 81 | Other Services (except Public Administration) | 89,652 | 729,236 | 3,206,392 | 3,935,628 | 12.3% | 2.3% | HIGH_GAP |
| 56 | Administrative and Support and Waste Management | 116,607 | 376,192 | 2,905,446 | 3,281,638 | 31.0% | 3.6% | HIGH_GAP |
| 53 | Real Estate and Rental and Leasing | 157,772 | 366,557 | 3,170,531 | 3,537,088 | 43.0% | 4.5% | HIGH_GAP |
| 23 | Construction | 220,721 | 782,487 | 2,917,631 | 3,700,118 | 28.2% | 6.0% | HIGH_GAP |
| 44-45 | Retail Trade | 170,759 | 645,404 | 2,081,566 | 2,726,970 | 26.5% | 6.3% | HIGH_GAP |
| 42 | Wholesale Trade | 51,703 | 277,932 | 458,466 | 736,398 | 18.6% | 7.0% | HIGH_GAP |
| 11 | Agriculture, Forestry, Fishing and Hunting | 20,886 | 22,599 | 255,717 | 278,316 | 92.4% | 7.5% | HIGH_GAP |
| 62 | Health Care and Social Assistance | 338,933 | 693,801 | 2,303,883 | 2,997,684 | 48.9% | 11.3% | MODERATE_GAP |
| 72 | Accommodation and Food Services | 160,435 | 574,723 | 664,264 | 1,238,987 | 27.9% | 12.9% | MODERATE_GAP |
| 61 | Educational Services | 149,177 | 103,287 | 893,520 | 996,807 | 144.4% | 15.0% | MODERATE_GAP |
| 71 | Arts, Entertainment, and Recreation | 283,929 | 148,290 | 1,737,630 | 1,885,920 | 191.5% | 15.1% | MODERATE_GAP |
| 54 | Professional, Scientific, and Technical Services | 774,174 | 872,305 | 4,075,717 | 4,948,022 | 88.8% | 15.6% | MODERATE_GAP |
| 52 | Finance and Insurance | 215,724 | 244,536 | 805,567 | 1,050,103 | 88.2% | 20.5% | MODERATE_GAP |
| 55 | Management of Companies and Enterprises | 8,361 | 25,413 | 0 | 25,413 | 32.9% | 32.9% | ADEQUATE |
| 21 | Mining, Quarrying, and Oil and Gas Extraction | 40,480 | 17,341 | 70,159 | 87,500 | 233.4% | 46.3% | ADEQUATE |
| 22 | Utilities | 15,175 | 6,772 | 18,147 | 24,919 | 224.1% | 60.9% | ADEQUATE |
| 31-33 | Manufacturing | 403,907 | 239,265 | 406,575 | 645,840 | 168.8% | 62.5% | ADEQUATE |
| 51 | Information | 339,232 | 89,332 | 399,440 | 488,772 | 379.7% | 69.4% | ADEQUATE |
| 99 | Industries not classified | 564,669 | 8,498 | 0 | 8,498 | 6644.7% | 6644.7% | ADEQUATE |
