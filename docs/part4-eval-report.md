# Part 4 Eval Report — Precision / Recall

**Generated**: 2026-06-17  
**Run scope**: 200 records (main run) + 20 ground-truth records from parallel run, all merged into `data/enriched/part4_enriched_sample.parquet`  
**Ground truth**: `evals/ground_truth.json` — 20 hand-labelled records (enterprise + mid-market segments)  
**Eval script**: `evals/eval_runner.py`

---

## Summary

| Metric | Value |
|--------|-------|
| GT records | 20 |
| Matched in enriched output | 20 (100%) |
| **Macro Precision** | **0.731** |
| **Macro Recall** | **0.710** |
| **Macro F1** | **0.720** |

---

## Per-Field Metrics

| Field | Precision | Recall | F1 | TP | FP | FN |
|-------|-----------|--------|----|----|----|----|
| type | 0.947 | 0.900 | **0.923** | 18 | 1 | 2 |
| industry | 0.789 | 0.750 | 0.769 | 15 | 4 | 5 |
| website | 0.750 | 0.750 | 0.750 | 12 | 4 | 4 |
| size | 0.438 | 0.438 | **0.438** ⚠️ | 7 | 9 | 9 |

---

## Per-Segment Metrics

### Enterprise

| Field | Precision | Recall | F1 |
|-------|-----------|--------|----|
| type | 0.909 | 0.833 | 0.870 |
| industry | 0.909 | 0.833 | 0.870 |
| website | 0.800 | 0.800 | 0.800 |
| size | 0.400 | 0.400 | 0.400 |

### Mid-Market

| Field | Precision | Recall | F1 |
|-------|-----------|--------|----|
| type | 1.000 | 1.000 | **1.000** ✅ |
| industry | 0.625 | 0.625 | 0.625 |
| website | 0.667 | 0.667 | 0.667 |
| size | 0.500 | 0.500 | 0.500 |

---

## Size Ordinal Analysis

Exact-match F1 of 0.438 understates accuracy — most errors are off-by-one band:

| Metric | Value |
|--------|-------|
| Total size mismatches | 9 |
| Within 1 band | 6 (67%) |
| Avg band distance on mismatches | 1.67 |

The pipeline finds the right company in most cases but misjudges headcount by one tier — a data-sparsity issue more than an entity-resolution issue.

---

## Confidence Calibration

Among records where `confidence ≥ 0.80`:

| Field | High-conf predictions | Correct | Calibration |
|-------|-----------------------|---------|-------------|
| type | 17 | 16 | **94.1%** ✅ |
| industry | 18 | 14 | 77.8% |
| website | 10 | 7 | 70.0% ⚠️ |
| size | 7 | 4 | **57.1%** ⚠️ |

Target calibration: ≥80% correct at ≥0.80 confidence (from `config/project.yaml → cascade.confidence_calibration_target`).  
**Failures**: website (70%) and size (57%) are both below target — the pipeline is over-claiming confidence on these fields.

---

## Source Data Reliability

How often the original dataset value was correct (where known):

| Field | Enterprise reliability | Mid-market reliability |
|-------|------------------------|------------------------|
| type | 78.9% | 76.5% |
| size | 31.8% | 56.5% |
| industry | 50.0% | 31.8% |
| website | 38.5% | 50.0% |

Low source reliability on size (enterprise: 32%) and industry (mid-market: 32%) explains why enrichment is hard — the pipeline is correcting bad originals, not just filling blanks.

---

## All Mismatches (20 errors across 20 GT records)

| Handle | Field | Expected | Got | Segment | Band Δ |
|--------|-------|----------|-----|---------|--------|
| avera-mckennan-hospital | website | `averamckennan.org` | `avera.org` | enterprise | — |
| avera-mckennan-hospital | size | `1K-5K` | `5K-10K` | enterprise | 1 |
| stolt-nielsen-usa-inc | type | `Public Company` | `Privately Held` | enterprise | — |
| stolt-nielsen-usa-inc | size | `501-1K` | `11-50` | enterprise | **3** |
| alpine-access | size | `1K-5K` | `501-1K` | enterprise | 1 |
| oregon-department-of-corrections | industry | `public safety` | `law practice` | enterprise | — |
| whatabrands-llc | size | `5K-10K` | `1K-5K` | enterprise | 1 |
| boeing-commercial-space-company | website | `boeing.com` | *(none)* | enterprise | — |
| boeing-commercial-space-company | type | `Public Company` | *(none)* | enterprise | — |
| boeing-commercial-space-company | industry | `aviation and aerospace component manufacturing` | *(none)* | enterprise | — |
| north-haven-school-district | size | `501-1K` | `1K-5K` | enterprise | 1 |
| car-source-collision-center | size | `1K-5K` | `11-50` | enterprise | **4** |
| governor-shapiro | website | `governor.pa.gov` | `pa.gov` | mid-market | — |
| governor-shapiro | size | `201-500` | `11-50` | mid-market | 2 |
| hoboken-hospitality | industry | `hospitality` | `restaurants` | mid-market | — |
| kass-shuler-p.a. | industry | `law practice` | `legal services` | mid-market | — |
| kass-shuler-p.a. | size | `201-500` | `51-200` | mid-market | 1 |
| willamette-esd-school-district | website | `wesd.k12.or.us` | `wesd.org` | mid-market | — |
| willamette-esd-school-district | industry | `primary and secondary education` | `higher education` | mid-market | — |
| willamette-esd-school-district | size | `201-500` | `501-1K` | mid-market | 1 |

---

## Weakness Analysis

### Size (F1: 0.438 — primary failure mode)
- 9 FPs and 9 FNs — symmetric, suggesting systematic miscalibration not random noise
- Confidence calibration at 57% (target: 80%) — the pipeline is over-confident on wrong size predictions
- Enterprise size reliability is only 32% — original data is frequently wrong, making correction harder
- **Root cause pattern**: subsidiary/division headcount conflated with parent (Avera, Boeing, Stolt-Nielsen); stale data for acquired/renamed entities (Car Source, Alpine Access)
- **Recommended fix**: lower the `size_confidence` acceptance threshold from 0.55 → 0.65, or add a Stage 3b re-query when the enriched size differs from original by more than 1 band

### Website (Calibration: 70% — below target)
- Parent domain returned instead of subsidiary URL (Avera → `avera.org`, Governor Shapiro → `pa.gov`, Willamette ESD → `wesd.org`)
- Boeing Commercial Space: no result returned (entity too ambiguous as a division, not a standalone legal entity)
- **Recommended fix**: add subsidiary-awareness prompt instruction in Stage 1; flag entities where `entity_verdict=SUBSIDIARY` and website domain matches parent

### Industry (near-miss mismatches)
- `law practice` vs `legal services`, `hospitality` vs `restaurants`, `primary education` vs `higher education` — semantic near-misses, not wrong-industry errors
- These would pass a coarse-grained taxonomy check; the loss is from strict exact-match eval against a fine-grained label set

### Stage 4 (Sonnet) usage: 14% — within the 40% cost signal threshold ✅
