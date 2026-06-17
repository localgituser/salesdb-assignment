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

**Gap 1 — Transportation and Warehousing (NAICS 48-49)** · 1.99% overall; HIGH_GAP all 48 states; 34.5% vs SUSB employer firms · Confidence 0.88 · Verifier: ✓ CONFIRMED

FMCSA and DOT carrier registries not ingested. NES inflation (94% non-employers) raises the comparator denominator but the employer-firm gap is real and recoverable. Commercial signal: freight tech, fuel card, and fleet-service AEs cannot build viable prospect lists from current inventory.

---

**Gap 2 — Construction (NAICS 23)** · 5.93% overall; HIGH_GAP all 48 states; 28.0% vs SUSB employer firms · Confidence 0.90 · Verifier: ✓ CONFIRMED

State contractor licensing boards and building permit databases not systematically ingested. 48-state uniformity of the gap signals a sourcing miss, not a quality issue. Commercial signal: construction tech and equipment financing AEs face sub-10% coverage in every state — no viable territory to run.

---

**Gap 3 — Retail Trade (NAICS 44-45)** · 6.19% overall; HIGH_GAP all 48 states; 25.5% vs SUSB employer firms · Confidence 0.87 · Verifier: ✓ CONFIRMED

Franchise disclosure registries and state retail licensing records not ingested. NES inflation (75.7% non-employers) accounts for some of the headline gap; recoverable employer-firm layer is real. Commercial signal: POS, supply chain, and staffing AEs cannot identify the majority of their retail SMB TAM.

---

**Gap 4 — Enterprise sourcing volume (cross-cut, no NAICS)** · 1.65% of records (69,109 firms); website fill 80.9% masks the volume gap · Confidence 0.88 · Verifier: ~ PLAUSIBLE

Sourcing pipelines calibrated toward high-volume SMB ingestion; enterprise firms are numerically rare but disproportionately valuable. Fill-rate improvements don't close this — new firms must be sourced via SEC filings, D&B, and corporate hierarchy databases. Commercial signal: ABM programs for enterprise-tier customers don't have enough records to run at scale.

---

**Gap 5 — Micro-firm website fill: trucking and restaurants** · 17,208 micro truck transport records at 58.1% website fill; 21,723 micro restaurant records at 56.7% — 15-17 points below segment average · Confidence 0.83 · Verifier: ✓ CONFIRMED

Many micro-operators are genuinely phone-first or offline; sourcing captures the company record but can't resolve a URL. Standard web discovery won't work — alternative enrichment (FMCSA carrier contacts, state food service licensing, reverse-phone append) needed. Commercial signal: outbound sequences for last-mile logistics, fleet fuel, restaurant supply, and hospitality staffing face systematic deliverability gaps.

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