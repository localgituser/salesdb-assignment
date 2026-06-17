# SalesDB Regional Data Lead Assessment

## Overview
PoC for regional market coverage audit and enrichment pipeline against a 4.16M-record US company dataset.

## Deliverables by Part

| Part | Deliverable | File |
|------|-------------|------|
| Part 1 — Scope & Baseline | Baseline observations, fill rates, stratification, rule-vs-LLM split | `docs/part1-baseline.md` |
| Part 2 — Agentic Audit | Top 5 gaps, verifier spot-checks, trust calibration note | `docs/part2-audit.md` |
| Part 3 — Commercial Framing | ICE scoring, top-2 selection with reasoning | `docs/part3-commercial.md` |
| Part 4 — PoC Enrichment Pipeline | Cascade design, eval results, cost/trace summary | `docs/part4-enrichment.md` |
| Part 5 — Reusable Skill | Skill spec (coverage-audit) | `skills/coverage-audit/SKILL.md` |
| Part 6 — 90-Day Pod Plan | Thesis, metrics, Linear tickets, sequencing, risk | `docs/part6-90day-plan.md` |
| Traces | All LLM call logs | `data/processed/shared_observability.jsonl` |
| Enriched output | 288-record enriched batch | `data/enriched/part4_enriched_sample.parquet` |
| Eval | Ground truth + precision/recall runner | `evals/ground_truth.json`, `evals/eval_runner.py` |

## Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
```

## Repo Structure

```
├── config/project.yaml       — all tunable parameters (thresholds, budgets, paths)
├── data/
│   ├── raw/                  — source datasets (not in repo)
│   ├── processed/            — intermediate outputs (parquet, json, jsonl)
│   └── enriched/             — Phase 4 enriched output
├── docs/                     — assessor-facing write-ups, one file per Part
├── src/                      — pipeline modules (phase-organised)
├── prompts/                  — versioned LLM prompt templates
├── evals/                    — ground truth + eval runner
├── skills/ → .claude/skills/ — reusable skill specs (symlink)
└── docs/                     — all write-ups: Part 1–6 deliverables, strategy, schema, guidelines
```

## Running the Pipeline

```bash
# Part 0: Ingestion
python src/part0_ingestion.py

# Part 1: Baseline & Stratification
python src/part1_sampling.py

# Part 4: Enrichment & Eval
python src/part4_pipeline.py
python evals/eval_runner.py
```

## Cost Tracking
All LLM costs logged to `data/processed/shared_observability.jsonl` and summarized in `data/processed/shared_cost_tracking.json`.  
Self-imposed budget: **$10 total** — split per phase in `config/project.yaml` → `budget.per_phase_usd`.

## Part Summary

| Part | Description | Script | Budget |
|------|-------------|--------|--------|
| 0 — Ingestion | Infrastructure | `src/part0_ingestion.py` | $0 |
| 1 — Baseline & Stratification | Scope & Baseline | `src/part1_sampling.py` | $0 |
| 2 — Agentic Audit | Coverage & Quality Audit | `src/part2_audit.py` | $3 |
| 3 — Commercial Framing | Commercial Framing | (manual) | $0 |
| 4 — PoC Enrichment | Build the PoC Pipeline | `src/part4_pipeline.py` | $5 |
| 5 — Reusable Skill | Reusable Skill | (docs) | $0 |
| 6 — 90-Day Plan | 90-Day Pod Plan | (docs) | $0 |
