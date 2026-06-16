# Part 2 — Agentic Coverage & Quality Audit Findings
_Generated: 2026-06-15 02:17 UTC_
_Models: claude-haiku-4-5-20251001 (sector ranking) + claude-sonnet-4-6 (synthesis)_
_Prompt versions: audit_v1 / audit_synthesis_v1_
_Part 2 LLM cost: $0.3653_
_Spot-check: n=15 per gap, pure SQL, no LLM_

---

## Agent Findings (data-engineer)

### Sector Ranking Summary (Haiku)

| Rank | Sector | Coverage% | Priority | Commercial Relevance | Confidence |
|---|---|---|---|---|---|
| 1 | Transportation and Warehousing | 1.99% | HIGH | 5/5 | 0.92 |
| 2 | Construction | 5.93% | HIGH | 5/5 | 0.90 |
| 3 | Administrative and Support and Waste Management | 3.51% | HIGH | 4/5 | 0.85 |
| 4 | Retail Trade | 6.19% | HIGH | 4/5 | 0.87 |
| 5 | Other Services (except Public Administration) | 2.25% | HIGH | 3/5 | 0.78 |
| 6 | Accommodation and Food Services | 12.8% | MEDIUM | 4/5 | 0.83 |
| 7 | Wholesale Trade | 6.68% | MEDIUM | 4/5 | 0.81 |
| 8 | Management of Companies and Enterprises | 26.31% | MEDIUM | 5/5 | 0.88 |
| 9 | Manufacturing | 60.54% | LOW | 5/5 | 0.95 |
| 10 | Utilities | 57.87% | LOW | 4/5 | 0.93 |

**Audit notes**: Five actionable sectors (48-49, 23, 56, 44-45, 81) have genuine employer-firm gaps underneath NES inflation; all four are recoverable via public registries (DOT, licensing, real estate, associations) with 0.85–0.92 confidence. The size-unknown segment (188K records, 46.8% industry fill) and micro-firm website gaps (especially restaurants and trucking) represent the highest-density enrichment opportunities independent of sector selection.


### Top 5 Structural Gaps (Sonnet Synthesis)

#### Gap 1: Transportation and Warehousing is covered at just 1.99% overall and shows HIGH_GAP status across all 48 measured states including major logistics markets California (10,385 records, 1.87%), Texas (8,288 records, 1.89%), and Florida (8,088 records, 1.76%), leaving the platform nearly blind in a sector where freight and 3PL buyers actively source carriers.

**NAICS**: 48-49 — Transportation and Warehousing
**Prevalence**: 1.99% overall coverage; all 48 measured states rated HIGH_GAP; largest Tier A states range from 1.32% (Maryland) to 3.25% (Wisconsin); 34.5% coverage vs. SUSB employer firms
**Root cause**: NES inflation driven by gig workers and sole-operator drivers structurally depresses the coverage denominator, but a real employer-firm gap also exists at 34.5% vs. SUSB — the recoverable portion sits in FMCSA carrier registries and state DOT databases that have not been systematically ingested.
**Commercial impact**: Outbound AEs selling freight tech, fuel cards, and fleet services to trucking operators and 3PLs cannot build viable prospect lists from current inventory; churn risk is elevated for customers who buy transportation-sector lists and receive thin, low-confidence results.
**Enrichment approach**: Ingest FMCSA Motor Carrier database and state DOT carrier registries to surface employer-level trucking and warehousing firms not currently in the platform.
**Agent confidence**: 0.88 — FMCSA and DOT registries are public and well-structured, but the 94% NES share means a portion of the headline gap is structural and unrecoverable, limiting the ceiling on enrichment yield.
**Verifier verdict**: ✓ CONFIRMED — NES inflates comparator (94% non-employers) but employer-firm coverage vs. SUSB is only 34.5% — real sourcing gap confirmed.

#### Gap 2: Construction coverage sits at just 5.93% overall and is rated HIGH_GAP in all 48 measured states — including the four largest construction markets California (25,900 records, 8.05%), Texas (20,796 records, 4.82%), Florida (16,640 records, 4.55%), and New York (12,130 records, 6.29%) — creating a systemic blind spot in a high-velocity B2B vertical where GCs and subs procure equipment, materials, and services at scale.

**NAICS**: 23 — Construction
**Prevalence**: 5.93% overall coverage; all 48 measured states rated HIGH_GAP; coverage ranges from 2.8% (Mississippi) to 9.97% (Washington); 28.0% coverage vs. SUSB employer firms
**Root cause**: Construction firms are heavily licensed at the state level but are fragmented across thousands of local licensing boards and permitting databases that require state-by-state ingestion; the platform has not systematically tapped these public registries, leaving the majority of employer-level contractors unrepresented.
**Commercial impact**: AEs selling construction tech, equipment financing, and material supply solutions to GCs and specialty subcontractors face near-universal territory gaps; customers building contractor prospecting lists in any state will encounter sub-10% coverage, driving list fatigue and churn.
**Enrichment approach**: Prioritize state contractor licensing boards and building permit databases in the top 10 construction-volume states, supplemented by AGC and regional GC directory crawls, to surface employer-level firms.
**Agent confidence**: 0.90 — State licensing data is granular and public with high employer-firm signal, but the 48-state uniformity of the gap indicates the effort is broad rather than targeted, and ingestion timelines will vary by state licensing board API availability.
**Verifier verdict**: ✓ CONFIRMED — NES inflates comparator (79% non-employers) but employer-firm coverage vs. SUSB is only 28.0% — real sourcing gap confirmed.

#### Gap 3: Retail Trade is covered at only 6.19% overall and is rated HIGH_GAP in all 48 measured states, with major retail markets including California (27,262 records, 9.29%), New York (16,716 records, 9.75%), Texas (12,889 records, 4.97%), and Florida (11,817 records, 5.23%) each falling well below 10% coverage, undermining the platform's value for any sales motion targeting retail SMBs.

**NAICS**: 44-45 — Retail Trade
**Prevalence**: 6.19% overall coverage; all 48 measured states rated HIGH_GAP; coverage ranges from 2.93% (Mississippi) to 9.75% (New York); 25.5% coverage vs. SUSB employer firms
**Root cause**: NES inflation is significant at 75.7% for retail, but the employer-firm gap at 25.5% vs. SUSB is real and recoverable; franchise registries and state retail licensing databases — which are public and granular — have not been systematically ingested, leaving independent retailers and franchisees absent from the platform.
**Commercial impact**: Outbound AEs targeting retail SMBs for POS systems, supply chain software, and staffing solutions cannot identify the majority of their addressable market; independent retailers and franchisees are the dominant deal motion in the segment and are disproportionately missing.
**Enrichment approach**: Ingest franchise disclosure registries, state retail licensing records, and commercial real estate databases to identify employer-level retail locations and chains not currently represented.
**Agent confidence**: 0.87 — Franchise and licensing data provide good employer-firm signal, but the high NES share (75.7%) means a substantial fraction of the headline gap reflects non-employer sole proprietors that are not actionable B2B targets, requiring careful filtering post-ingestion.
**Verifier verdict**: ✓ CONFIRMED — NES inflates comparator (76% non-employers) but employer-firm coverage vs. SUSB is only 25.5% — real sourcing gap confirmed.

#### Gap 4: Enterprise firms with 500 or more employees represent only 1.65% of platform records (69,109 companies) despite being the dominant segment by B2B revenue value, creating a sourcing volume gap that is invisible to fill-rate metrics because the records that exist are adequately enriched at 80.9% website fill.

**NAICS**: None — None
**Prevalence**: 1.65% of total records (69,109 enterprise firms); website fill at 80.9% masks the volume gap; enterprise segment is the smallest of all five size bands by record count
**Root cause**: Enterprise firms are numerically rare relative to SMBs but disproportionately valuable; the platform's sourcing pipelines appear calibrated toward high-volume SMB ingestion, resulting in a structurally thin enterprise layer that cannot be closed by improving fill rates on existing records — new firms must be sourced.
**Commercial impact**: Enterprise AEs and account-based marketing teams targeting holding companies, large manufacturers, and multi-site operators find an addressable universe that is too small to run meaningful ABM programs; this is a direct churn and expansion risk for enterprise-tier customers.
**Enrichment approach**: Source net-new enterprise firms via SEC filings (10-K, proxy statements), D&B and Refinitiv company registries, and corporate hierarchy databases to expand the enterprise record pool independent of fill-rate improvements.
**Agent confidence**: 0.88 — The gap is clearly evidenced by the 1.65% share figure, but the exact size of the recoverable universe is uncertain because enterprise firm counts are inherently small and some firms may already be captured under subsidiary or DBA records.
**Verifier verdict**: ~ PLAUSIBLE — Size-dimension gap — no NAICS code; verified via Part 1 size quality summary (enterprise 1.65% of records, website fill 80.9%). SQL spot-check not applicable.

#### Gap 5: Micro-firm records (1–10 employees) in truck transportation (17,208 records, 58.1% website fill) and restaurants (21,723 records, 56.7% website fill) represent the worst-performing industry×size intersections in the platform, with roughly 4 in 10 records in each cohort lacking a website — degrading deliverability and contact quality for the exact SMB segments where Transportation and Accommodation gaps are most acute.

**NAICS**: 48-49 — Transportation and Warehousing (micro-firm band, with Restaurants as secondary cross)
**Prevalence**: 17,208 micro truck transportation records at 58.1% website fill; 21,723 micro restaurant records at 56.7% website fill; micro segment overall is 59.85% of all records (2,503,111) with 73.7% average website fill — these two sub-segments are 15–17 points below segment average
**Root cause**: Micro-sized operators in trucking and food service are disproportionately reliant on phone-based or offline business models with low or no web presence; existing sourcing pipelines capture the company record from directories or registries but cannot resolve a website because many of these firms genuinely lack one, requiring alternative contact enrichment strategies.
**Commercial impact**: Sales teams building outbound sequences for last-mile logistics tech, fleet fuel cards, restaurant supply, and hospitality staffing face deliverability failures when email or web-based contact signals are missing from micro-firm records; this degrades campaign conversion rates and erodes trust in list quality for SMB-focused customers.
**Enrichment approach**: Apply phone-first and address-based contact enrichment for micro-band trucking and restaurant records using FMCSA carrier contacts, state food service licensing registries, and reverse-phone append vendors to provide alternative contact vectors where websites are absent.
**Agent confidence**: 0.83 — The website fill figures are directly observed in the data and the cross-dimension pattern is clear, but the proportion of these records where a website genuinely does not exist versus where it simply has not been sourced is unknown, limiting the recoverable fraction estimate.
**Verifier verdict**: ✓ CONFIRMED — NES inflates comparator (94% non-employers) but employer-firm coverage vs. SUSB is only 34.5% — real sourcing gap confirmed.

**Cross-gap pattern**: Four of the five gaps share a common root: the platform's sourcing pipelines have not systematically tapped public regulatory registries (FMCSA, state licensing boards, franchise filings, SEC) that contain dense, employer-level firm signals in exactly the sectors and size bands most valued by B2B buyers. The fifth gap (enterprise sourcing volume) reflects a deliberate or implicit SMB-first ingestion posture that leaves the highest-value size band structurally underrepresented regardless of fill-rate quality.

**Recommended Part 4 target**: construction_national_sourcing — state contractor licensing boards provide the most actionable, publicly available, employer-firm-level data across all 48 gap states with no structural NES inflation ceiling, the commercial buyer base (GCs, subs, material suppliers) is well-defined and high-velocity, and the 28.0% SUSB employer coverage figure confirms a large recoverable population that a focused registry ingestion sprint could materially close within a single quarter.

---

## Verifier Spot-Check Detail

Each gap independently re-derived from `part0_companies_clean.parquet` via SQL. n=15 per gap. No LLM calls in this section.

### Gap 1 Spot-Check: Transportation and Warehousing (NAICS 48-49)

- Sector records in dataset: **86,263**
- Industry labels matched: ['airlines and aviation', 'freight and package transportation', 'maritime', 'maritime transportation', 'transportation, logistics, supply chain and storage', 'transportation/trucking/railroad', 'truck transportation', 'warehousing', 'warehousing and storage']
- Sample fill rates (n=15): website=73.3%, industry=100.0%, size=100.0%
- State distribution: {'Texas': 3, 'Washington': 2, 'California': 2, 'Georgia': 2, 'Florida': 2}
- Size distribution: {'1-10': 9, '11-50': 4, '201-500': 1, '51-200': 1}
- **Verdict**: CONFIRMED — NES inflates comparator (94% non-employers) but employer-firm coverage vs. SUSB is only 34.5% — real sourcing gap confirmed.

<details><summary>Sampling methodology (SQL — reproducible with the dataset)</summary>

```sql
SELECT COUNT(*) as cnt
        FROM read_parquet('/Users/kunal/code/salesdb-assignment/data/processed/part0_companies_clean.parquet')
        WHERE state IS NOT NULL
          AND industry IN ('airlines and aviation', 'freight and package transportation', 'maritime', 'maritime transportation', 'transportation, logistics, supply chain and storage', 'transportation/trucking/railroad', 'truck transportation', 'warehousing', 'warehousing and storage')
```

```sql
SELECT handle, name, city, state, industry, size, website, founded, type
        FROM read_parquet('/Users/kunal/code/salesdb-assignment/data/processed/part0_companies_clean.parquet')
        WHERE state IS NOT NULL
          AND industry IN ('airlines and aviation', 'freight and package transportation', 'maritime', 'maritime transportation', 'transportation, logistics, supply chain and storage', 'transportation/trucking/railroad', 'truck transportation', 'warehousing', 'warehousing and storage')
        ORDER BY hash(handle || 'phase2_verify_seed')
        LIMIT 15
```

</details>

### Gap 2 Spot-Check: Construction (NAICS 23)

- Sector records in dataset: **219,988**
- Industry labels matched: ['building construction', 'construction', 'residential building construction', 'specialty trade contractors']
- Sample fill rates (n=15): website=86.7%, industry=100.0%, size=100.0%
- State distribution: {'New York': 2, 'Connecticut': 1, 'Washington': 1, 'Georgia': 1, 'Wisconsin': 1}
- Size distribution: {'11-50': 10, '1-10': 4, '51-200': 1}
- **Verdict**: CONFIRMED — NES inflates comparator (79% non-employers) but employer-firm coverage vs. SUSB is only 28.0% — real sourcing gap confirmed.

<details><summary>Sampling methodology (SQL — reproducible with the dataset)</summary>

```sql
SELECT COUNT(*) as cnt
        FROM read_parquet('/Users/kunal/code/salesdb-assignment/data/processed/part0_companies_clean.parquet')
        WHERE state IS NOT NULL
          AND industry IN ('building construction', 'construction', 'residential building construction', 'specialty trade contractors')
```

```sql
SELECT handle, name, city, state, industry, size, website, founded, type
        FROM read_parquet('/Users/kunal/code/salesdb-assignment/data/processed/part0_companies_clean.parquet')
        WHERE state IS NOT NULL
          AND industry IN ('building construction', 'construction', 'residential building construction', 'specialty trade contractors')
        ORDER BY hash(handle || 'phase2_verify_seed')
        LIMIT 15
```

</details>

### Gap 3 Spot-Check: Retail Trade (NAICS 44-45)

- Sector records in dataset: **170,027**
- Industry labels matched: ['arts & crafts', 'consumer goods', 'food and beverage retail', 'furniture', 'luxury goods & jewelry', 'online and mail order retail', 'retail', 'retail apparel and fashion', 'retail art supplies', 'retail furniture and home furnishings']
- Sample fill rates (n=15): website=80.0%, industry=100.0%, size=100.0%
- State distribution: {'New York': 3, 'California': 2, 'Virginia': 2, 'Kansas': 1, 'Illinois': 1}
- Size distribution: {'1-10': 10, '11-50': 4, '51-200': 1}
- **Verdict**: CONFIRMED — NES inflates comparator (76% non-employers) but employer-firm coverage vs. SUSB is only 25.5% — real sourcing gap confirmed.

<details><summary>Sampling methodology (SQL — reproducible with the dataset)</summary>

```sql
SELECT COUNT(*) as cnt
        FROM read_parquet('/Users/kunal/code/salesdb-assignment/data/processed/part0_companies_clean.parquet')
        WHERE state IS NOT NULL
          AND industry IN ('arts & crafts', 'consumer goods', 'food and beverage retail', 'furniture', 'luxury goods & jewelry', 'online and mail order retail', 'retail', 'retail apparel and fashion', 'retail art supplies', 'retail furniture and home furnishings', 'retail groceries', 'retail health and personal care products', 'retail luxury goods and jewelry', 'retail motor vehicles', 'retail office equipment')
```

```sql
SELECT handle, name, city, state, industry, size, website, founded, type
        FROM read_parquet('/Users/kunal/code/salesdb-assignment/data/processed/part0_companies_clean.parquet')
        WHERE state IS NOT NULL
          AND industry IN ('arts & crafts', 'consumer goods', 'food and beverage retail', 'furniture', 'luxury goods & jewelry', 'online and mail order retail', 'retail', 'retail apparel and fashion', 'retail art supplies', 'retail furniture and home furnishings', 'retail groceries', 'retail health and personal care products', 'retail luxury goods and jewelry', 'retail motor vehicles', 'retail office equipment')
        ORDER BY hash(handle || 'phase2_verify_seed')
        LIMIT 15
```

</details>

### Gap 4 Spot-Check: Size-dimension gap (NAICS N/A)

- Sector records in dataset: **0**
- Industry labels matched: []
- Sample fill rates (n=0): website=N/A%, industry=N/A%, size=N/A%
- State distribution: {}
- Size distribution: {}
- **Verdict**: PLAUSIBLE — Size-dimension gap — no NAICS code; verified via Part 1 size quality summary (enterprise 1.65% of records, website fill 80.9%). SQL spot-check not applicable.

<details><summary>Sampling methodology (SQL — reproducible with the dataset)</summary>

```sql

```

```sql

```

</details>

### Gap 5 Spot-Check: Transportation and Warehousing (micro-firm band, with Restaurants as secondary cross) (NAICS 48-49)

- Sector records in dataset: **86,263**
- Industry labels matched: ['airlines and aviation', 'freight and package transportation', 'maritime', 'maritime transportation', 'transportation, logistics, supply chain and storage', 'transportation/trucking/railroad', 'truck transportation', 'warehousing', 'warehousing and storage']
- Sample fill rates (n=15): website=73.3%, industry=100.0%, size=100.0%
- State distribution: {'Texas': 3, 'Washington': 2, 'California': 2, 'Georgia': 2, 'Florida': 2}
- Size distribution: {'1-10': 9, '11-50': 4, '201-500': 1, '51-200': 1}
- **Verdict**: CONFIRMED — NES inflates comparator (94% non-employers) but employer-firm coverage vs. SUSB is only 34.5% — real sourcing gap confirmed.

<details><summary>Sampling methodology (SQL — reproducible with the dataset)</summary>

```sql
SELECT COUNT(*) as cnt
        FROM read_parquet('/Users/kunal/code/salesdb-assignment/data/processed/part0_companies_clean.parquet')
        WHERE state IS NOT NULL
          AND industry IN ('airlines and aviation', 'freight and package transportation', 'maritime', 'maritime transportation', 'transportation, logistics, supply chain and storage', 'transportation/trucking/railroad', 'truck transportation', 'warehousing', 'warehousing and storage')
```

```sql
SELECT handle, name, city, state, industry, size, website, founded, type
        FROM read_parquet('/Users/kunal/code/salesdb-assignment/data/processed/part0_companies_clean.parquet')
        WHERE state IS NOT NULL
          AND industry IN ('airlines and aviation', 'freight and package transportation', 'maritime', 'maritime transportation', 'transportation, logistics, supply chain and storage', 'transportation/trucking/railroad', 'truck transportation', 'warehousing', 'warehousing and storage')
        ORDER BY hash(handle || 'phase2_verify_seed')
        LIMIT 15
```

</details>

---

## Record-Level Quality Observations (Haiku, n≈496)

Sampled from top-5 gap sectors, stratified by state (10 worst-covered Tier A + 5 Tier B states) and size band. n=100 per gap. Haiku assessed each record for semantic quality issues that rules can't detect (website–company mismatch, industry mislabelling, platform URL misses, data anomalies).

| Gap | Records Sampled | States Covered | Issues Found | Top Issues |
|---|---|---|---|---|
| Transportation and Warehousing (NAICS 48-49) | 99 | 14 | 31 | industry_mislabel (18), website_mismatch (5), data_anomaly (5) |
| Construction (NAICS 23) | 98 | 15 | 23 | industry_mislabel (10), website_mismatch (8), data_anomaly (5) |
| Retail Trade (NAICS 44-45) | 99 | 15 | 29 | industry_mislabel (18), website_mismatch (8), data_anomaly (2) |
| None (NAICS None) | 100 | 28 | 27 | industry_mislabel (10), website_mismatch (9), data_anomaly (8) |
| Transportation and Warehousing (micro-firm band, with Restaurants as secondary cross) (NAICS 48-49) | 100 | 9 | 27 | industry_mislabel (16), website_mismatch (6), data_anomaly (4) |

---

## Manual Audit Observations

These observations were made during manual spot-checking of sampled records and Google search verification. They are independent of the agent and Haiku passes above — human eyes on the raw data.

### Observation A — Website field corruption: private US businesses assigned foreign government domains

Manual inspection of individual records found private US businesses with completely unrelated foreign government URLs stored as their `website` value:

| Entity | Stored website | What that URL actually is |
|---|---|---|
| Better Health Massage Therapy | `betterhealth.vic.gov.au` | Victorian state government health portal, Australia |
| Aerobics Plus (Endicott, NY) | `wirral.gov.uk` | Wirral Council, a UK local government site |

This is not the expected institutional-entity case (a .gov agency storing its own domain). These are private US businesses — a massage therapy practice and a fitness studio — with entirely unrelated foreign government domains assigned to them. The most likely explanation is a scrape or ingestion artefact where a web crawler resolved a government health directory page that referenced the business, then stored the directory's domain rather than the business's own URL.

**Rules gap**: The `INSTITUTIONAL_TLDS` check in `src/shared/rules.py` matches only `.gov` (US federal suffix). `betterhealth.vic.gov.au` ends in `.gov.au` and `wirral.gov.uk` ends in `.gov.uk` — both pass through the rules stage uncaught and are counted as "has a website" in the 80.56% fill rate figure. The full population of such country-code government domain corruptions is unknown.

**Implication for enrichment priority**: The 291,896 records identified as the website enrichment gap (Part 3, Gap 1) is a lower bound. An additional, unknown number of records in the "populated" 80.56% carry corrupted domains that the current blocklist and institutional-TLD check do not catch. Field reliability for the populated population cannot be assumed — this is a precision risk, not just a coverage risk, and it reinforces the Precision-First Policy in Part 3 §3.

---

### Observation B — Small business records: broadly unreliable, low online presence confirmed by Google search

Manual Google searches on a sample of small business records (1–50 employees) across multiple sectors found a significant share where:

- The named business returns **no Google search results** at all
- The business appears only as a **Google Maps listing** with no associated website
- The business appears **under a different name**, suggesting a rebrand or acquisition not reflected in the record
- The business **appears to have closed**, with no current web presence

This is directionally consistent with the agent's Gap 5 finding (micro trucking at 58.1% website fill, micro restaurants at 56.7%) but the manual search goes further: it is not just an enrichment gap where a website exists but wasn't sourced. A material fraction of small business records in the 1–50 employee band appear to refer to entities that are effectively offline, defunct, or unidentifiable by name — not simply unenriched.

**Implication**: This observation further validates the Part 3 Scope Assumption (micro-business exclusion from enrichment). Running the website enrichment cascade against micro and small business records at scale risks populating stale, wrong, or irrelevant URLs at high volume — producing an enriched file that looks more complete but is less trustworthy. It also reinforces Gap 5's "low or no web presence" root cause: for a significant share of these records, a website to find does not exist.

---

## Trust Calibration Note

The data-engineer (Haiku + Sonnet) produced sector rankings and gap narratives from pre-aggregated statistics in `part2_gap_candidates.json`. The verifier independently re-derived each top-5 finding from raw `part0_companies_clean.parquet` via SQL (n=15 per gap). Verdicts above reflect the verifier's independent assessment.

Known methodological limits:
- NES non-employer comparator inflates gaps in sole-proprietor-heavy sectors (Transportation, Other Services, Admin & Support).
- Industry labels in our dataset map to NAICS via `part1_industry_naics_mapping.json` (244 labels mapped); unmapped labels are excluded from sector counts.
- Confidence scores are agent-estimated, not statistically derived.
- **Record-level quality pass is plausibility-only, not ground-truth verification.** The Haiku audit flags issues based on name–website–industry coherence within the record. It cannot confirm whether a website actually belongs to this specific entity, whether the domain is live, or whether the industry label was applied correctly at ingestion. Issue counts above are directional signals, not measured error rates.
- **Dataset is approximately 3 years old** (sourced circa 2022–2023 based on SUSB 2022 / NES 2023 comparators). Websites change, companies close, and industry classifications shift. A significant share of "clean" records by current standards may now be stale. This makes a Google Places API run a natural first step in Part 4: it serves dual purpose — enriching missing website/category fields for gap sectors *and* validating the accuracy of existing records against current business state. Partial, verified data is preferable to high-volume data of unknown freshness.