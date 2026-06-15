# Part 4 — PoC Enrichment Pipeline Walkthrough
_Target gap: Construction (Gap 2) — state contractor licensing + website enrichment_  
_Output: `data/enriched/part4_enriched_sample.parquet` (288 records, 4 size segments)_

---

## Pipeline Design

The cascade runs in `src/part4_pipeline.py` against `data/processed/part1_sample_audit.parquet` (288 records after handle-dedup from 300 target).

| Stage | What | Model | Why |
|-------|------|-------|-----|
| 1 | Deterministic rule pass — blocklist, URL cleanup, state normalisation | None | Rules win on structured, predictable patterns; no token cost |
| 2 | Search/lookup — Google Places API or equivalent structured retrieval | None (API) | Cheap, deterministic retrieval; returns structured JSON |
| 3 | Verify search result matches company name + location | Haiku | High-volume classification; unambiguous match/no-match task |
| 4 | Resolve conflicting or low-confidence cases | Sonnet | Nuanced judgement on ambiguous entity matching; lower volume |

**Model choice rationale**: Haiku for Stage 3 because entity-matching against a known name+city+state is a binary classification task — 500 tokens in/out, no reasoning chain needed. Sonnet for Stage 4 because conflicting results (multiple Google Places hits, subsidiary vs. parent ambiguity) require multi-step reasoning the Haiku architecture doesn't reliably do.

---

## Retry / Fallback State Machine

```
Stage 1 → passes all records
Stage 2 → if source missing: skip to Stage 3 with null evidence (Haiku notes gap)
Stage 3 → confidence < 0.70: escalate to Stage 4 (once)
Stage 4 → uncertain: mark status=unresolved, move on (no retry)
Any stage → cost ceiling hit mid-batch: stop cleanly, write status=budget_exhausted for remaining records
```

Every transition is logged to `data/processed/shared_observability.jsonl` with `phase`, `model`, `stage_resolved`, `cost`, `latency`, `outcome`.

---

## Sample Composition

288 unique records (handle-deduped from 300-record target):

| Segment | N | missing_website | missing_industry | platform_url |
|---------|---|-----------------|------------------|--------------|
| Enterprise (500+) | 60 | 30 | 18 | 12 |
| Mid-market (51–500) | 80 | 40 | 24 | 16 |
| SMB (11–50) | 80 | 40 | 24 | 16 |
| Micro (1–10, churn-filtered) | 88 | 44 | 26 | 18 |

Enterprise is oversampled to ~21% of records despite being 1.65% of the population — gives the eval statistical power on the primary ICP.

---

## Structured Output Schema

Each enriched record adds the following columns to the base schema:

| Column | Type | Description |
|--------|------|-------------|
| `website_enriched` | VARCHAR | Discovered website URL (NULL if unresolved) |
| `industry_enriched` | VARCHAR | Canonical industry label (NULL if unresolved) |
| `confidence` | FLOAT | 0.0–1.0; from the model that resolved the record |
| `stage_resolved` | INT | 1–4 indicating which cascade stage produced the result |
| `status` | VARCHAR | `resolved`, `unresolved`, `budget_exhausted` |
| `enrichment_source` | VARCHAR | `rules`, `search`, `haiku`, `sonnet` |

---

## Eval Results

_Hand-labelled: `evals/ground_truth.json` (20–25 records, static)_  
_Runner: `evals/eval_runner.py` (no LLM calls)_

Results to be filled in after Part 4 run:

| Segment | Precision | Recall | Notes |
|---------|-----------|--------|-------|
| Enterprise | — | — | |
| Mid-market | — | — | |
| SMB | — | — | |
| Micro | — | — | |
| **Overall** | — | — | |

**Weakness paragraph**: _To be written from eval_runner.py output._

---

## Cost & Traces

Part 4 budget: $5.00 (from `config/project.yaml` → `budget.per_part_usd.part_4`)  
Cost log: `data/processed/shared_cost_tracking.json` → `part_4` key  
Trace log: `data/processed/shared_observability.jsonl` filtered by `"phase": "part_4"`

Stage 4 (Sonnet) cost signal: if Stage 4 accounts for >40% of resolved records, the cascade is over-relying on the expensive model — flag for calibration review.
