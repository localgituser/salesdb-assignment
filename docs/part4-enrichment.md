# Part 4 — PoC Enrichment Pipeline

_Target fields: website, industry, type, size_  
_Batch: `data/processed/part1_sample_audit.parquet` (288 records across 4 size segments)_  
_Output: `data/enriched/part4_enriched_sample.parquet`_

---

## Pipeline Design

The cascade runs in `src/part4_pipeline.py`. All model calls log to `data/processed/shared_observability.jsonl`.

| Stage | What | Model | Why |
|-------|------|-------|-----|
| 0 | Rules — detect platform/institutional URLs, pass-through clean values | None | Deterministic, zero cost, handles the easy cases first |
| 1 | Search + extract — web search for company, extract website/type/size/industry_raw | Haiku + `web_search_20250305` | Live retrieval from real web; Haiku is cheap enough to run on all 209 missing/platform records |
| 1b | Parametric classify — industry/type/size from company name alone | Haiku (no search) | For 79 records that already have a website but missing industry; search not needed |
| 2 | Industry snap — fuzzy-match `industry_raw` to canonical 492-label taxonomy | None (deterministic) | Separates retrieval (Stage 1) from classification; no token cost |
| 3 | Verify — confirm candidate website belongs to company | Haiku (no search) | Catches entity mismatch (e.g. subsidiary vs parent); only fires when Stage 1 confidence < 0.72 |
| 4 | Resolve — full-context resolution for uncertain/conflicting fields | Sonnet | For unresolved conflicts only (~18% of records per design; Stage 4 share flagged if >40%) |

**Model choice rationale**:
- **Haiku + web_search** for Stage 1: live retrieval without a separate search API key. The `web_search_20250305` first-party tool executes server-side — one API call gets search + extraction. Avoids the CLAUDE.md warning against Perplexity (consumer wrapper with latency variance); Anthropic's tool has predictable structured output.
- **Haiku** for Stage 3: website verification is binary (matches company or doesn't). High volume, unambiguous — no reasoning chain needed.
- **Sonnet** for Stage 4: entity disambiguation, subsidiary vs parent calls, conflicting evidence — requires multi-step reasoning Haiku doesn't reliably do. Volume is ~18% of batch.

---

## Retry / Fallback State Machine

```
Stage 1    → confidence < 0.72 for website: escalate to Stage 3 (verify)
Stage 3    → website_verified=False: escalate to Stage 4 (Sonnet), once
             website_verified=True: upgrade confidence, skip Stage 4
Stage 4    → uncertain: status=unresolved, move on (no retry)
Budget hit → stop cleanly; write status=budget_exhausted for remaining records
Stage 1b   → missing_industry only: no search; Stage 3/4 only if type/size confidence < 0.60
```

Every transition is logged to `data/processed/shared_observability.jsonl` with `phase`, `model`, `stage`, `handle`, `cost`, `outcome`.

---

## Sample Composition

288 unique records (handle-deduped from 300 target quota):

| Segment | N | missing_website | missing_industry | platform_url |
|---------|---|-----------------|------------------|--------------|
| Enterprise (500+) | 60 | 30 | 18 | 12 |
| Mid-market (51–500) | 76 | 40 | 20 | 16 |
| SMB (11–50) | 73 | 40 | 18 | 15 |
| Micro (1–10) | 79 | 40 | 23 | 16 |

Enterprise oversampled to ~21% of records vs 1.65% of population — gives statistical power on the primary ICP. Micro pre-filtered for HIGH_CHURN_RISK (size=1-10 + founded≥2015 + no website + no type).

---

## Enrichment Fields and Output Schema

Four target fields per record, with full lineage:

| Column | Description |
|--------|-------------|
| `{field}_original` | Value in source before this run |
| `{field}_enriched` | Pipeline's candidate value (may differ from original) |
| `{field}_final` | Write-back value (enriched if found, else original passthrough) |
| `{field}_original_correct` | `true` = pipeline agrees with stored value; `false` = conflict; `null` = was already null |
| `{field}_confidence` | 0.0–1.0 float from the resolving stage |
| `{field}_pipeline_stage` | `rules` / `haiku` / `haiku_parametric` / `sonnet` / `NO_CANDIDATE` |
| `{field}_review_flag` | `true` when confidence is medium or a conflict was detected |
| `enrichment_status` | `FULLY_ENRICHED` / `PARTIALLY_ENRICHED` / `NO_CANDIDATE` / `CONFLICT` / `ERROR` |
| `stage_resolved` | 1 / 1b / 2 / 3 / 4 — highest stage that fired |
| `status` | `completed` / `budget_exhausted` / `error` |

The `{field}_original_correct` column is the **data validity audit trail**: even for records that already had values, the pipeline scores whether those values are correct. Over time, aggregate correctness rates by field × size band give a live signal of source data reliability — not just what's missing, but how wrong the existing values are.

---

## Eval Results

_Ground truth: `evals/ground_truth.json` (20 hand-labeled records, static, never regenerated programmatically)_  
_Runner: `evals/eval_runner.py` (deterministic, no LLM calls)_

| Field | Precision | Recall | F1 | TP | FP | FN |
|-------|-----------|--------|----|----|----|----|
| website | 0.750 | 0.750 | 0.750 | 12 | 4 | 4 |
| type | 0.900 | 0.900 | 0.900 | 18 | 2 | 2 |
| industry | 0.600 | 0.600 | 0.600 | 12 | 8 | 8 |
| size | 0.375 | 0.375 | 0.375 | 6 | 10 | 10 |
| **macro** | **0.656** | **0.656** | **0.656** | — | — | — |

**Per-segment website precision**: enterprise P=0.80, mid-market P=0.667

**Weakness analysis**: The pipeline has two distinct failure modes. First, size is the weakest field (P=0.38) because web search returns the **parent organization's** headcount, not the specific entity's: searching for "Avera McKennan Hospital" surfaces Avera Health System (10K+) rather than the individual hospital (1K-5K). This is structural — enriching subsidiary-level employee counts from public web sources requires entity disambiguation at a granularity that Haiku's web search doesn't reliably achieve in one pass. Second, industry precision (P=0.60) suffers from near-synonym confusion in the 491-label taxonomy: the model returns "government relations" instead of "government administration" and "higher education" instead of "primary and secondary education" — taxonomically adjacent, but wrong. Website precision (P=0.75) is bounded by the same parent/subsidiary problem: the pipeline correctly identifies the organization but picks the canonical root domain (avera.org) rather than the entity-specific subdomain (averamckennan.org). Type precision (P=0.90) is the cleanest signal — binary classification from clear signals like "LLC", "School District", "Federal Agency" is reliable. The pipeline should be trusted for type enrichment and treated with caution for size and granular industry within large healthcare and government org charts.

---

## Cost & Traces

Budget: $5.00 (from `config/project.yaml` → `budget.per_part_usd.part_4`)  
Cost tracker: `data/processed/shared_cost_tracking.json` → key `part_4`  
Trace log: `data/processed/shared_observability.jsonl` filtered by `"phase": "part_4"`

Stage 4 cost signal: if Stage 4 (Sonnet) accounts for >40% of resolved records, the cascade is over-relying on the expensive model — indicates Stage 1 search quality needs improvement or Stage 3 confidence threshold needs tuning.

**Cost estimate pre-run** (based on dry run at $0.006/record):
- Stage 1 (Haiku + search, 209 records): ~$1.25
- Stage 1b (Haiku parametric, 79 records): ~$0.10
- Stage 3 (Haiku verify, ~30% of Stage 1): ~$0.20
- Stage 4 (Sonnet, ~18% of Stage 3 escalations): ~$0.15
- **Projected total**: ~$1.70 of $5.00 budget

**Actual cost**: $2.38 of $5.00 budget used (288 records × ~$0.008/record average). Stage breakdown: 228 records resolved at Stage 1 (Haiku+search), 2 at Stage 3 (Haiku verify), 58 at Stage 4 (Sonnet) = 20.1% Sonnet share — within the 40% cost-signal threshold. Total project spend: $2.76 of $10.00 ceiling.
