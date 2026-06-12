# SalesDB Regional Data Lead Assessment

## Overview
PoC for regional market coverage audit and enrichment pipeline.

## Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Repo Structure
- `data/raw/` — Source datasets
- `data/processed/` — Aggregations, samples, audit logs
- `data/enriched/` — PoC enriched output
- `src/` — Pipeline modules
- `prompts/` — LLM prompt templates
- `evals/` — Ground truth and evaluation runner
- `skills/` — Reusable skill documentation
- `notebooks/` — Scratch/exploration only

## Phases

### Phase 0: Setup
- Scaffold repo (done)
- Load 4.25M dataset → DuckDB → Parquet
- Pull one comparator (Census CBP)
- Setup observability logger

### Phase 1: Baseline & Stratification
- Aggregations by state/industry/size
- Tier states by sample depth (A/B/C)
- Output: `baseline_audit.md`, `sample_audit.parquet`

### Phase 2: Agentic Audit
- Single audit agent surfaces gaps
- Fixed 15 spot-checks per gap
- Output: `gap_findings.md`, `agent_traces.jsonl`

### Phase 3: Commercial Framing
- ICE score top 5 gaps
- Pick top 2 with reasoning
- Output: commercial framing section

### Phase 4: PoC Enrichment Pipeline
- Cascade: rules → search → Haiku → Sonnet/frontier
- 200-1000 record sample
- Eval: 20-25 hand-labeled, precision/recall
- Output: `poc_enriched_sample.parquet`, eval results

### Phase 5: Reusable Skill
- `skills/SKILL.md` documenting pipeline

### Phase 6: 90-Day Pod Plan
- Thesis, metrics, work items, sequencing, risks

## Running the Pipeline
```bash
# Phase 0: Ingestion
python src/ingestion.py

# Phase 1: Baseline
python src/sampling.py

# Phase 4: Enrichment & Eval
python src/pipeline.py
python evals/eval_runner.py
```

## Cost Tracking
All LLM costs logged to `data/processed/observability.jsonl` and summarized in `data/processed/cost_tracking.txt`.

Budget: $10 total, split per phase in strategy_v3.md.
