# Part 1 — Baseline Observations
_Generated: 2026-06-12 | Script: src/baseline_sql.py | Dataset: data/processed/us_companies.parquet_

---

## 1. Record Counts

| Metric | Value |
|---|---|
| Total raw records | 4,306,855 |
| **US records (in-scope)** | **4,164,063** |
| Null-state records (excluded) | 97,912 |
| Non-US records (excluded) | 44,880 |
| US share of file | 96.68% |

**Note**: `us_companies.parquet` is already filtered at Phase 0, so non-US and null-state records are a small residue. The effective working dataset is **4.16M US records**.

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

At 4.16M records, a full LLM pass is not feasible within the $10 budget. The agentic audit (Phase 2) and enrichment PoC (Phase 4) both require a statistically defensible sample that mirrors the real distribution.

### Phase 2 Audit Sample (~3,500 records)

Proportional stratified random sample across Tier A and Tier B states, weighting by record count within each state. Tier C excluded (record counts too thin for statistical conclusions).

| State Tier | States | Records per State | Total |
|---|---|---|---|
| Tier A | 23 | ~100 | ~2,300 |
| Tier B | 25 | ~50 | ~1,250 |
| **Total** | **48** | — | **~3,550** |

Within each state, records are stratified by **industry sector** (proportional to state distribution) and **size band** (to ensure enterprise records are not diluted — see over-sampling note below). This produces `data/processed/sample_audit.parquet`.

**Enterprise over-sampling**: Because 500+ employee records are only 1.65% of the dataset, naive proportional sampling would yield ~58 enterprise records across 3,550 — too thin for gap analysis. The audit sample targets a minimum of **50 enterprise records per Tier A state** and **20 per Tier B state**, drawn first before filling remaining quota proportionally. This ensures enterprise coverage gaps surface as first-class findings rather than statistical noise.

### Phase 4 Enrichment PoC Sample (~300 records)

A focused execution batch drawn from the audit sample, targeting the highest-ROI gap segments identified in Phase 2:
- 100 records from highest-gap states (Iowa, Kansas, West Virginia) with `website = NULL`
- 100 records from MODERATE_GAP industry sectors (Construction, Retail, Wholesale) with `industry = NULL`
- 100 records from enterprise/mid-market size bands (51–500, 500+) regardless of state

**Rationale**: This 300-record batch costs ~$0.50–1.50 in LLM tokens at Haiku rates, fits within the $5 Phase 4 budget with room for evaluation, and exercises all three cascade stages (rules → search → Haiku verify → Sonnet fallback) within a realistic cost envelope.

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
| type | 54.90% | ~1.88M | Low |
| founded | 45.90% | ~2.25M | Low |

**Key finding**: `website` is the biggest gap (~910K missing). `industry` is the second largest actionable gap (~341K missing). `type` and `founded` are both majority-missing but have low commercial value for Sales Intelligence — not priority enrichment targets.

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

**Coverage parity definition (size-stratified)**: Coverage targets must differ by company size — achieving 90% website fill on micro-businesses (<10 employees) is historically impossible and low-value; the same threshold on enterprise accounts is commercially unacceptable.

| Size Band | Website Fill Target | Industry Fill Target | Size Fill Target |
|---|---|---|---|
| Enterprise (500+ employees) | **≥ 99%** | **≥ 99%** | **≥ 99%** |
| Mid-market (51–500) | ≥ 95% | ≥ 97% | ≥ 98% |
| SMB (11–50) | ≥ 88% | ≥ 93% | ≥ 96% |
| Micro (<11) | ≥ 75% | ≥ 85% | ≥ 93% |

A state reaches overall coverage parity when all four size bands meet their respective thresholds. For gap-ranking purposes (Phase 2), **enterprise and mid-market gaps are weighted 3× vs. micro-business gaps** — a single enterprise record with missing website is worth three micro-business completions for Sales Intelligence ROI.

The flat aggregate thresholds (website ≥ 90%, industry ≥ 95%, size ≥ 97%) from best-covered Tier A states remain useful as a simple summary signal but should not be used for enrichment prioritisation decisions.

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
| Short/garbage names (`.`, `n/a`, `test`) | **Rules** | Simple length + blocklist filter — no ambiguity |
| Suspicious founding years | **Rules** | Clamp to 1800–2026 range — no judgement needed |
| Missing city (50K records) | **Rules** | Can be inferred from state + zip (if available) via lookup table |
| Exact-match deduplication | **Rules** | Identical name+state → merge or flag — deterministic |
| Missing website (~910K records) | **LLM + Search** | Requires external lookup — rules cannot infer a URL from a name |
| Industry classification gaps (~341K) | **LLM** | High-cardinality, context-dependent — rules misclassify edge cases |
| Industry inconsistencies (present but wrong) | **LLM** | Semantic judgement on company name/description — rules can't do this |
| Fuzzy entity deduplication | **LLM** | "IBM Corp" vs "International Business Machines" — needs embeddings or LLM |

---

## 7. Candidate Key Analysis

| Candidate Key | Distinct Values | Duplicates | Collision Rate | Nulls in Key |
|---|---|---|---|---|
| `handle` | 4,164,063 | **0** | **0.00%** | 0 |
| `name + state` | 4,146,445 | 17,618 | 0.42% | 132 |
| `name + domain` | 4,152,405 | 11,658 | 0.28% | **908,947** |

**Recommendation**: Use **`handle`** as the primary merge key for all enrichment operations. It is perfectly unique (0 collisions, 0 nulls) and should be treated as the stable entity identifier throughout Phases 2–4.

`name + state` is usable as a human-readable key with a known 0.42% collision caveat — adequate for deduplication checks but not safe for automated merge-back without handle confirmation.

`name + domain` appears to have a lower collision rate (0.28%) but is misleading: 908,947 records have no website, meaning their domain key is NULL, and `COUNT(DISTINCT (name, NULL))` treats each as unique. The real collision rate among records _with_ a website is higher. Do not use as a merge key.

---

## 8. SUSB State Coverage Comparison

_Source: US Census Statistics of U.S. Businesses (SUSB) 2022 (`us_state_6digitnaics_2022.csv`) vs `us_companies.parquet` | Script: `src/comparator.py`_

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

**Implication**: State-level breadth is not the problem. The dataset has adequate geographic coverage across all 50 states + DC. Phase 2 gap detection should focus on **sub-state dimensions** — industry × state or size × state — not missing states.

**Limitations**: SUSB counts legal "firms"; our data counts records (may include duplicates). Ratios are directional. SUSB 2022 vintage may not match our dataset vintage.

---

## 9. SUSB Industry Coverage Comparison

_Source: Statistics of U.S. Businesses (SUSB) 2022 national totals (State='00') vs `us_companies.parquet` | Script: `src/industry_mapper.py` | LLM: claude-haiku-4-5-20251001 ($0.01208)_

244 free-text industry labels (≥500 records each) were mapped to 20 NAICS 2-digit sectors via a single Claude Haiku call. Coverage = our records in that NAICS sector / SUSB national firm count.

### MODERATE_GAP sectors (under-represented vs. SUSB)

| NAICS | Sector | Our Records | SUSB Firms | Coverage % |
|---|---|---|---|---|
| 81 | Other Services (personal care, repair) | 89,652 | 729,236 | **12.3%** |
| 42 | Wholesale Trade | 51,703 | 277,932 | **18.6%** |
| 44-45 | Retail Trade | 170,759 | 645,404 | **26.5%** |
| 72 | Accommodation & Food Services | 160,435 | 574,723 | **27.9%** |
| 23 | Construction | 220,721 | 782,487 | **28.2%** |

These five sectors collectively represent ~1.6M SUSB firms we have only partial coverage for. They are the **primary Phase 2 gap candidates**.

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

_Source: Statistics of U.S. Businesses (SUSB) 2022 (employer firms) + Nonemployer Statistics (NES) 2023 (non-employer establishments) vs `us_companies.parquet` | Script: `src/nes_comparator.py`_

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

**Implication for Phase 2**: The combined analysis sharpens the gap narrative considerably:
1. The dataset is well-calibrated for the employer-firm professional economy (Information, Finance, Professional Services at 15–70%)
2. The genuine coverage gaps are in gig-economy/solo-operator sectors (Transportation 2%, Other Services 2.3%) and traditional physical economy (Construction 6%, Retail 6.3%)
3. These are sourcing gaps — they cannot be closed by enriching existing records. Requires additional data sources (trade registers, state contractor licenses, gig platform exports)

---

## Summary: What This Means for Phases 2–4

1. **Primary enrichment target**: `website` field (~910K missing). Closing this gap has the highest ROI for Sales Intelligence — a company without a website URL is effectively un-linkable to external data sources.

2. **Secondary target**: `industry` classification (~341K missing + unknown quality issues on present values). Needed for ICP filtering.

3. **Highest-priority states**: Iowa, Kansas, West Virginia, Mississippi, Arkansas (Tier B with worst avg fill). Tennessee and Oregon are the Tier A outliers worth targeting.

4. **Enterprise coverage gap**: Only 1.65% of records are 500+ employees — a structural thin-coverage issue for enterprise-focused Sales Intelligence use cases.

5. **Physical economy sectors are structurally under-represented**: Construction (6.0%), Retail (6.3%), Transportation (2.0%), Other Services (2.3%), and Admin/Support (3.6%) are all HIGH_GAP when measured against the full SUSB+NES universe. These gaps reflect the source platform's professional/digital bias — they are sourcing gaps, not enrichment opportunities.

6. **The Information over-index is explained, not bias**: The 379.7% SUSB-only figure drops to 69.4% when NES non-employers are included. Our dataset captures the digital non-employer economy well; it does not over-represent tech firms, it just sees sole-proprietor tech workers that SUSB misses.

7. **Rules cleanup first**: Short/garbage names, malformed URLs, suspicious founding years — clear these with `src/rules.py` before running any LLM passes to avoid wasting tokens on non-entities.

8. **Safe merge key established**: `handle` is the anchor for all enrichment writes.
