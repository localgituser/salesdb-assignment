# Part 4 Enrichment Run Report

_Generated: 2026-06-17 02:46 UTC_  
_Pipeline version: v2_  
_Records: 220_  
_Budget spent: $8.0026 / $8.00 ($-0.0026 remaining)_


## Enrichment Outcome Distribution

| Status | Count | % |
|--------|------:|--:|
| NO_CANDIDATE | 138 | 48% |
| FULLY_ENRICHED | 101 | 35% |
| PARTIALLY_ENRICHED | 49 | 17% |

## Stage Distribution

| Highest stage reached | Count | % |
|----------------------|------:|--:|
| Stage 0 only (budget/skip) | 86 | 30% |
| Stage 1/1b (Haiku search) | 35 | 12% |
| Stage 2 | 134 | 47% |
| Stage 3 (Haiku verify) | 2 | 1% |
| Stage 4 (Sonnet) | 31 | 11% |

## Fill Rate by Field

| Field | Originally null | Now filled | Fill rate |
|-------|---------------:|----------:|----------:|
| website | 214 | 77 | 36% |
| type | 212 | 133 | 63% |
| industry | 134 | 62 | 46% |
| size | 68 | 0 | 0% |

_Fill rate = newly filled ÷ originally null. Does not reflect pre-existing values carried through._

## Post-Enrichment Coverage (all schema fields)

Final coverage across all 220 enriched records after merging original + enriched values into `*_final` fields.

| Field | Pre-enrichment | Post-enrichment | Delta |
|-------|---------------:|----------------:|------:|
| `website` | 34% (74/220) | 63% (139/220) | +29pp |
| `industry` | 70% (154/220) | 98% (216/220) | +28pp |
| `type` | 35% (76/220) | 95% (209/220) | +60pp |
| `size` | 100% (220/220) | 100% (220/220) | — |
| `name` | 100% (220/220) | 100% (220/220) | — |
| `city` | 100% (220/220) | 100% (220/220) | — |
| `state` | 100% (220/220) | 100% (220/220) | — |

_`size`, `name`, `city`, `state` were not enrichment targets — shown for completeness._

## Source Data Reliability (`original_correct` by field × segment)

_Rows where `original_correct=True` — pipeline confirmed the source value was right. `False` — pipeline found a different (likely correct) value. `unknown` — field was originally null (no signal)._

| Field | Metric | enterprise | mid_market | smb | micro |
|-------|--------|-------|-------|-------|-------|
| **website** | correct | 5 | 6 | 3 | 0 |
| | incorrect | 8 | 6 | 6 | 0 |
| | reliability | 38% | 50% | 33% | — |
| **type** | correct | 15 | 13 | 8 | 7 |
| | incorrect | 4 | 4 | 4 | 2 |
| | reliability | 79% | 76% | 67% | 78% |
| **industry** | correct | 17 | 14 | 14 | 3 |
| | incorrect | 17 | 30 | 26 | 6 |
| | reliability | 50% | 32% | 35% | 33% |
| **size** | correct | 14 | 35 | 23 | 6 |
| | incorrect | 30 | 27 | 20 | 1 |
| | reliability | 32% | 56% | 53% | 86% |

## Source Data Reliability by Field × Size Band

| Field | Metric | 1-10 | 11-50 | 51-200 | 201-500 | 501-1K | 1K-5K | 5K-10K | 10K+ |
|-------|--------|-------|-------|-------|-------|-------|-------|-------|-------|
| **website** | correct/total | — | 3/9 | 2/7 | 4/5 | 1/4 | 2/6 | 2/3 | — |
| | reliability | — | 33% | 29% | 80% | 25% | 33% | 67% | — |
| **type** | correct/total | 7/9 | 8/12 | 9/11 | 4/6 | 2/2 | 9/11 | 3/4 | 1/2 |
| | reliability | 78% | 67% | 82% | 67% | 100% | 82% | 75% | 50% |
| **industry** | correct/total | 3/9 | 14/40 | 9/32 | 5/12 | 2/10 | 12/18 | 3/5 | 0/1 |
| | reliability | 33% | 35% | 28% | 42% | 20% | 67% | 60% | 0% |
| **size** | correct/total | 6/7 | 23/43 | 27/43 | 8/19 | 3/14 | 10/24 | 1/6 | — |
| | reliability | 86% | 53% | 63% | 42% | 21% | 42% | 17% | — |

## Business Operating Status

| Status | Count | % of batch |
|--------|------:|-----------:|
| Active | 167 | 58% |
| Defunct | 14 | 5% |
| Unknown | 107 | 37% |

_Closure signals observed:_

- `no_results`: 2

## B2B vs B2C by Segment

| Segment | B2B | B2C | Both | Unknown |
|---------|----:|----:|-----:|--------:|
| enterprise | 22 | 21 | 10 | 7 |
| mid_market | 35 | 25 | 5 | 11 |
| smb | 34 | 20 | 7 | 12 |
| micro | 3 | 2 | 3 | 71 |
| **total** | **94** | **68** | **25** | **101** |

## Review Queue Summary

**73 records** flagged for manual review (25% of batch).

| Field | Flagged records |
|-------|---------------:|
| website | 4 |
| type | 19 |
| industry | 15 |
| size | 20 |
| operating_status | 54 |

| Segment | Flagged | Total |
|---------|--------:|------:|
| enterprise | 19 | 60 |
| mid_market | 20 | 76 |
| smb | 29 | 73 |
| micro | 5 | 79 |

Review queue written to: `data/enriched/part4_review_queue.csv`