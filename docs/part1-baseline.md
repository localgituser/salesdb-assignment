# Part 1 — Baseline Observations
_Generated: 2026-06-12 | Script: src/part1_baseline.py | Dataset: data/processed/part0_companies.parquet_

---

## 1. Record Counts

| Metric | Value |
|---|---|
| Total raw records | 4,306,855 |
| **US records (in-scope)** | **4,164,063** |
| Null-state records (excluded) | 97,912 |
| Non-US records (excluded) | 44,880 |
| US share of file | 96.68% |

**Note**: `part0_companies.parquet` is already filtered at Part 0. Null-state and non-US records are a 3.32% residue — non-trivial for mid-to-large companies (see Section 1b). The effective working dataset is **4.16M US records**, but invalid-state records are worth cleaning before Part 4.

---

## 1b. Invalid & Null State Analysis

_Script: `src/part1_invalid_states.py` | Comparator: full US state name list (50 states + DC + 5 territories)_

**Summary**

| Category | Count | % of Total |
|---|---|---|
| Valid state | 4,164,063 | 96.69% |
| Null state | 97,912 | 2.27% |
| Non-null invalid state | 44,880 | 1.04% |
| **Total excluded** | **142,792** | **3.32%** |

**Medium-to-large companies (51+ employees) affected**

| Size Band | Total in Tier | Excluded (null/invalid) | % of Tier |
|---|---|---|---|
| 51–200 | 284,633 | 8,840 | 3.1% |
| 201–500 | 78,975 | 2,901 | 3.7% |
| 501–1K | 30,026 | 1,171 | 3.9% |
| 1K–5K | 27,173 | 1,053 | 3.9% |
| 5K–10K | 5,529 | 309 | 5.6% |
| **10K+** | **9,119** | **660** | **7.2%** |
| **TOTAL (51+)** | **435,455** | **14,934** | **3.4%** |

**Verdict**: Exclusion rate increases with company size — reaching 7.2% for large enterprises (10K+). This is above any "safe to ignore" threshold and represents a real commercial gap for Sales Intelligence.

**Root cause — mostly dirty US data, not foreign companies**

Inspection of the top invalid-state values shows the majority are malformed US state references:

| State Value | Records | Type |
|---|---|---|
| York | 14,774 | City leaked into state field |
| District Of Columbia | 10,495 | Capitalisation mismatch vs "District of Columbia" |
| D.C. | 1,871 | Abbreviation variant |
| Portland | 995 | City leaked into state field |
| Tx Texas | 282 | Redundant state prefix |
| Fl Florida | 129 | Redundant state prefix |
| Flrida | 213 | Typo |

These are **rules-fixable** — normalisation (case folding, whitespace trim, abbreviation lookup, city→state disambiguation) will recover the majority without any LLM calls.

**Quantified breakdown** of the 45,169 non-null invalid-state records, after rule-based categorisation:

| Category | Records | Distinct values | Notes |
|---|---|---|---|
| US recoverable — case mismatch | 10,495 | 1 | "District Of Columbia" → "District of Columbia" |
| US recoverable — city leaked into state | 17,903 | 41 | "York", "Portland", "Marietta" — recombine with city field |
| US recoverable — abbreviation variant | 2,087 | 47 | "D.C.", "N.Y.", "N.J." → expand |
| US recoverable — redundant prefix | 2,155 | 143 | "Tx Texas", "Fl Florida" → strip prefix |
| US recoverable — typo | 511 | 6 | "Flrida", "Califrnia", "Californie" |
| US territory (excluded from gap rankings) | 355 | 5 | Puerto Rico (239), Virgin Islands (66), American Samoa (38) |
| **Genuinely foreign** | **1,879** | **75** | Ontario, London, Maharashtra, Karnataka, Delhi, Gauteng, Dubai, etc. |
| Junk | 165 | 2 | "Null", "Unknown" |
| Unclassified (mostly city-like, smaller cities not in lookup) | 9,619 | 2,806 | Long tail; majority likely additional city leaks |

**Foreign-record bound**: ≥1,879 confirmed foreign + an unknown sub-fraction of the 9,619 unclassified (estimated upper bound: ~3K–4K records total foreign). The non-recoverable residue after a full rules pass is therefore expected to be ~3K–4K records (~0.07%–0.10% of the US population) — small enough to drop without commercial impact.

**Recommended fix** (add to `src/shared/rules.py` before Part 4):
1. Case-fold + trim: catches "District Of Columbia" → "District of Columbia"
2. Abbreviation expansion map: "D.C." → "District of Columbia", "Tx Texas" → "Texas", "Fl Florida" → "Florida"
3. City-in-state lookup: "Portland" → "Oregon" (or flag for manual review if ambiguous), "York" → flag
4. After normalisation, re-run `record_counts` query to confirm recovery rate before Part 4 enrichment

---

## 1c. Post-Cleanup Null-State: High-Value Records Unassignable to Part 2

_Queried from `data/processed/part0_companies_clean.parquet` (post-rules-cleanup). Pre-cleanup Section 1b used `part0_companies.parquet` and reported 142,792 excluded (null + invalid state combined); after rules recovery of ~18,267 records, the residual null-state population is **124,525**._

**Part 2 treatment**: Records with `state IS NULL` after cleanup cannot be bucketed into any state-level gap calculation and are excluded from Part 2 denominators. City is not a Part 2 dimension and does not affect inclusion.

**High-value residue** (mid-market and enterprise with null state post-cleanup):

| Size Band | Null-State Count |
|---|---|
| 51–200 | 7,787 |
| 201–500 | 2,536 |
| 1K–5K | 914 |
| 10K+ | 528 |
| 5K–10K | 270 |
| **Total (51+)** | **13,061** |

13,061 mid-market and enterprise records (~10.5% of the 124K null-state total) have no assignable state. These are excluded from Part 2 gap ratios but should be **logged as a separate finding** in `part2_gap_candidates.json` — they represent recoverable enrichment value in Part 4 (a company with 500+ employees very likely has a public website that would reveal HQ state). Tag as `state_unknown_high_value` in the gap candidates output.

Records missing **industry** or **size** remain in Part 2 denominators — they are the gap signal, not an exclusion criterion.

---

## 2. State Tier Distribution

Thresholds calibrated for 4.25M-record scale:
- **Tier A** ≥ 50,000 records → full audit confidence
- **Tier B** 10,000–49,999 → directional
- **Tier C** < 10,000 → flag only, exclude from ranked gap lists

| Tier | States | Total Records | Record Range |
|---|---|---|---|
| A | 23 | 3,504,270 (84.2% of US) | 62K – 619K |
| B | 25 | 634,208 (15.2%) | 10K – 48K |
| C | 7 | 25,585 (0.6%) | 5 – 9,245 |

Tier C contains: Alaska, South Dakota, North Dakota, and 4 US territories (Puerto Rico, American Samoa, Guam, Northern Mariana Islands). **Territories should be excluded from all gap rankings** — record counts are too thin (5–239) to draw conclusions.

Top 5 Tier A states by record count: California (619K), Texas (351K), New York (309K), Florida (306K), Illinois (165K). These 5 states alone account for **41% of all US records**.

---

## 2b. Sampling & Stratification Strategy

At 4.16M records, a full LLM pass is not feasible within the $10 budget. The agentic audit (Part 2) and enrichment PoC (Part 4) both require a statistically defensible sample that mirrors the real distribution.

### Part 2 Audit Sample (n=100 per gap, 5 gaps → 496 records)

Part 2 ran a **semantic record-quality audit** across the top 5 gap sectors identified by Part 1.6, not a broad state-stratified sample. Each gap sector received 100 records drawn from states where that sector's coverage ratio was lowest, for a total of 496 records audited (slight shortfall from 500 due to state availability in two gaps).

| Gap Sector | NAICS | Records Audited |
|---|---|---|
| rank_1 — Transportation & Warehousing | 48-49 | 99 |
| rank_2 — Construction | 23 | 98 |
| rank_3 — Retail Trade | 44-45 | 99 |
| rank_4 — Size-dimension enrichment | (cross-cut) | 100 |
| rank_5 — Transportation & Warehousing (secondary) | 48-49 | 100 |
| **Total** | | **496** |

**Why 100/gap instead of ~3,500**: A state-stratified sample of 3,500 would cost ~$14 at Haiku rates — over the entire $10 project ceiling. The audit goal was qualitative pattern detection (mislabels, bad URLs, platform URLs missed), not distributional precision by state. At an observed issue rate of ~31% in the first gap (31/99 records flagged), n=100 gives more than sufficient power to characterise systematic error types. State-level stratification would matter for estimating *prevalence* by state, which is a Part 4 enrichment concern, not a gap-detection concern.

**Verifier spot-check sample size (n=15 per gap)** — n=15 gives ~96.5% power to detect a structural gap at ≥20% within-slice prevalence. Sufficient for directional confirmation; finer-grained gaps (p < 10%) are flagged but not ranked.

### Part 4 Enrichment PoC Sample (~300 records) — Single-Run, Size-Stratified

The PoC runs in a single pass against a size-stratified sample spanning the full enrichable distribution. 

**Pre-filter (applied, not deferred)**: Exclude records matching `size = '1-10' AND founded >= 2015 AND website IS NULL AND type IS NULL` — the `HIGH_CHURN_RISK` flag from Section 5b. Strict-match count is only ~5,718 records, so excluding them costs almost nothing and removes the highest-stale-entity-risk slice. `size IS NULL` records are also excluded (no anchor field for segment assignment).

**Sample composition (~300 records, 4 segments × 3 conditions):**

| Segment | Total | missing_website | missing_industry | platform_url |
|---|---|---|---|---|
| Enterprise (500+) | 60 | 30 | 18 | 12 |
| Mid-market (51–500) | 80 | 40 | 24 | 16 |
| SMB (11–50) | 80 | 40 | 24 | 16 |
| Micro (1–10, churn-filtered) | 80 | 40 | 24 | 16 |
| **Total (pre-dedup)** | **300** | **150** | **90** | **60** |

Enterprise is heavily oversampled (~0.05% population weight gets 20% of the sample). A record may satisfy multiple conditions (e.g., both website and industry missing); handle-level dedup collapses these — actual sample size is **288 records**.

The `platform_url` condition forces the rules-stage blocklist to fire (yelp/facebook/wixsite etc. as the website value) and is the right test for the platform-URL reclassification logic. Sample is deterministic via `hash(handle || seed)`.

**Cost**: ~$0.50–1.50 at Haiku rates, fits the $5 Part 4 budget.

Script: `src/part1_sampling.py` → `data/processed/part1_sample_audit.parquet`. Each row is stamped with `poc_segment` and `poc_condition` so the eval can report per-cell.

---

## 3. Nationwide Field-Level Fill Rates (Missingness)

| Field | Fill % | Records Missing | Priority |
|---|---|---|---|
| handle | 100.00% | 0 | — |
| name | 100.00% | 0 | — |
| state | 100.00% | 0 | — |
| city | 98.78% | ~50,934 | Low |
| size | 95.49% | ~188K | Medium |
| industry | 91.81% | ~341K | **High** |
| website | 78.17% | **~910K** | **Critical** |
| type | 54.90% | ~1.88M | Medium† |
| founded | 45.90% | ~2.25M | Low |

**Key finding**: `website` is the biggest gap (~910K missing). `industry` is the second largest actionable gap (~341K missing). `founded` is majority-missing but low commercial priority — secondary signal, harder to recover. `type` is split: the public-company sub-case is **High** priority (deterministic SEC/ticker lookup, no model call, ICE 63, Rank 3 in Part 3); the private/unknown sub-case is Low (requires LLM inference, ICE 16).

_† `type` priority split per Part 3 ICE analysis: public companies = High (Ease 9, SEC EDGAR); private/unknown = Low (Ease 4, LLM inference)._

**Reconciling three `website` missing counts cited in this document:**
- **908,883** (Section 11.2): raw SQL count of `website IS NULL` on the valid-state US population (4,164,063 records). Authoritative "raw NULL" figure.
- **~910K** (this section, rounded): same as above.
- **~972K** (Section 6b): raw NULL + ~62,057 platform/social/builder URLs reclassified as effectively NULL per the blocklist. This is the **enrichment-relevant** count — the number of records that need a real website discovered, not just imputed.

When sizing enrichment work, use **~972K**. When reporting raw fill rate as queried, use **908,883 / 21.83%**.

---

## 4. Fill Rates by State (Enrichment Opportunity Map)

Worst-coverage states (lowest avg fill across website + industry + size):

| State | Tier | Website % | Industry % | Size % | Avg Fill % |
|---|---|---|---|---|---|
| Iowa | B | 68.8 | 81.2 | 95.8 | 81.9 |
| Kansas | B | 70.8 | 84.1 | 95.7 | 83.5 |
| West Virginia | B | 67.2 | 89.7 | 94.5 | 83.8 |
| Mississippi | B | 67.7 | 90.4 | 94.1 | 84.1 |
| Arkansas | B | 70.5 | 90.3 | 94.1 | 85.0 |
| Tennessee | A | 73.5 | 87.3 | 96.3 | 85.7 |
| Oregon | A | 75.0 | 86.7 | 96.1 | 85.9 |

Best-coverage states:

| State | Tier | Website % | Industry % | Size % | Avg Fill % |
|---|---|---|---|---|---|
| Massachusetts | A | 81.9 | 94.1 | 95.8 | 90.6 |
| Delaware | B | 84.5 | 94.3 | 95.8 | 91.6 |
| District of Columbia | B | 86.7 | 95.6 | 93.7 | 92.0 |

**Observation**: `website` is consistently the lowest-filled field in every state — the gap range is 67–87%. It dominates the enrichment opportunity signal. `industry` has more variance by state (81% in Iowa vs. 96% in DC), suggesting Iowa/Kansas/West Virginia have both a website problem AND an industry classification gap. These are the highest-ROI enrichment targets in Tier B. Among Tier A states, Tennessee and Oregon stand out as below-average.

### 4a. Full 51-state fill-rate table (worst → best by avg fill)

_Generated from `data/processed/part0_companies.parquet` on the 4,163,774-record valid-state population (50 states + DC). Avg fill = mean of website/industry/size fill percentages._

| State | Tier | Records | Website % | Industry % | Size % | Avg Fill % |
|---|---|---|---|---|---|---|
| Iowa | B | 31,249 | 68.8 | 81.2 | 95.8 | 81.9 |
| Kansas | B | 32,199 | 70.8 | 84.1 | 95.7 | 83.5 |
| West Virginia | B | 10,569 | 67.2 | 89.7 | 94.5 | 83.8 |
| Mississippi | B | 17,301 | 67.7 | 90.4 | 94.1 | 84.1 |
| Arkansas | B | 23,429 | 70.5 | 90.3 | 94.1 | 85.0 |
| Alaska | C | 9,245 | 69.8 | 89.6 | 96.7 | 85.4 |
| Tennessee | A | 72,102 | 73.5 | 87.3 | 96.3 | 85.7 |
| Oregon | A | 62,334 | 75.0 | 86.7 | 96.1 | 85.9 |
| New Mexico | B | 17,978 | 72.4 | 91.1 | 94.8 | 86.1 |
| Alabama | B | 39,190 | 73.6 | 90.6 | 94.1 | 86.1 |
| Oklahoma | B | 35,484 | 73.6 | 90.8 | 94.3 | 86.2 |
| South Dakota | C | 8,534 | 73.4 | 90.8 | 94.4 | 86.2 |
| North Dakota | C | 7,517 | 73.8 | 90.6 | 94.5 | 86.3 |
| Louisiana | B | 39,837 | 73.7 | 91.4 | 94.5 | 86.5 |
| Kentucky | B | 32,080 | 75.5 | 89.9 | 94.3 | 86.6 |
| Montana | B | 12,685 | 76.8 | 89.5 | 93.8 | 86.7 |
| Ohio | A | 127,174 | 75.2 | 90.2 | 95.2 | 86.9 |
| Nebraska | B | 20,478 | 75.7 | 90.7 | 95.1 | 87.2 |
| Indiana | A | 67,249 | 78.3 | 91.3 | 92.6 | 87.4 |
| South Carolina | B | 45,982 | 77.8 | 91.5 | 93.9 | 87.7 |
| Michigan | A | 108,881 | 76.8 | 91.9 | 95.1 | 87.9 |
| New Jersey | A | 124,155 | 75.6 | 92.8 | 95.4 | 87.9 |
| Rhode Island | B | 14,198 | 76.3 | 92.3 | 95.2 | 87.9 |
| Hawaii | B | 15,106 | 74.5 | 93.8 | 95.6 | 88.0 |
| Missouri | A | 64,537 | 76.2 | 92.6 | 95.4 | 88.1 |
| Wisconsin | A | 67,453 | 77.9 | 91.7 | 95.0 | 88.2 |
| Minnesota | A | 75,049 | 78.4 | 91.3 | 95.3 | 88.3 |
| Texas | A | 351,297 | 77.5 | 91.8 | 95.7 | 88.3 |
| Idaho | B | 19,650 | 79.3 | 91.5 | 94.3 | 88.3 |
| Connecticut | B | 48,191 | 78.2 | 91.9 | 94.9 | 88.3 |
| Pennsylvania | A | 141,916 | 78.1 | 91.9 | 95.0 | 88.4 |
| North Carolina | A | 115,134 | 78.0 | 92.6 | 94.7 | 88.5 |
| Georgia | A | 133,221 | 77.8 | 91.9 | 95.8 | 88.5 |
| New Hampshire | B | 20,572 | 79.4 | 91.8 | 94.8 | 88.7 |
| Vermont | B | 10,225 | 80.1 | 91.1 | 95.1 | 88.8 |
| Maine | B | 16,889 | 80.4 | 91.3 | 94.8 | 88.8 |
| Virginia | A | 101,700 | 79.2 | 92.3 | 95.3 | 88.9 |
| Nevada | B | 38,056 | 78.0 | 92.9 | 95.9 | 88.9 |
| Illinois | A | 165,346 | 79.0 | 91.9 | 95.6 | 88.9 |
| Washington | A | 104,783 | 78.7 | 92.4 | 95.7 | 89.0 |
| Maryland | A | 71,005 | 80.2 | 92.3 | 95.1 | 89.2 |
| California | A | 619,440 | 79.6 | 92.0 | 96.2 | 89.3 |
| Florida | A | 306,228 | 80.3 | 92.1 | 95.6 | 89.3 |
| Arizona | A | 80,683 | 80.5 | 92.1 | 95.7 | 89.4 |
| New York | A | 309,011 | 78.9 | 93.5 | 96.1 | 89.5 |
| Utah | B | 44,321 | 80.5 | 93.2 | 95.5 | 89.7 |
| Colorado | A | 105,915 | 82.6 | 92.3 | 95.8 | 90.2 |
| Wyoming | B | 11,424 | 81.1 | 93.8 | 96.1 | 90.3 |
| Massachusetts | A | 129,657 | 81.9 | 94.1 | 95.8 | 90.6 |
| Delaware | B | 20,061 | 84.5 | 94.3 | 95.8 | 91.6 |
| District of Columbia | B | 17,054 | 86.7 | 95.6 | 93.7 | 92.0 |

Tier C (Alaska, South Dakota, North Dakota) shown for completeness but excluded from ranked gap lists per the skill.

### 4b. size × state cross-tab — website fill vs. parity targets

_Tier A+B states (≥10K records). Mid-market = size bands 51-200 + 201-500. Enterprise = 501-1K + 1K-5K + 5K-10K + 10K+._

**Finding**: All 48 Tier A+B states are below parity on website fill for BOTH mid-market (target ≥95%) AND enterprise (target ≥99%). Best mid-market is Delaware at 93.3%; best enterprise is Vermont at 97.9%. The parity targets in the table below are aspirational ceilings — no US state currently clears them on `website`.

Worst 10 states on mid-market website fill (a Part 4 enrichment priority slice):

| State | Mid-market n | Mid-market website % | Enterprise n | Enterprise website % |
|---|---|---|---|---|
| Mississippi | 1,463 | 82.0 | 304 | 89.5 |
| West Virginia | 949 | 83.2 | 160 | 85.0 |
| Arkansas | 1,779 | 84.5 | 355 | 90.4 |
| New Mexico | 1,209 | 85.7 | 187 | 94.7 |
| Alabama | 3,453 | 86.1 | 674 | 92.7 |
| Oklahoma | 3,106 | 86.3 | 559 | 92.1 |
| Louisiana | 3,699 | 86.4 | 622 | 88.7 |
| Tennessee | 5,691 | 87.5 | 1,281 | 92.2 |
| Kentucky | 3,042 | 87.6 | 604 | 91.7 |
| Hawaii | 1,076 | 87.6 | 188 | 92.0 |

**Implication for Part 4 sample weighting**: within the mid-market segment of the PoC sample (see Section 2b), prioritise records from Mississippi, West Virginia, Arkansas, New Mexico, Alabama, Oklahoma, and Louisiana — they have the largest parity gap and a meaningful absolute record count (≥950 per state). Iowa and Kansas (worst overall avg fill in §4) are dominated by their micro/SMB cohorts; their mid-market populations are mid-pack on website fill.

### 4c. Coverage parity definition (size-stratified)

Coverage targets must differ by company size — achieving 90% website fill on micro-businesses (<10 employees) is historically impossible and low-value; the same threshold on enterprise accounts is commercially unacceptable.

| Size Band | Website Fill Target | Industry Fill Target | Size Fill Target |
|---|---|---|---|
| Enterprise (500+ employees) | **≥ 99%** | **≥ 99%** | **≥ 99%** |
| Mid-market (51–500) | ≥ 95% | ≥ 97% | ≥ 98% |
| SMB (11–50) | ≥ 88% | ≥ 93% | ≥ 96% |
| Micro (<11) | ≥ 75% | ≥ 85% | ≥ 93% |

A state reaches overall coverage parity when all four size bands meet their respective thresholds. For gap-ranking purposes (Part 2), **enterprise and mid-market gaps are weighted 3× vs. micro-business gaps** — a single enterprise record with missing website is worth three micro-business completions for Sales Intelligence ROI.

The flat aggregate thresholds (website ≥ 90%, industry ≥ 95%, size ≥ 97%) from best-covered Tier A states remain useful as a simple summary signal but should not be used for enrichment prioritisation decisions.

**Accuracy standard (the brief asks "at what accuracy", not just fill rate)**: Fill rate alone is incomplete — a website field populated with a wrong URL meets a fill-rate threshold but fails commercially. Coverage parity in this submission therefore has two dimensions:

| Dimension | What's measured | Measurement point |
|---|---|---|
| Completeness | % of records with a non-null value (after platform-URL reclassification per §6b) | Part 1 (this document) |
| Correctness | Precision against ground truth: enriched values that match human-labelled answers | Part 4 eval (`evals/ground_truth.json`, n=20–25 hand-labelled) |

Targets per field:
- **Website correctness**: ≥ 90% precision (a populated URL must resolve to the company's own domain, not a platform/social URL, not a 404, not a wrong company)
- **Industry correctness**: ≥ 85% precision against the canonical-merged taxonomy (semantic-duplicate pairs from §6b counted as correct if either label appears)
- **Size correctness**: ≥ 95% precision (size is enum-bounded; misclassification is the main failure mode)

A state reaches **true parity** when both completeness AND correctness targets are met. The Part 1 baseline cannot measure correctness without ground truth — only Part 4's eval can. Completeness is the necessary-but-not-sufficient gate.

**State-tier variant on completeness**: Tier A states are held to the full size-band table above. Tier B states are scored *directionally* — they meet parity if they are within 5 percentage points of the Tier A target (e.g., Tier B enterprise website ≥ 94% rather than ≥ 99%) given thinner record counts. Tier C is excluded from parity scoring entirely.

**PoC scope**: Parity targets are evaluated *per segment* in a single PoC pass (see Section 2b). Enterprise and mid-market targets are the realistic Part 4 deliverable; micro and SMB targets are aspirational against the higher-churn, lower-fill baseline — the eval reports precision/recall per size band so the gap between aspiration and achievement is visible rather than hidden by deferral.

---

## 5. Industry & Size Distributions

### Industry (top 10 by volume)
| Industry | Records | % |
|---|---|---|
| (null) | 341,170 | 8.19 |
| Construction | 217,362 | 5.22 |
| Real Estate | 146,750 | 3.52 |
| Hospitals & Health Care | 135,015 | 3.24 |
| Advertising Services | 131,740 | 3.16 |
| Medical Practices | 111,790 | 2.68 |
| IT Services & Consulting | 105,361 | 2.53 |
| Financial Services | 98,110 | 2.36 |
| Software Development | 93,497 | 2.25 |
| Retail | 92,955 | 2.23 |

**Observation**: The dataset skews heavily toward traditional/physical industries (construction, real estate, healthcare). Tech (IT consulting + software) accounts for ~4.8% combined. No single industry dominates — the top 10 cover only ~36% of records. This is consistent with a broad B2B universe rather than a curated tech-company dataset.

### Size Distribution
| Size Band | Records | % |
|---|---|---|
| 1–10 employees | 2,490,862 | 59.82 |
| 11–50 | 1,065,045 | 25.58 |
| 51–200 | 275,793 | 6.62 |
| (null) | 187,635 | 4.51 |
| 201–500 | 76,074 | 1.83 |
| 501–1K | 28,855 | 0.69 |
| 1K–5K | 26,120 | 0.63 |
| 10K+ | 8,459 | 0.20 |
| 5K–10K | 5,220 | 0.13 |

**Observation**: 85.4% of records are micro/small businesses (<50 employees). Enterprise accounts (500+) are only 1.65% of the dataset (~68K records). For Sales Intelligence targeting mid-market and enterprise, the dataset has structural thin coverage at the top of the market — a genuine commercial gap worth flagging.

**PoC scope**: The Part 4 sample spans all four size segments — enterprise (500+), mid-market (51–500), SMB (11–50), and churn-filtered micro (1–10) — with enterprise oversampled to ~20% of the 300-record sample despite being 1.65% of the population. The earlier "Run 1 = 51+ only, Run 2 = micro/SMB" framing was discarded; see Section 2b for the single-run rationale. A `HIGH_CHURN_RISK` pre-filter (Section 5b) excludes the highest-stale-entity-risk slice of micro (~5,718 records) without deferring the segment entirely.

---

## 5b. Data Reliability by Size Band (Vintage Adjustment)

_Vintage-reliability evidence — used in the PoC to justify the `HIGH_CHURN_RISK` pre-filter and per-segment eval reporting, not to defer micro/SMB to a second run._

The dataset is 2023-vintage (~3 years old). Fill rates and average company age by size band show a clear monotonic gradient:

_Counts and rates below recomputed against the valid-state US population (4,163,774 records). Earlier draft of this table had count-column estimates (232K / 64K / 24K / 22K / 4.4K / 7.4K) that did not reconcile with §5 — those have been replaced with the authoritative figures from the same query as §5. Avg age uses a 2026-vintage baseline (2026 − founded) for established firms; the dataset itself is 2023-collected._

| Size Band | Records | Website Fill | Industry Fill | Type=NULL % | Avg Company Age (2026 baseline) |
|---|---|---|---|---|---|
| 1–10 (micro) | 2,490,725 | 75.3% | 92.9% | 47.2% | ~13 years (2023 base) / ~16 (2026) |
| 11–50 | 1,064,962 | 80.6% | 94.7% | 43.0% | ~23 / ~26 |
| 51–200 | 275,757 | 89.3% | 97.5% | 18.1% | ~35 / ~38 |
| 201–500 | 76,063 | 90.7% | 98.5% | 11.9% | ~42 / ~45 |
| 501–1K | 28,851 | 92.6% | 99.2% | 7.9% | ~48 / ~51 |
| 1K–5K | 26,114 | 92.7% | 99.3% | 8.1% | ~52 / ~55 |
| 5K–10K | 5,219 | 92.2% | 99.2% | 6.4% | ~57 / ~60 |
| 10K+ | 8,458 | 92.3% | 99.6% | 4.6% | ~52 / ~55 |

**Vintage reliability interpretation**: Established firms with 51+ employees average 38–61 years old. The 3-year survival probability for firms this size exceeds 95%. Enriching a 2023-vintage record for a company that averaged 38+ years in age in 2023 is very likely to produce a still-accurate result in 2026. By contrast, micro businesses averaging 16 years of age in 2023 include a meaningful fraction of companies founded 2018–2022 — a cohort with 35–45% failure rates over a 5-year window. Enriching closed entities wastes tokens and pollutes the output file.

**HIGH_CHURN_RISK pre-filter** (applied in the Part 4 PoC sample):
```sql
size IN ('1-10')
AND founded >= 2015
AND website IS NULL
AND type IS NULL
```
Records matching all four criteria are high-probability stale entities. Strict-match count is ~5,718 records — excluding them costs almost nothing and removes the slice most likely to waste tokens on closed companies. The remaining ~2.5M micro records stay in scope and are sampled normally; the PoC eval reports precision/recall per size band so the vintage gradient is visible in the results rather than hidden by deferral.

---

## 6. Data Quality Flags

| Flag | Count | % of US Records |
|---|---|---|
| Total US records | 4,164,063 | 100% |
| Malformed websites | 98 | <0.01% |
| Suspicious founding year (< 1800) | 1,331 | 0.03% |
| Future founding year (> 2026) | 0 (see note) | — |
| Short names (< 2 chars) | 505 | 0.01% |
| Missing city | 50,934 | 1.22% |
| Duplicate records (name+state) | 33,850 | 0.81% |

**Note on `future_founded`**: Returned NaN — likely a type issue (founded stored as float, comparison to int 2026 may not fire). Flag for investigation before rules cleanup.

**Note on `malformed_website`**: Only 98 flagged despite ~910K missing. The regex only catches present-but-malformed URLs; missing URLs are captured in the fill-rate table, not here. The website _quality_ problem is overwhelmingly one of absence, not malformation.

**Duplicate spot-check finding**: The top name+state "duplicates" are noise records: `.`, `none`, `na`, `n/a`, `a`, `x`, `test`, `closed`. These 505 short-name records + ~32 records named `.` in California represent garbage data, not true business entity duplicates. True business entity duplicates are a much smaller subset of the 33,850 flagged.

### Rule-vs-LLM Split

| Issue | Approach | Reason |
|---|---|---|
| Malformed website URLs | **Rules** | Regex normalization (strip scheme, add TLD, trim whitespace) — deterministic |
| Platform/social profile URLs in website field | **Rules** | Blocklist of known non-company domains — deterministic |
| Website-builder root domains (no subdomain) | **Rules** | Blocklist of builder platforms where root ≠ real company URL — deterministic |
| Short/garbage names (`.`, `n/a`, `test`) | **Rules** | Simple length + blocklist filter — no ambiguity |
| Status-sentinel names (`Closed`, `Retired`, `Deleted`) | **Rules** | Fixed sentinel blocklist — deterministic |
| Suspicious founding years | **Rules** | Clamp to 1800–2026 range — no judgement needed |
| Missing city (50K records) | **Rules** | Can be inferred from state + zip (if available) via lookup table |
| City/state split artifacts (`city=New`, `state=York`) | **Rules** | Deterministic recombination when city+state = known city name |
| Junk city abbreviations (`Ny`, `Fl`, `Dc`, `N/A`) | **Rules** | State-abbreviation blocklist + length filter — deterministic |
| Exact-match deduplication | **Rules** | Identical name+state → merge or flag — deterministic |
| Missing website (~910K records) | **LLM + Search** | Requires external lookup — rules cannot infer a URL from a name |
| Industry semantic duplicates (`it services` vs `information technology & services`) | **LLM** | Canonical label merging requires semantic judgement |
| Industry classification gaps (~341K) | **LLM** | High-cardinality, context-dependent — rules misclassify edge cases |
| Industry inconsistencies (present but wrong) | **LLM** | Semantic judgement on company name/description — rules can't do this |
| Fuzzy entity deduplication | **LLM** | "IBM Corp" vs "International Business Machines" — needs embeddings or LLM |

---

## 6b. Field-Type-Aware Value Distribution Audit

_Script: ad-hoc DuckDB queries on `part0_companies.parquet` | Scope: 4,164,063 US records_

Each field was audited according to its expected cardinality. High-cardinality fields (should be mostly unique) were checked for anomalously frequent values. Low-cardinality enum fields were checked for values outside the canonical set. Medium-cardinality categorical fields were checked for near-duplicate labels.

---

### website — high-cardinality (should be mostly unique)

**Finding: 62,057 records store a platform/social/institutional URL instead of the company's own website.**

These records are not missing (`website IS NOT NULL`) and would pass a simple fill-rate check, but the stored value is useless for Sales Intelligence outreach. They are effectively NULL and should be treated as such before enrichment.

| Category | Examples | Records |
|---|---|---|
| Social / directory profiles | yelp.com (13,151), facebook.com (11,017), instagram.com (3,407), linkedin.com (3,403), twitter.com (499) | ~35,000 |
| Link aggregators / URL shorteners | linktr.ee (7,317), bit.ly (1,957), hub.biz (377) | ~9,700 |
| Website builder root domains | wixsite.com (3,499), weebly.com (1,661), wordpress.com (1,610), squarespace.com (431) | ~9,500 |
| Search / e-commerce platforms | google.com (1,787), amazon.com (387), youtube.com (1,554) | ~3,700 |
| Institutional (.edu / .mil / .gov) | berkeley.edu (445), army.mil (348), ca.gov (426) | ~4,100 |
| **Total** | | **~62,057** |

**Note on website-builder platforms**: `wixsite.com` stored without a subdomain means the company's actual URL (`companyname.wixsite.com/page`) was truncated to the platform root. The same applies to weebly.com, wordpress.com, etc. These are not valid company websites as stored.

**Cardinality-explosion check (>0.1% threshold)**: The platform/social URLs above qualify by an order of magnitude — `yelp.com` at 13,151 records is 0.32% of US records; `facebook.com` at 0.26%; `linktr.ee` at 0.18%. All 13 platform/social domains exceed the 0.1% anomalous-frequency threshold and are correctly captured by the blocklist above.

**Franchise/chain shared domains — full ≥50-records pass**: 383 distinct domains appear on ≥50 distinct `handle` records, covering 101,391 records total. Categorised:

| Category | Distinct domains | Records |
|---|---|---|
| Platform/social (already in blocklist) | 13 | 47,967 |
| Website builder (already in blocklist) | 10 | 11,605 |
| Institutional (.edu/.mil/.gov, already in blocklist) | 168 | 19,841 |
| **True franchise / chain shared domain** | **192** | **21,978** |

Top 10 true franchise/chain by record count: `thetopperson.com` (641), `marriott.com` (621), `expresspros.com` (499), `hilton.com` (495), `schoolloop.com` (328), `myshopify.com` (327), `meetup.com` (309), `hyatt.com` (306), `substack.com` (305), `vpweb.com` (281). Hotels, real estate brokerages (`kw.com` = Keller Williams), franchise services, and shared community platforms dominate. These are technically valid as proxy websites but misleading for unique company identification — flag with `has_shared_domain = true` in `src/shared/rules.py`; do not null out.

**Placeholder strings**: ~90 records store partial URL strings (`www`, `com`, `http`, `https`) with no domain — rules-fixable via regex.

**Rule**: Null out any website value that matches the platform blocklist above. Estimated recovery: **62,057 records reclassified from "has website" to "needs enrichment"** — raises the true missing-website count from 910K to ~972K.

---

### type — low-cardinality enum

**Finding: clean. No out-of-vocabulary values, no typos.**

8 distinct non-null values, all valid: `Privately Held`, `Self-Owned`, `Nonprofit`, `Partnership`, `Public Company`, `Self-Employed`, `Educational`, `Government Agency`. The 44.71% null rate is a missingness problem, not a quality problem. No rules fix needed.

---

### size — low-cardinality enum

**Finding: clean. No out-of-vocabulary values.**

8 distinct non-null values matching expected bands: `1-10`, `11-50`, `51-200`, `201-500`, `501-1K`, `1K-5K`, `5K-10K`, `10K+`. The 4.49% null rate is a missingness problem only. No rules fix needed.

---

### industry — medium-cardinality categorical (491 distinct values)

**Finding: no typos, but 3 semantic duplicate label pairs covering ~329K records.**

**Cardinality trend check (label-explosion threshold = 500 distinct values)**: 491 distinct values — **below the 500 threshold**, so this check **clears with `no_action_needed`**. Stating this explicitly so it appears in the profiling JSON summary.

**String-similarity check (token sort ratio ≥ 0.85)**: All pairs above the 0.85 threshold were inspected (the threshold yielded 12 pairs; manual review confirmed all 12 are legitimately different sectors — e.g., `residential building construction` vs `nonresidential building construction`). No spelling errors found via this check.

**Taxonomy-inconsistency check** (subset/abbreviation pattern — distinct from the similarity check): three label pairs describe the same concept using different wording — a LinkedIn taxonomy inconsistency, not a data entry error. These were found via the subset-pattern check, not the 0.85 string-similarity check:

| Label A | Records | Label B | Records | Combined | Recommended Canonical |
|---|---|---|---|---|---|
| `it services and it consulting` | 107,040 | `information technology & services` | 30,873 | **137,913** | `it services and it consulting` |
| `wellness and fitness services` | 77,642 | `health, wellness & fitness` | 24,077 | **101,719** | `wellness and fitness services` |
| `non-profit organizations` | 70,725 | `non-profit organization management` | 18,706 | **89,431** | `non-profit organizations` |

These 329,063 records are split across two labels each. For NAICS mapping and ICP filtering, the split artificially deflates each label's apparent volume. **LLM canonical merging** (not rules) is the right fix — the labels are semantically close but not identical strings, so a blocklist won't generalize.

---

### city — medium-cardinality

**Finding: two distinct junk patterns totalling ~16,500 records.**

**Pattern 1 — city/state field split** (14,114 records): `city='New'` + `state='York'` = New York City records where "New York" was split across the two fields during ingestion. This is the **same root cause** as the `state='York'` invalid-state finding in Section 1b (14,774 records). The counts align: `state='York'` records are overwhelmingly `city='New'`. Rules fix: when `city + ' ' + state` matches a known city+state pair, recombine and assign correct state.

**Pattern 2 — state abbreviations / junk in city field** (~2,400 records): `Ny` (805), `Mc` (458), `Fl` (171), `N/A` (165), `La` (135), `Sf` (109), `Dc` (67) plus hyphen-prefix patterns (`B-`, `A-`, `E-`). These are state abbreviations or address-fragment artifacts. Rules fix: blocklist of known state abbreviations appearing as city values, plus length ≤ 2 filter.

---

### name — should be unique

**Finding: 293 records use status-sentinel strings as company names (beyond the 505 short-name records already flagged in Section 6).**

| Sentinel | Count |
|---|---|
| Closed / closed | 55 |
| None / none | 65 |
| N/A / n/a / NA / na | 80 |
| Retired | 34 |
| Test / test | 22 |
| Delete / deleted | 14 |
| ... | 14 |
| Unknown / unknown | 6 |
| Removed | 3 |
| **Total** | **~293** |

These are status markers entered by a data operator rather than actual company names. Rules fix: add to the garbage-name blocklist alongside the short-name filter.

---

### founded — numeric year

**Finding: 1,357 pre-1800 records confirmed junk; 0 future-year records (>2026) confirmed clean.**

Pre-1800 sample is unambiguously fictional: founding years of 1201, 1210, 1212, 1215, etc., paired with names like "CBS Corporation Ltd" (1212), "LinkedIn Harder" (1323), "MISKATONIC UNIVERSITY" (1347). These are not historical institutions — they are test records or data entry errors. Rules fix: clamp `founded < 1800 → NULL`.

The future-year (`founded > 2026`) NaN result from Section 6 is resolved: there are genuinely **0 future-year records**. The DuckDB float→int comparison worked correctly; NaN indicated an empty result set, not a type error.

---

### Summary: new issues surfaced by field-type audit

| Field | Issue | Count | Fix |
|---|---|---|---|
| `website` | Platform/social/institutional URL stored as website | ~62,057 | Rules: blocklist → reclassify as NULL |
| `website` | Incomplete website-builder root domain | ~9,500 | Rules: builder blocklist → NULL |
| `website` | Placeholder strings (`www`, `com`, `http`) | ~90 | Rules: regex |
| `industry` | Semantic duplicate label pairs (3 pairs) | ~329,063 | LLM canonical merge |
| `city` | city/state split (`New` + `York`) | ~14,114 | Rules: recombine → fix `state` too |
| `city` | State abbreviations / junk in city | ~2,400 | Rules: blocklist + length filter |
| `name` | Status-sentinel garbage names | ~293 | Rules: blocklist |
| `founded` | Pre-1800 junk years | 1,357 | Rules: clamp → NULL |

**Total new records requiring rules cleanup (beyond Section 6 flags)**: ~409,000 — dominated by the website reclassification (~72K) and the industry semantic-merge scope (~329K).

---

## 7. Candidate Key Analysis

| Candidate Key | Distinct Values | Duplicates | Collision Rate | Nulls in Key |
|---|---|---|---|---|
| `handle` | 4,164,063 | **0** | **0.00%** | 0 |
| `name + state` | 4,146,445 | 17,618 | 0.42% | 132 |
| `name + domain` | 4,152,405 | 11,658 | 0.28% | **908,947** |
| `name + city + state` | 4,155,692 | 8,082 | 0.19% | 51,064 |

**Recommendation**: Use **`handle`** as the primary merge key for all enrichment operations. It is perfectly unique (0 collisions, 0 nulls) and should be treated as the stable entity identifier throughout Parts 2–4.

`name + city + state` is the best human-readable / external-linkage key — adding city cuts the `name + state` collision rate by more than half (0.42% → 0.19%), halving the ambiguity for the micro/SMB tail where state-registered name uniqueness doesn't apply. The 51,064 nulls in key are driven entirely by missing `city` (~1.22% of records); `name` and `state` are both present in the valid-state population. Use this key when joining to external datasets or lookup sources that lack `handle` (e.g., spot-checking enriched output against web search). Do not use for automated merge-back.

`name + state` is usable as a fallback human-readable key with a known 0.42% collision caveat — adequate for deduplication checks but not safe for automated merge-back without handle confirmation.

`name + domain` appears to have a lower collision rate (0.28%) but is misleading: 908,947 records have no website, meaning their domain key is NULL, and `COUNT(DISTINCT (name, NULL))` treats each as unique. The real collision rate among records _with_ a website is higher. Do not use as a merge key.

---

## 8. SUSB State Coverage Comparison

_Source: US Census Statistics of U.S. Businesses (SUSB) 2022 (`us_state_6digitnaics_2022.csv`) vs `part0_companies.parquet` | Script: `src/part1_comparator.py`_

**SUSB** (Statistics of U.S. Businesses) counts employer firms — businesses with at least one W-2 employee — by state and NAICS sector. It is the primary government benchmark for US business universe coverage.

Coverage ratio = our records / SUSB firm count per state. Gap tiers: HIGH_GAP <10%, MODERATE_GAP 10–30%, ADEQUATE >30%.

**Finding: all 51 states are ADEQUATE.** No state is below 35% coverage. Coverage ranges from 35.1% (Montana) to 89.5% (DC).

| Tier | States | Range |
|---|---|---|
| HIGH_GAP | 0 | — |
| MODERATE_GAP | 0 | — |
| ADEQUATE | 51 | 35.1% – 89.5% |

**Lowest-coverage states** (all Tier B by record count — thin but not structural gaps):
- Montana: 35.1%, South Dakota: 35.9%, North Dakota: 37.4%, Vermont: 39.1%, Wyoming: 39.9%

**Highest-coverage states** (small states where our records approach SUSB totals):
- DC: 89.5%, Delaware: 82.7%, Massachusetts: 87.9%

**Large Tier A states** (California, Texas, New York, Florida): 58%–73% — solid representation.

**Implication**: State-level breadth is not the problem. The dataset has adequate geographic coverage across all 50 states + DC. Part 2 gap detection should focus on **sub-state dimensions** — industry × state or size × state — not missing states.

**Limitations**: SUSB counts legal "firms"; our data counts records (may include duplicates). Ratios are directional. SUSB 2022 vintage may not match our dataset vintage.

---

## 9. SUSB Industry Coverage Comparison

_Source: Statistics of U.S. Businesses (SUSB) 2022 national totals (State='00') vs `part0_companies.parquet` | Script: `src/part1_industry_mapper.py` | LLM: claude-haiku-4-5-20251001 ($0.01208)_

244 free-text industry labels (≥500 records each) were mapped to 20 NAICS 2-digit sectors via a single Claude Haiku call. Coverage = our records in that NAICS sector / SUSB national firm count.

### MODERATE_GAP sectors (under-represented vs. SUSB)

| NAICS | Sector | Our Records | SUSB Firms | Coverage % |
|---|---|---|---|---|
| 81 | Other Services (personal care, repair) | 89,652 | 729,236 | **12.3%** |
| 42 | Wholesale Trade | 51,703 | 277,932 | **18.6%** |
| 44-45 | Retail Trade | 170,759 | 645,404 | **26.5%** |
| 72 | Accommodation & Food Services | 160,435 | 574,723 | **27.9%** |
| 23 | Construction | 220,721 | 782,487 | **28.2%** |

These five sectors collectively represent ~1.6M SUSB firms we have only partial coverage for. They are the **primary Part 2 gap candidates**.

### Sectors at parity (ADEQUATE)

| NAICS | Sector | Coverage % | Note |
|---|---|---|---|
| 52 | Finance & Insurance | 88.2% | Near-parity |
| 54 | Professional, Scientific & Technical Services | 88.8% | Near-parity |
| 11 | Agriculture | 92.4% | Slightly over — plausible |

### Over-indexed sectors (>100% — dataset bias signal)

| NAICS | Sector | Coverage % | Interpretation |
|---|---|---|---|
| 61 | Educational Services | 144.4% | Individual tutors/training counted as companies |
| 31-33 | Manufacturing | 168.8% | Duplicate records or broad label usage |
| 71 | Arts, Entertainment, Recreation | 191.5% | Freelancers/creators counted as companies |
| 51 | Information | **379.7%** | **Strong LinkedIn/tech-source bias** |
| 99 | Unclassified (null + rare labels) | 6,644.7% | Artificial — null industries bucket here |

**Note — revised by Section 10**: The over-indexed ratios above use SUSB employer firms as the sole denominator. When NES non-employer establishments are added (Section 10), the Information sector falls to 69.4% ADEQUATE and Manufacturing to 62.5% ADEQUATE. The over-indexing was an artifact of SUSB's employer-only scope, not source bias. See Section 10 for the authoritative interpretation.

**Limitations**: NAICS mapping is LLM-generated and approximate — multi-sector labels (e.g., "IT Services") may be misclassified. Null industry records (~341K) and rare labels all count under NAICS 99, artificially inflating unclassified coverage. SUSB-only ratios should not be used for gap prioritisation without the NES adjustment.

---

## 10. SUSB + NES Combined Industry Coverage

_Source: Statistics of U.S. Businesses (SUSB) 2022 (employer firms) + Nonemployer Statistics (NES) 2023 (non-employer establishments) vs `part0_companies.parquet` | Script: `src/part1_nes_comparator.py`_

**NES** (Nonemployer Statistics) counts businesses with no paid employees — sole proprietors, self-employed individuals, and independent contractors. It captures ~30.4M entities that SUSB misses entirely. Adding NES to the SUSB denominator (~6.5M employer firms) produces a 36.9M total business universe. This changes the coverage picture significantly.

### Key findings vs. SUSB-only comparison

**Sectors that were "over-indexed" — now explained:**

| NAICS | Sector | SUSB-Only % | Combined % | Shift |
|---|---|---|---|---|
| 51 | Information | 379.7% | 69.4% | ADEQUATE — non-employers explain the gap |
| 31-33 | Manufacturing | 168.8% | 62.5% | ADEQUATE — maker/fabricator sole props |
| 71 | Arts/Entertainment | 191.5% | 15.1% | MODERATE_GAP — still under-represented vs. full universe |
| 61 | Educational Services | 144.4% | 15.0% | MODERATE_GAP — tutors/coaches dominate NES |

The Information sector over-indexing is fully accounted for by non-employer tech workers, freelancers, and indie creators. **This is no longer evidence of source bias — it's evidence that our dataset captures the non-employer digital economy well.**

**New HIGH_GAP sectors revealed by NES:**

| NAICS | Sector | Combined % | Interpretation |
|---|---|---|---|
| 48-49 | Transportation & Warehousing | 2.0% | Gig workers (Uber/Lyft/DoorDash) dominate NES — 4M non-employers |
| 81 | Other Services | 2.3% | Solo repair, personal care — 3.2M non-employers missed |
| 56 | Admin & Support | 3.6% | Cleaning services, solo temp workers — 2.9M non-employers |
| 53 | Real Estate | 4.5% | Individual agents/property managers — 3.2M non-employers |
| 23 | Construction | 6.0% | Solo contractors — 2.9M non-employers |

These sectors were ADEQUATE or MODERATE_GAP against SUSB alone, but are HIGH_GAP against the full business universe. The dataset genuinely under-covers gig economy and trades operators.

**Sectors remaining ADEQUATE after NES adjustment:**
- Manufacturing (62.5%), Information (69.4%), Utilities (60.9%), Management of Companies (32.9%)

**Implication for Part 2**: The combined analysis sharpens the gap narrative considerably:
1. The dataset is well-calibrated for the employer-firm professional economy (Information, Finance, Professional Services at 15–70%)
2. The genuine coverage gaps are in gig-economy/solo-operator sectors (Transportation 2%, Other Services 2.3%) and traditional physical economy (Construction 6%, Retail 6.3%)
3. These are sourcing gaps — they cannot be closed by enriching existing records. Requires additional data sources (trade registers, state contractor licenses, gig platform exports)

---

## Summary: What This Means for Parts 2–4

1. **Primary enrichment target**: `website` field (~910K missing). Closing this gap has the highest ROI for Sales Intelligence — a company without a website URL is effectively un-linkable to external data sources.

2. **Secondary target**: `industry` classification (~341K missing + unknown quality issues on present values). Needed for ICP filtering.

3. **Highest-priority states**: Iowa, Kansas, West Virginia, Mississippi, Arkansas (Tier B with worst avg fill). Tennessee and Oregon are the Tier A outliers worth targeting.

4. **PoC sample spans all four size segments in a single run** (~300 records → 288 after handle dedup). Enterprise (500+) is oversampled to 20% of the sample despite being 1.65% of the population — gives the eval statistical power on the primary ICP. Mid-market, SMB, and churn-filtered micro each contribute ~27% so the cascade is stress-tested across the full distribution, not just the easy half. The strict `HIGH_CHURN_RISK` filter (Section 5b) excludes ~5,718 highest-risk micro records as a pre-filter; the remaining micro population stays in scope. Per-segment precision/recall in the Part 4 eval is the actionable signal — it tells us which size bands the cascade is trustworthy for, rather than deferring 85% of the dataset to a Run 2 that might never ship. Enterprise records are structurally thin in the source data (only 1.65% at 500+) — that's a sourcing gap, not an enrichment issue.

5. **Physical economy sectors are structurally under-represented**: Construction (6.0%), Retail (6.3%), Transportation (2.0%), Other Services (2.3%), and Admin/Support (3.6%) are all HIGH_GAP when measured against the full SUSB+NES universe. These gaps reflect the source platform's professional/digital bias — they are sourcing gaps, not enrichment opportunities.

6. **The Information over-index is explained, not bias**: The 379.7% SUSB-only figure drops to 69.4% when NES non-employers are included. Our dataset captures the digital non-employer economy well; it does not over-represent tech firms, it just sees sole-proprietor tech workers that SUSB misses.

7. **Rules cleanup first**: Short/garbage names, malformed URLs, suspicious founding years, and invalid state values — clear these with `src/shared/rules.py` before running any LLM passes to avoid wasting tokens on non-entities. Invalid/null state records are 3.32% overall but reach 7.2% of large enterprises (10K+); most are recoverable via case normalisation and abbreviation expansion (see Section 1b).

8. **Safe merge key established**: `handle` is the anchor for all enrichment writes.

---

## 11. Extended Profiling Audit

_Generated: 2026-06-12 | Script: ad-hoc DuckDB queries | Dataset: data/processed/part0_companies.parquet | Scope: 4,164,063 US records_

---

### 11.1 Cross-Field Consistency Checks

#### 11.1a City/State Coherence

The top 20 most-frequent (city, state) pairs were queried and verified against known US geography:

| City | State | Count | Verdict |
|---|---|---|---|
| New York | New York | 120,391 | Valid |
| Los Angeles | California | 81,103 | Valid |
| Houston | Texas | 58,812 | Valid |
| Chicago | Illinois | 56,633 | Valid |
| San Francisco | California | 51,587 | Valid |
| Miami | Florida | 40,301 | Valid |
| Atlanta | Georgia | 39,659 | Valid |
| Austin | Texas | 38,831 | Valid |
| Dallas | Texas | 37,613 | Valid |
| San Diego | California | 33,203 | Valid |
| Seattle | Washington | 30,709 | Valid |
| Denver | Colorado | 28,481 | Valid |
| Las Vegas | Nevada | 23,086 | Valid |
| Phoenix | Arizona | 22,950 | Valid |
| Boston | Massachusetts | 22,782 | Valid |
| Portland | Oregon | 21,789 | Valid |
| Philadelphia | Pennsylvania | 20,542 | Valid |
| Orlando | Florida | 19,645 | Valid |
| Charlotte | North Carolina | 18,896 | Valid |
| Tampa | Florida | 18,570 | Valid |

**Finding: 0 impossible city/state pairs in the top 20.** All top-20 (city, state) combinations are geographically coherent. The city/state field-split artifact ("New" + "York") identified in Section 6b is not surfacing in the top-20 because those split records have been captured separately under state='York' in Section 1b — they do not appear in the valid-state-filtered dataset used here.

**Fix classification**: `no_action_needed` for top-20. The split-artifact records (14,114) already flagged in Section 6b under `city` should be addressed by the rules already specified there.

---

#### 11.1b Size vs. Founded Year Plausibility

**Finding: 231 records have `size = '10K+'` AND `founded >= 2021`** — companies that large in under 5 years as of 2026.

Count: **231** (0.006% of US records; 2.73% of all 10K+ records)

Top 10 examples:

| Handle | Name | Founded | Size |
|---|---|---|---|
| company/sccpconference | Consciousness: Science, Spirituality & Social Impact | 2023 | 10K+ |
| company/salesforce-qa-engineer | Salesforce QA Engineer | 2023 | 10K+ |
| company/generative-ai-crm | Generative AI CRM | 2023 | 10K+ |
| company/acostagrp | Acosta Group | 2023 | 10K+ |
| company/beagambler | Be A Gambler | 2023 | 10K+ |
| company/infinite-group-worldwide | INFINITE GROUP | 2023 | 10K+ |
| company/kia-veterans-technician-apprenticeship-program-vtap | KIA Veterans Technician Apprenticeship Program (VTAP) | 2023 | 10K+ |
| company/mays-cmc | Career Management Center - Texas A&M University Mays Business School | 2023 | 10K+ |
| company/fearless-founders | Fearless Founders AI | 2023 | 10K+ |
| company/neltify | Neltify | 2023 | 10K+ |

**Interpretation**: The examples reveal two distinct root causes. "Acosta Group" is a legitimate large company that rebranded/reorganized in 2023 and may have updated its LinkedIn `founded` year to reflect the restructuring rather than the original entity's founding. "Salesforce QA Engineer" and "Generative AI CRM" are clearly not independent companies — they are likely job posting pages or LinkedIn profile artifacts that were ingested as company records. "Consciousness: Science, Spirituality & Social Impact" and "Fearless Founders AI" are likely community pages or micro-events misclassified as 10K+ organizations. The `size` field for these records is almost certainly scraped from follower counts or event attendance, not actual employee headcount.

**Fix classification**: `flag_only` — these 231 records should be tagged `implausible_size_founded = true` in `src/shared/rules.py`. Do not null out `size` or `founded` without manual verification; the root cause is ambiguous (rebranding vs. phantom record).

---

#### 11.1c Website vs. Entity Type Consistency

Records where `type IN ('Nonprofit', 'Government Agency')` AND `website IS NOT NULL` AND the website does not end in `.org`, `.gov`, `.mil`, or `.edu`:

| Type | Non-mission-TLD count | Total with website | Non-mission % |
|---|---|---|---|
| Nonprofit | 67,497 | 231,951 | 29.1% |
| Government Agency | 9,194 | 21,519 | 42.7% |
| **Total** | **76,691** | **253,470** | **30.3%** |

Top 5 examples:

| Handle | Name | Type | Website |
|---|---|---|---|
| company/100peoplemacomb | 100 People Macomb | Nonprofit | 100peoplemacomb.com |
| company/2020wonvision | 2020WonVision | Nonprofit | 2020wonvision.com |
| company/3-steps-2-start-up | 3 Steps 2 Start Up | Nonprofit | 3steps2startup.com |
| company/4justiceemory | 4 Justice Emory | Nonprofit | instagram.com |
| company/a-better-chance-a-better-community | A BETTER CHANCE A BETTER COMMUNITY | Nonprofit | abc-2.net |

**Interpretation**: This is predominantly a **data quality signal, not an error pattern**. Many legitimate US nonprofits register `.com` domains (especially smaller community organizations). The 29.1% non-.org rate for nonprofits reflects reality — the IRS does not require `.org` registration for 501(c)(3) status. However, the 42.7% rate for Government Agency entities with `.com` websites is more concerning: legitimate federal, state, and local government agencies almost always use `.gov` or `.mil` domains. A `.com` website for a "Government Agency"-typed entity strongly suggests either a miscategorized record (e.g., a government contractor labeled as the agency itself) or a platform/social URL artifact (the `instagram.com` example above confirms this).

**Fix classification**: `flag_only` — flag `type = 'Government Agency'` AND `website` not ending in `.gov`/`.mil`/`.edu` (9,194 records) for manual spot-check. Nonprofits with `.com` (67,497) are low-priority given domain choice is arbitrary for nonprofits.

---

#### 11.1d Domain vs. Website Redundancy

**Finding: No `domain` column exists in the dataset.** The schema contains only `handle`, `name`, `website`, `industry`, `size`, `type`, `founded`, `city`, `state`, and `country_code`. There is no separate `domain` field to compare against.

**Fix classification**: `no_action_needed`.

---

### 11.2 Null Pattern Analysis (MCAR / MAR / MNAR)

**National null rates (baseline):**

| Field | Null Count | Null Rate |
|---|---|---|
| `website` | 908,883 | 21.83% |
| `industry` | 341,161 | 8.19% |
| `size` | 187,625 | 4.51% |
| `type` | 1,877,900 | 45.10% |

#### Null rates by state tier

| Tier | Records | website null % | industry null % | size null % | type null % |
|---|---|---|---|---|---|
| A (≥50K records) | 3,504,270 | 21.39% | 8.00% | 4.38% | 44.01% |
| B (10K–49,999) | 634,208 | 24.00% | 9.20% | 5.18% | 50.50% |
| C (<10K) | 25,296 | 27.81% | 9.67% | 4.74% | 61.43% |

_Note: Tier C row covers the 3 Tier C US states (Alaska, South Dakota, North Dakota = 25,296 records), excluding the 289 territory records (Puerto Rico, Guam, etc.) which are also <10K but outside the 50-state+DC scope used here._

#### Null rates by size band (website and industry)

| Size Band | Records | website null % | industry null % |
|---|---|---|---|
| 1–10 | 2,490,725 | 24.73% | 7.06% |
| 11–50 | 1,064,962 | 19.43% | 5.34% |
| 51–200 | 275,757 | 10.69% | 2.52% |
| 201–500 | 76,063 | 9.29% | 1.50% |
| 501–1K | 28,851 | 7.43% | 0.83% |
| 1K–5K | 26,114 | 7.28% | 0.69% |
| 5K–10K | 5,219 | 7.78% | 0.84% |
| 10K+ | 8,458 | 7.74% | 0.35% |
| NULL size | 187,625 | 23.71% | 53.22% |

#### Website null rate by state: top 5 and bottom 5 by record count

Top 5 states by record count (Tier A):

| State | Records | website null % | vs. national 21.83% |
|---|---|---|---|
| California | 619,440 | 20.38% | -1.45 pp |
| Texas | 351,297 | 22.54% | +0.71 pp |
| New York | 309,011 | 21.14% | -0.69 pp |
| Florida | 306,228 | 19.71% | -2.12 pp |
| Illinois | 165,346 | 20.96% | -0.87 pp |

Bottom 5 states by record count (Tier B/C):

| State | Records | website null % | vs. national 21.83% |
|---|---|---|---|
| North Dakota | 7,517 | 26.25% | +4.42 pp |
| South Dakota | 8,534 | 26.63% | +4.80 pp |
| Alaska | 9,245 | 30.18% | +8.35 pp |
| Vermont | 10,225 | 19.94% | -1.89 pp |
| West Virginia | 10,569 | 32.84% | +11.01 pp |

#### Null pattern classification per field

**`website` — MAR (Missing At Random given observed data)**

Evidence: The null rate varies substantially and systematically across both state tier and company size. West Virginia: 32.84% vs. national 21.83% (+11 pp); Alaska: 30.18% (+8.35 pp); Florida: 19.71% (-2.12 pp). The gradient across size bands is even stronger: micro businesses (1–10 employees) have a 24.73% null rate vs. 7.43% for mid-market (501–1K) — a 17.3 pp spread. This is consistent with MAR: whether a website is missing is predictable from observable covariates (state, company size). Enrichment should be stratified — do not apply a uniform model across all states and sizes. The high null rate in agricultural/rural states (West Virginia, Mississippi, Iowa) likely reflects structural differences in small business web presence, not random data collection failures.

**`industry` — MAR (Missing At Random given observed data), with MNAR characteristics**

Evidence: Null rate varies by size band: 7.06% for micro vs. 0.35% for 10K+ — a 20× gradient. Crucially, the `size=NULL` cohort has a 53.22% industry null rate (vs. 8.19% national), indicating that the two missingness patterns are correlated. Records missing both `size` and `industry` are likely the lowest-quality scrapes where the source profile had minimal data. This has MNAR characteristics: the kind of company that lacks an industry label is specifically the kind that would not have had one — informal businesses, stubs, and placeholder profiles. Enrichment will be harder for this cohort since there is no anchor field to infer from.

**`size` — MAR (Missing At Random given observed data)**

Evidence: Null rate varies by tier (Tier A: 4.38%, Tier C: 4.74%) but the spread is narrow (< 1 pp across tiers). The dominant correlation is the extreme null rate in the `size=NULL` cohort itself is tautological — the interesting finding is the `industry=NULL` correlation (53.22% of size-null records also lack industry). Size missingness appears uniformly distributed across states but correlated with record quality (same low-quality scrapes that miss industry also miss size). Enrichment can be applied relatively uniformly across states; the sub-population requiring attention is the doubly-null (size AND industry NULL) cohort.

**`type` — MNAR (Missing Not At Random)**

Evidence: The null rate follows an almost perfectly monotonic gradient: micro businesses (1–10 employees) have a 47.21% type null rate, enterprise (10K+) has 4.55%. Tier A: 44.01%, Tier B: 50.50%, Tier C: 61.43%. The `type` field in this dataset appears to reflect how often LinkedIn users (or data vendors) bother to classify organizational type — larger, more professionally curated company pages almost always have a type value; small/informal businesses almost never do. This is structurally MNAR: the companies that don't have a `type` value are specifically those that are less likely to have one (informal sole proprietors, hobby businesses, stub pages). Enrichment is structurally harder — rules cannot derive type from other fields, and LLM inference from name alone would be low-precision.

---

### 11.3 `founded` Round-Number Check

**Non-null `founded` records: 2,001,208**

#### Multiples of 1000 (primary check)

| Value | Count | % of non-null |
|---|---|---|
| 2000 | 29,320 | 1.465% |
| **Total mult-of-1000** | **29,320** | **1.465%** |

**Finding: 1.465% of non-null `founded` values are exact multiples of 1000** — well below the 5% flag threshold. Only the year 2000 qualifies (not 1000, 3000, etc.), and the context confirms it is a genuine year: `founded=2000` records have 91.2% website fill and 96.9% industry fill, nearly identical to `founded=2001` controls (92.3% and 97.1% respectively). The 2000 peak is also plausibly explained by the dot-com era founding spike — not placeholder inflation.

**Finding: 0.041% are multiples of 100 but not 1000** (828 records). The top values are 1900 (766), 1800 (53), and smaller counts for earlier century marks. These are ambiguous: some are likely genuine century-mark founding years (e.g., a company founded in 1900), while others are probably rounding artifacts. The total (828) is too small to act on without manual review.

#### Decade mark clustering (secondary signal)

Among records with `founded` between 1950 and 2024, 12.35% fall on decade marks (multiples of 10), versus an expected 10% if uniform. Multiples of 5: 21.24% vs. expected 20%. Both ratios are within ~2.5% of their expected values — consistent with mild human rounding bias (preferring round years when exact founding dates are unknown) but not a systematic placeholder-injection pattern.

**Fix classification**: `no_action_needed` — neither the mult-of-1000 rate (1.47%) nor the decade clustering (12.35% vs. 10% expected) exceeds the 5% threshold or exhibits an anomalous distribution pattern. The pre-1800 junk years (1,357 records) identified in Section 6b remain the actionable issue; this check adds no new cleaning requirements.

---

### 11.4 `name` Encoding Artifacts

All counts below are scoped to US state records (4,164,063).

#### 11.4a Unicode Replacement Character (U+FFFD)

**Count: 10 records** (0.0002% of US records)

Top 5 examples:

| Handle | Name |
|---|---|
| company/proflex-products-inc | PROFLEX▯▯ Products Inc |
| company/arête-custom-builds | Ar▯▯te Custom Builds |
| company/trured | TRU RED▯▯ |
| company/gezzo's-surf-&-grille | Gezzo▯▯▯s Surf & Grille |
| company/manyuses | ManyUses▯▯ |

**Interpretation**: Replacement characters indicate UTF-8 decoding failures during ingestion — likely caused by special characters (accented letters, typographic quotes, trademark symbols) in the source data that were not correctly decoded. The pattern `Ar▯▯te` is almost certainly `Arête` (the word "arête") and `Gezzo▯▯▯s` is `Gezzo's` (typographic apostrophe → three-byte sequence decoded as replacement chars).

**Fix classification**: `rules_fixable` — the 10 affected records can be individually reviewed and corrected. A general fix would attempt re-encoding from the original source (if available) or fuzzy-match the handle URL (which correctly shows `arête-custom-builds`) to reconstruct the intended name.

#### 11.4b High Special Character Ratio (>30% non-alphanumeric excluding spaces)

**Count: 4,006 US records** (0.096% of US records) — _reproduced as ~2,851 with `re.sub(r'[a-zA-Z0-9 ]', '', name)`; the 4,006 figure reflects a broader character-class definition in the original profiling script (treating digits as non-"plain" characters). Both counts support the same conclusion: this cohort is <0.1% of records._

Top 5 examples (mixed Latin + special chars):

| Handle | Name | Special % |
|---|---|---|
| company/jamit-news | --------------------------x | 96.3% |
| company/adriennearagon | ᴀᴇꜱᴛʜᴇᴛᴇ \| ʙy ᴀᴅʀɪᴇɴɴᴇ ᴀʀᴀɢᴏɴ | 96.0% |
| company/familia-español | 𝓕𝓪𝓶𝓲𝓵𝓲𝓪 𝓔𝓼𝓹𝓪n𝓸𝓵® 𝓒𝓪𝓽𝓮𝓻𝓲𝓷𝓰 | 95.7% |
| company/learn-english-academy | أكاديمية تعلم اللغة الإنجليزية - LEA | 90.3% |
| company/jejwd | 西[CJK+control chars] | 89.7% |

**Interpretation**: This cohort contains three distinct sub-patterns: (1) separator/spacer strings (`--------------------------x`) that are garbage names, (2) names using Unicode typographic letterforms (mathematical bold `𝗥𝗘𝗫𝗢𝗣𝗔𝗞`, script `𝓕𝓪𝓶𝓲𝓵𝓲𝓪`) that are real company names stored in decorative Unicode — these will break search indexes and string comparisons, and (3) foreign-language names (Arabic, CJK) that appear in US state records due to diaspora/immigrant businesses. The decorative-Unicode sub-pattern (8 records with 4-byte codepoints) should be normalized to plain ASCII equivalents.

**Fix classification**: `rules_fixable` for the garbage/separator names (overlaps with Section 6b short-name filter); `flag_only` for the decorative-Unicode names (8 records) — rules can strip to ASCII but may lose meaningful characters; `no_action_needed` for legitimate foreign-language names of US businesses.

#### 11.4c Mixed-Script and Foreign-Script Names

| Pattern | US Records | % of US Records |
|---|---|---|
| CJK characters (U+4E00–U+9FFF) | 316 | 0.0076% |
| Arabic characters (U+0600–U+06FF) | 302 | 0.0073% |
| Mixed Latin + CJK | 330 | 0.0079% |

Top 5 CJK examples:

| Handle | Name | State |
|---|---|---|
| company/calchina2020 | 2020加州中美峰会 California China-US Summit | California |
| company/casela-technologies | Casela Technologies 镭芯光电 | California |
| company/ospa-overseas-students-philanthropy-actions | OSPA (Overseas Students Philanthropy Actions)留学生公益在行动 | Maryland |
| company/spice-workshop-椒房 | Spice workshop 椒房 | New York |
| company/superus-health | Superus Health 至尚健康 | (not shown) |

Top 5 Arabic examples:

| Handle | Name | State |
|---|---|---|
| company/maawanamaa | Maawanamaa - ماء ونماء | Massachusetts |
| company/شبكة-ومنتديات-العمري-1 | شبكة ومنتديات العمري | New York |
| company/beati-بيئتي | Be'ati بيئتي | Massachusetts |
| company/wassmacapital | Wassma \| وسما | (null state) |
| company/lawelitefirm | نخبة القانون | (null state) |

**Interpretation**: CJK and Arabic names in US state records are predominantly legitimate businesses serving immigrant communities or operating bilingually. The mixed Latin+CJK pattern (330 records) is expected for US-based Chinese-American businesses that use both scripts on their LinkedIn profiles. Pure Arabic names (302 records) similarly reflect US-based Arabic-speaking businesses. These are not data quality errors — they are valid company names. The issue is operational: these names will not sort correctly in ASCII-first indexes and may cause display issues in downstream systems.

**Fix classification**: `flag_only` — tag records with CJK or Arabic characters as `has_non_latin_name = true` in rules.py so downstream consumers can handle them appropriately. Do not null out or modify the names.

---

### 11. Part 1.5 — Deterministic Cleanup Gate Results

**Executed**: 2026-06-13 | **Script**: `src/shared/rules.py` | **Input**: `part0_companies.parquet` (4,306,855 records) | **Output**: `part0_companies_clean.parquet`

Rules are non-destructive: the original parquet is never modified. Each output record carries a `rules_flags` column listing which rules fired (empty = no change). Total records modified: **132,463 of 4,306,855 (3.1%)**.

#### State normalisation (6-step pipeline, first match wins)

| Rule | Records affected |
|---|---|
| `state_city_recover` — city field used to disambiguate leaked suffix | 14,142 recovered |
| `state_abbrev_expand` — USPS codes + dotted variants (A.L., N.Y., etc.) | 2,060 recovered |
| `state_redundant_prefix` — "Tx Texas" → "Texas" (generic suffix search) | 1,649 recovered |
| `state_typo_fix` — known typos (Flrida, Californie, etc.) | 416 recovered |
| `state_unresolvable` — exhausted all steps, set to NULL | 26,613 → NULL |

**Net**: 44,880 invalid state values → **18,267 recovered (40.7%)**, 26,613 unresolvable → NULL.

Note: `state_case_fix` recoveries (title-case normalisation, ~10,495 records per §1b) are applied silently — no flag emitted for case-only fixes since the value is already semantically correct.

#### Website reclassification

| Rule | Records affected |
|---|---|
| `website_platform_blocklist` — social/directory/builder domains | 47,056 → NULL |
| `website_institutional_tld` — .edu / .mil / .gov | 40,864 → NULL |
| `website_placeholder` — stub strings ("www", "n/a", "example.com", etc.) | 153 → NULL |

**Net**: 88,073 URLs reclassified as NULL. True enrichable-missing website count rises from ~909K to **~997K** (was documented as ~972K in §2a; the institutional-TLD component was underestimated there).

#### Founded cleanup

| Rule | Records affected |
|---|---|
| `founded_pre1800` — confirmed junk test records (years 1201, 1212, etc.) | 1,403 → NULL |

---

### 12. Summary Table

| Field | Issue | Count | % of US Records | Fix |
|---|---|---|---|---|
| `city`/`state` | Impossible city/state pairs in top 20 | 0 | 0% | no_action_needed |
| `size`/`founded` | 10K+ companies founded ≥ 2021 | 231 | 0.006% | flag_only |
| `type`/`website` | Gov Agency with non-.gov/.mil/.edu website | 9,194 | 0.22% | flag_only |
| `type`/`website` | Nonprofit with non-.org/.gov website | 67,497 | 1.62% | flag_only |
| `domain` | No `domain` column exists | N/A | — | no_action_needed |
| `website` | Null rate (national) | 908,883 | 21.83% | MAR — stratified enrichment |
| `industry` | Null rate (national) | 341,161 | 8.19% | MAR/MNAR — stratified enrichment |
| `size` | Null rate (national) | 187,625 | 4.51% | MAR — uniform enrichment viable |
| `type` | Null rate (national) | 1,877,900 | 45.10% | MNAR — structurally hard |
| `founded` | Multiples of 1000 (year 2000 only) | 29,320 | 0.70% | no_action_needed (below 5% threshold) |
| `founded` | Multiples of 100 (not 1000) | 828 | 0.02% | no_action_needed |
| `name` | Unicode replacement character (U+FFFD) | 10 | 0.0002% | rules_fixable |
| `name` | >30% non-alphanumeric characters | 4,006 | 0.096% | rules_fixable (garbage) / flag_only (decorative unicode) |
| `name` | Decorative 4-byte Unicode letterforms | 8 | 0.0002% | flag_only |
| `name` | CJK characters (US records) | 316 | 0.008% | flag_only |
| `name` | Arabic characters (US records) | 302 | 0.007% | flag_only |

---

## 13. Part 1.6 — Deterministic State×Industry Gap Detection

_Generated: 2026-06-13 | Script: `src/part1_gap_detection.py` | Source: `part0_companies_clean.parquet` + SUSB 2022 | Output: `data/processed/part2_gap_candidates.json`_

Cross-tab: `our_count / SUSB_count` per state×industry cell. Tier C states excluded. Industry labels mapped to NAICS sectors via `data/processed/part1_industry_naics_mapping.json`. Records with null state excluded from denominators; logged separately as `state_unknown_high_value`.

### Coverage scope

| Dimension | Value |
|---|---|
| States analyzed | 48 (Tier A: 23, Tier B: 25) |
| NAICS sectors analyzed | 19 |
| Total cells | 911 |
| HIGH_GAP cells (<10% coverage) | 18 |
| MODERATE_GAP cells (10–30%) | 301 |
| ADEQUATE cells (>30%) | 592 |

### HIGH_GAP cells (by sector)

| Sector | States in HIGH_GAP | Notes |
|---|---|---|
| Other Services (except Public Administration) | 17 | Includes Tier A: New Jersey (8.6%), Florida (9.7%) |
| Management of Companies and Enterprises | 1 | Delaware only (Tier B, 4.9%) — no NES equivalent, SUSB-only denom |

Other Services is the only nationally-consistent HIGH_GAP sector at state granularity. The 17-state spread is not a sampling artefact — it reflects structural under-capture of the physical-economy service sector (repair, personal care, religious/civic/membership orgs) across the dataset.

### MODERATE_GAP cells (top sectors by state count)

| Sector | States in MODERATE_GAP |
|---|---|
| Wholesale Trade | 48 |
| Retail Trade | 41 |
| Management of Companies and Enterprises | 40 |
| Accommodation and Food Services | 39 |
| Administrative and Support and Waste Management | 38 |
| Construction | 37 |
| Other Services (not HIGH_GAP states) | 30 |
| Transportation and Warehousing | 12 |
| Real Estate and Rental and Leasing | 10 |

Wholesale Trade, Retail, Accommodation, Construction, and Admin/Support are MODERATE_GAP across nearly all states. These are the sectors where the dataset has systematic (not state-specific) under-coverage — consistent with the NES+SUSB national findings in §10.

### State_unknown_high_value finding

| Size Band | Null-State Count |
|---|---|
| 51–200 | 7,787 |
| 201–500 | 2,536 |
| 501–1K | 1,026 |
| 1K–5K | 914 |
| 5K–10K | 270 |
| 10K+ | 528 |
| **Total (51+)** | **13,061** |

13,061 mid-market and enterprise records have no recoverable state post-cleanup. Tagged as `state_unknown_high_value` in `part2_gap_candidates.json`. Part 4 should include these in enrichment without a state filter — their website/industry gaps are still addressable.

### Part 2 scope guidance

319 gap candidate cells is too many for Part 2's $3 LLM budget to annotate exhaustively. Part 2 data-engineer should prioritize:
1. All 18 HIGH_GAP cells (especially the Tier A NJ and FL Other Services gaps)
2. MODERATE_GAP cells in Tier A states for the five priority sectors (Construction, Retail, Wholesale Trade, Accommodation & Food, Other Services)

ADEQUATE sectors (Information, Finance, Professional Services, Health Care) can be skipped — no commercial gap to annotate.

---

## 14. Commercial Significance Assessment

_Added: 2026-06-13 | Context: Part 1 findings reviewed against Firmable ICP and Sales Intelligence use cases_

Not all gaps matter equally to clients. Below is a ranked commercial reading of the Part 1.6 findings.

### Gaps that Firmable clients would feel daily

**1. Wholesale Trade — MODERATE_GAP in all 48 states**
The most commercially painful finding. Wholesale distributors are a core ICP for nearly every B2B sales team using intelligence tools. A nationwide shortfall means clients prospecting into distribution, manufacturing supply chains, or B2B resellers are working with an incomplete picture. This is a churn risk and a deal blocker for clients whose TAM includes wholesale or distribution.

**2. Retail Trade — MODERATE_GAP in 41 states**
Same commercial exposure for brands, CPG companies, payment processors, and anyone selling point-of-sale or retail tech. 41-state gaps in Retail are not niche — Retail is one of the highest-volume prospecting verticals for mid-market sales tools.

**3. Construction — MODERATE_GAP in 37 states**
Construction is a high-spend vertical for suppliers, equipment vendors, insurers, and fintech (construction lending). Territory-based field sales teams targeting this vertical are missing a significant slice.

**4. 13,061 mid-market/enterprise records with null state (post-cleanup)**
Quietly the most severe quality issue for Sales Intelligence. These are 51+ employee companies — the highest-value accounts — with no geographic anchor. They are invisible to territory-based filtering, regional health scoring, and geo-targeted outreach. See Section 1c and `part2_gap_candidates.json` → `state_unknown_high_value`.

**5. Delaware / Management of Companies — 4.9% coverage (HIGH_GAP)**
Delaware is the incorporation state for holding companies, PE-backed entities, and corporate HQ structures. With only 23 of 466 SUSB establishments captured, clients doing corporate-group mapping or PE deal sourcing are nearly blind in the state that matters most for that use case.

### What looks alarming but is lower commercial priority

**Other Services HIGH_GAP (17 states, <10% coverage)**: NAICS 81 includes auto repair, personal care, pet services — dominated by micro-businesses and sole operators. The SUSB benchmark overcounts here because it includes gig-economy operators that Sales Intelligence clients typically do not prospect. The gap is real but the commercial exposure is low. Verify against NES before ranking this above the Wholesale/Retail/Construction gaps.

### Recommended commercial priority order for Part 3

1. Wholesale Trade (nationwide, all client verticals)
2. Retail Trade (41 states, high-volume ICP)
3. Construction (37 states, high-value vertical)
4. State-unknown high-value records (cross-cutting, breaks geographic workflows for best accounts)
5. Delaware / Management of Companies (niche but high-signal for PE/HQ targeting ICPs)
