# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SalesDB Regional Data Lead Assessment** — A PoC pipeline for market coverage audit and enrichment of a 4.25M-company dataset. The project executes in 6 sequential phases:

- **Phase 0**: Ingestion (CSV → DuckDB → Parquet)
- **Phase 1**: Baseline & Stratification (fill-rate audit, state tiering)
- **Phase 2**: Agentic Audit (surface gaps via LLM)
- **Phase 3**: Commercial Framing (ICE score top gaps)
- **Phase 4**: PoC Enrichment Pipeline (cascade: rules → search → Haiku verify → Sonnet fallback)
- **Phase 5**: Reusable Skill documentation

**Key constraint**: Hard $10 total LLM budget across all phases. Cost must be logged and checked per phase.

**Note on Phase 6**: The 90-Day Pod Plan is a Notion deliverable, not a code phase — no script in `src/` corresponds to it. It's written last, informed by outputs from Phases 1-4.

## Tech Stack

- **Data**: DuckDB (in-memory SQL), Pandas, Polars
- **ML/LLM**: Anthropic SDK (Claude Haiku, Sonnet, frontier models)
- **Validation**: Pydantic v2
- **Python**: 3.9+
- **Environment**: Virtual environment (`venv/`), managed via `requirements.txt`

## Subagents

This project uses two subagents defined in `.claude/agents/`:

- **data-engineer** — produces work: Phase 2 gap candidates (`gap_candidates.json`), Phase 4 enrichment cascade output (`poc_enriched_sample.parquet`). Never marks its own output as verified.
- **verifier** — checks work: Phase 2 spot-checks (15 records per gap candidate, independent re-derivation from raw data → `gap_findings.md`), Phase 4 eval (`eval_runner.py`, precision/recall). Never produces new gaps or enrichments, never edits the data-engineer's output files.

**Invoke explicitly** — auto-delegation is unreliable. E.g.:
- "Use the data-engineer subagent for Phase 2 gap detection"
- "Use the verifier subagent to spot-check the Phase 2 gap candidates"

**Phase 3 (commercial framing) and Phase 5 (SKILL.md) are not delegated to subagents** — they are manual/Claude tasks with $0 LLM budget.

**Never let one agent do both roles for the same phase.** The separation is the point — it's how trust calibration gets demonstrated (Part 2 of the brief).

Verifier calls (spot-checks, eval_runner) do not count against the phase's LLM budget — they're read-only/deterministic by design.

## Context Hygiene (avoid burning tokens)

- **Never read the raw CSV or full Parquet files into context.** Use DuckDB SQL queries that return aggregates, `.head()`, or `LIMIT`-bounded samples only.
- When inspecting `data/processed/observability.jsonl` or other large JSONL/JSON outputs, grep/filter for the relevant phase or gap_id — never cat the whole file.
- When checking dataset schema or distributions, query DuckDB directly (`SELECT state, COUNT(*) FROM ... GROUP BY state`) rather than loading into pandas and printing.

## Before re-running any LLM phase

Check `data/processed/observability.jsonl` for existing entries tagged with that phase. If entries exist, **ask the user before re-running** — re-running an LLM phase consumes budget again from the fixed $10 total, and there's no automatic carryover or refund.



### Phase-Based Execution Model

Each phase is a standalone script in `src/`. They run sequentially but independently — no shared state between them except through output files. Phases 0–1 are rules-based (no LLM); Phases 2–4 use LLM calls.

**Key files**:
- `src/ingestion.py` — Load CSV into DuckDB, export to Parquet
- `src/sampling.py` — Stratify by state/industry/size, tier states (A/B/C), candidate key analysis
- `src/rules.py` — Deterministic cleanup (URL/domain, regex normalization)
- `src/pipeline.py` — Cascade enrichment (rules → search → Haiku → Sonnet), with explicit retries/fallback state machine
- `src/observability.py` — Cost tracking and logging

### Observability & Cost Tracking

**Critical design**: All LLM calls must log to `ObservabilityLogger`:

```python
from src.observability import ObservabilityLogger

logger = ObservabilityLogger()
logger.log_call(
    phase="phase_2",
    model="claude-3-5-haiku-20241022",
    tokens=1500,
    cost=0.0011,
    prompt_version="audit_v1",
    outcome="success",
    metadata={"gap_id": "TX_retail"}
)
```

Cost is tracked in `data/processed/cost_tracking.json` (running total + per-phase breakdown) and `data/processed/observability.jsonl` (per-call details). **Before running any LLM phase, check the budget**:

```python
logger = ObservabilityLogger()
phase_cost = logger.get_phase_cost("phase_2")
if phase_cost > PHASE_2_BUDGET:
    logger.info(f"Phase 2 budget exhausted. Cost: ${phase_cost:.4f}")
    sys.exit(1)
```

### Rules vs. LLM

**Rules-based enrichment** (Phase 1, Phase 4 first stage):
- URL/domain cleanup (regex, TLD validation)
- Format normalization (phone, postal codes)
- Deduplication (exact match)

**LLM-based enrichment** (Phase 2 audit, Phase 4 later stages):
- Entity disambiguation (company name variations)
- Industry classification nuance
- Semantic gap detection

This split is **intentional** — rules are deterministic and cacheable; LLM adds nuance where ambiguity exists.

### Stratification & Tiering

States are tiered by sample depth:
- **Tier A** (≥100 records): Full confidence, include in ranked gap lists
- **Tier B** (30–99): Directional, flag in outputs
- **Tier C** (<30): Exclude from ranked lists, append to audit tables

This tiering is defined in Phase 1 and referenced throughout.

### Sampling & Ground Truth

- `data/processed/sample_audit.parquet` — Stratified sample used for audit
- `evals/ground_truth.json` — 20–25 hand-labeled records for Phase 4 eval

**Important**: Ground truth is **static and hand-curated**. Never regenerate or modify it programmatically.

## Running the Pipeline

### Setup
```bash
source venv/bin/activate  # Use venv/ (not .venv/)
```

### Phase 0: Ingestion
```bash
python src/ingestion.py
# Output: data/processed/us_companies.parquet
```

### Phase 1: Baseline & Stratification
```bash
python src/sampling.py
# Output: data/processed/baseline_audit.md, data/processed/sample_audit.parquet
```

### Data Sanity Check (ad-hoc)
```bash
python data_sanity_check.py  # Quick state/industry/size distribution
```

### Phase 4: Enrichment & Evaluation
```bash
python src/pipeline.py   # Cascade enrichment
python evals/eval_runner.py  # Precision/recall against ground_truth.json
# Output: data/enriched/poc_enriched_sample.parquet, eval results
```

## Key Files & Output Artifacts

### Data Files
- `data/raw/` — Source datasets (not in repo, loaded from Kaggle)
- `data/processed/us_companies.parquet` — Main dataset (Parquet format)
- `data/processed/baseline_audit.md` — Fill-rate tables, sampling strategy
- `data/processed/sample_audit.parquet` — Stratified sample for audit
- `data/processed/observability.jsonl` — Line-delimited LLM call logs
- `data/processed/cost_tracking.json` — Running total + per-phase cost breakdown (single JSON object)
- `data/enriched/poc_enriched_sample.parquet` — Enriched records post-Phase 4

### Documentation
- `prompts/audit_v1.txt` — LLM prompt for Phase 2 gap detection
- `prompts/enrichment_v1.txt` — LLM prompt for Phase 4 enrichment
- `notes/strategy_v3.md` — Full execution plan with budgets, timelines, and brief Part mapping
- `skills/SKILL.md` — (Phase 5) Reusable skill documentation (enrichment pipeline, market-parameterised)

## Important Patterns & Constraints

### Dataset Metadata

The 4.25M company dataset has these characteristics (from Phase 0 sanity check):
- **State field**: Contains non-standard codes; flag any mismatches vs. Census CBP comparator
- **Website field**: Variable format (URL, domain, malformed)
- **Industry field**: High cardinality; normalization is LLM-friendly
- **Size field**: Categorical (S/M/L, or employee ranges — check schema)

Inspect via `data_sanity_check.py` for updated state/industry distributions.

### Candidate Key Analysis (Phase 1 requirement)

Phase 1 must evaluate candidate keys — this is explicitly required by Part 1 of the brief. Check uniqueness of:
- `name + state`
- `name + domain`
- Any synthetic ID column

Report collision rate per combination, identify the most defensible candidate key, and note it in `baseline_audit.md`. Do this with DuckDB GROUP BY + COUNT(*) — no LLM needed.

### Trace Artifact — Single Source of Truth

All LLM call logs go to **`data/processed/observability.jsonl`**. This is the submission's trace record. Do not create a separate `agent_traces.jsonl` — consolidate everything into `observability.jsonl`, filtered by `phase` tag when inspecting. The data-engineer agent definition of done references this file.

### Budget Enforcement

- **Phase 0–1**: $0 (rules only)
- **Phase 2**: $3 (agentic audit)
- **Phase 3**: $0 (commercial framing, no LLM)
- **Phase 4**: $5 (enrichment cascade, evals)
- **Phase 5**: $0 (skill documentation, rules-based/manual — no LLM needed)

If a phase's budget is exhausted, **stop LLM calls and log it**, never carry over budget from a later phase.

### Output Compliance

- All Markdown outputs (`baseline_audit.md`, `gap_findings.md`, etc.) must be **human-readable** and include:
  - Timestamp
  - Execution parameters (model, phase, sample size)
  - Summary statistics or tables
  - One-paragraph weakness analysis or limitations
- JSONL logs must have one complete JSON object per line (no streaming)
- Parquet outputs must preserve all original columns plus new enriched fields

### Logging & Observability

Use Python's standard `logging` module for debug output (directed to stderr). Example:

```python
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

logger.info(f"Phase 1: loaded {record_count:,} records")
logger.warning(f"Tier C states (n<30): {tier_c_count}")
```

## Testing

This project is **data-centric**, not unit-test heavy. Validation happens at data boundaries:

- **Phase 0**: Sanity check (state codes, record counts vs. comparator)
- **Phase 1**: Tier distributions and fill-rate tables
- **Phase 4**: Precision/recall from `eval_runner.py` against ground_truth

If you add new rules or transformations, validate with a small sample (e.g., 100 records) before running full dataset.

## Common Development Tasks

### Run a single phase
```bash
python src/pipeline.py  # Phase 4
```

### Check cost status
```python
from src.observability import ObservabilityLogger
logger = ObservabilityLogger()
print(f"Phase 2 cost: ${logger.get_phase_cost('phase_2'):.4f}")
print(f"Total cost: ${logger.total_cost:.4f}")
```

### Inspect a Parquet file
```bash
python -c "import pandas as pd; print(pd.read_parquet('data/processed/us_companies.parquet').head())"
```

### Add a new rule
Edit `src/rules.py` and test on a small slice of `sample_audit.parquet` before running Phase 4 end-to-end.

### Modify prompts
Update `prompts/audit_v1.txt` or `prompts/enrichment_v1.txt`, increment version, and update the `prompt_version` parameter in the corresponding phase script and observability logger.

## Notes on Codebase State

- **Phases 0–1**: Core infrastructure (ingestion, observability, stratification) — stable, foundational
- **Phase 2–4**: Still under development (placeholder TODOs in `sampling.py`, `rules.py`, `pipeline.py`, `eval_runner.py`)
- **Phase 5**: Not started (will document reusable skill for audit or enrichment)

When extending, maintain the phase-based structure and **always log LLM costs** if introducing new LLM calls.

## Environment Variables

No `.env` file is required for the base pipeline. Anthropic API key is read from `ANTHROPIC_API_KEY` (set via your shell or system). If adding external integrations (search, Census API, etc.), document required env vars here.
