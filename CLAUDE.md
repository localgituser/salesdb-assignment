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

**Project parameters**: All tunable parameters (budget caps, gap-tier thresholds, geography tier cutoffs, platform blocklist, run scope, market dataset/comparator paths) live in `config/project.yaml` and are loaded via `src/config.py` (`CONFIG`). To run this project against a new market, edit that YAML — no code changes required. **Never hardcode these values elsewhere.**

**Self-imposed budget ceiling**: $10 total — chosen as a discipline constraint, not a brief requirement. Cost is logged and checked per phase. See `config/project.yaml` → `budget` for the authoritative split.

**Note on Phase 6**: The 90-Day Pod Plan is a Notion deliverable, not a code phase — no script in `src/` corresponds to it. It's written last, informed by outputs from Phases 1-4.

## Tech Stack

- **Data**: DuckDB (in-memory SQL), Pandas, Polars
- **ML/LLM**: Anthropic SDK (Claude Haiku, Sonnet, frontier models)
- **Validation**: Pydantic v2
- **Python**: 3.9+
- **Environment**: Virtual environment (`venv/`), managed via `requirements.txt`

## Subagents

This project uses three subagents defined in `.claude/agents/`:

- **data-profiler** — Phase 1 extended data quality auditing: field-type-aware distribution checks, cross-field consistency, null pattern analysis. Deterministic only (no LLM calls). Produces a Markdown section for `notes/part1_baseline_observations.md` and `data/processed/profiling_summary.json`.
- **data-engineer** — produces work: Phase 2 gap candidates (`gap_candidates.json`), Phase 4 enrichment cascade output (`poc_enriched_sample.parquet`). Never marks its own output as verified.
- **verifier** — checks work: Phase 2 spot-checks (15 records per gap candidate, independent re-derivation from raw data → `notes/gap_findings.md`), Phase 4 eval (`eval_runner.py`, precision/recall). Never produces new gaps or enrichments, never edits the data-engineer's output files.

**Invoke explicitly** — auto-delegation is unreliable. E.g.:
- "Use the data-engineer subagent for Phase 2 gap detection"
- "Use the verifier subagent to spot-check the Phase 2 gap candidates"

**Phase 3 (commercial framing) and Phase 5 (SKILL.md) are not delegated to subagents** — they are manual/Claude tasks with $0 LLM budget.

**Coverage audit workflow**: When running Phase 1 (data-profiler) or Phase 2 (data-engineer), consult `.claude/skills/coverage-audit/SKILL.md` for *workflow* definitions (stage roles, sampling strategy, enterprise weighting, coverage parity targets) and `config/project.yaml` for *numeric thresholds* (gap tier cutoffs, geography tier cutoffs, blocklist, run scope). The skill defers to the YAML when they disagree.

**Never let one agent do both roles for the same phase.** The separation is the point — it's how trust calibration gets demonstrated (Part 2 of the brief).

Verifier calls (spot-checks, eval_runner) do not count against the phase's LLM budget — they're read-only/deterministic by design.

**Skill & agent spec updates require user approval.** Never edit `.claude/skills/coverage-audit/SKILL.md` or any file in `.claude/agents/` without first showing the user the proposed change and getting explicit sign-off. Present: (1) what triggered the update, (2) the exact diff, (3) why it passes the promotion gate (pattern, not incident). Only proceed after the user approves.

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

Numeric thresholds (tier cutoffs, gap-tier ratios) live in `config/project.yaml`. Workflow context (sampling strategy, coverage parity targets, enterprise weighting) lives in `.claude/skills/coverage-audit/SKILL.md`. Don't duplicate values here.

Observed US dataset distribution (descriptive, not a threshold):
- Tier A: 23 states (84.2% of records); Tier B: 25 states (15.2%); Tier C + territories: excluded (see `markets.us.excluded_subregions` and `excluded_territories` in the YAML).

### Sampling & Ground Truth

- `data/processed/sample_audit.parquet` — stratified sample used for audit
- `evals/ground_truth.json` — hand-labelled records for Phase 4 eval (size range in `config/project.yaml` → `eval.{ground_truth_size_min, ground_truth_size_max}`)

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
- `data/processed/baseline_audit.md` — Phase 0 initial data discovery (global dataset mismatch finding; historical artifact)
- `data/processed/sample_audit.parquet` — Stratified sample for audit
- `data/processed/observability.jsonl` — Line-delimited LLM call logs
- `data/processed/cost_tracking.json` — Running total + per-phase cost breakdown (single JSON object)
- `data/enriched/poc_enriched_sample.parquet` — Enriched records post-Phase 4

### Documentation
- `prompts/audit_v1.txt` — LLM prompt for Phase 2 gap detection
- `prompts/enrichment_v1.txt` — LLM prompt for Phase 4 enrichment
- `notes/strategy_v3.md` — Full execution plan with budgets, timelines, and brief Part mapping
- `.claude/skills/coverage-audit/SKILL.md` — Coverage audit skill: market-parameterised workflow for internal profiling + external gap detection. Canonical source for gap tier thresholds, coverage parity targets, enterprise weighting, and sampling strategy.

## Important Patterns & Constraints

### Dataset Metadata (Phase 1 completed findings)

The 4.16M US record dataset (from Phase 1 baseline analysis):
- **Primary key**: `handle` — perfectly unique (0 collisions, 0 nulls). Use as the stable entity identifier for all joins, logging, and merge-back across Phases 2–4.
- **State field**: 3.32% of records have invalid/null state. Mostly recoverable via rules (case normalisation, abbreviation expansion, city-split recombination). True foreign records are a small fraction.
- **Website field**: ~910K missing + ~62,057 records store a platform/social/builder URL that is effectively NULL for Sales Intelligence. **True missing-website count is ~972K.** When computing fill rates or gap sizes, treat platform URLs as missing. Platform blocklist lives in `config/project.yaml` → `enrichment_rules.platform_blocklist` (institutional TLDs `.edu`/`.mil`/`.gov` also excluded at the rules layer).
- **Industry field**: 491 distinct labels; 3 semantic duplicate pairs covering ~329K records (LLM canonical merge needed). 341K records have no industry value.
- **Size field**: Clean enum; 8 valid bands. 4.49% null rate (missingness only, no OOV values).

### Candidate Key Analysis (Phase 1 — completed)

Analysis complete. Results:
- `handle`: 0 collisions, 0 nulls → **primary merge key**
- `name + state`: 17,618 duplicates (0.42% collision rate)
- `name + domain`: misleading — 908,947 null domains are each counted as unique

Use `handle` for all enrichment operations. `name + state` is acceptable as a human-readable secondary key with the known collision caveat.

### Phase 2 Gap Detection — Context for data-engineer

SUSB state-level comparison shows all 51 states are ADEQUATE (35–90% coverage). **Do not chase state-level breadth gaps — they don't exist.** Focus on sub-state dimensions:
- **industry × state**: Five HIGH/MODERATE_GAP sectors from SUSB+NES: Other Services (2.3% combined coverage), Construction (6.0%), Retail (6.3%), Wholesale Trade (18.6%), Accommodation & Food Services (27.9%)
- **size × state**: Enterprise (500+) accounts are only 1.65% of records and are structurally thin — a sourcing gap, not enrichment opportunity

Comparator source data: `src/comparator.py` (SUSB), `src/nes_comparator.py` (NES). Full analysis in `notes/part1_baseline_observations.md` Sections 8–10.

### Phase 4 PoC Scope — Context for data-engineer

Single-pass PoC against a size-stratified sample spanning all four enrichable segments. Source: `markets.us.dataset.sample` (currently `data/processed/sample_audit.parquet`, 288 records after handle dedup from 300 quota). Sample builder: `src/sampling.py`.

Segment quotas (300 target → 288 unique): enterprise 60, mid-market 80, SMB 80, micro 80. Enterprise (500+) is oversampled relative to population share (1.65%) to give the eval statistical power on the primary ICP. Within each segment, records are split across three enrichment-target conditions: 50% missing website, 30% missing industry, 20% website set to a platform/social/builder URL.

Pre-filters (applied at sampling time, not deferral):
- `size IS NULL` excluded (no anchor for segment assignment)
- `HIGH_CHURN_RISK` strict flag excluded for micro: `size='1-10' AND founded>=2015 AND website IS NULL AND type IS NULL` (~5,718 records)

Per-segment precision/recall in the Phase 4 eval is the actionable signal — tells us which size bands the cascade is trustworthy for. The earlier two-run framing (51+ first, micro/SMB deferred) was discarded; see `notes/part1_baseline_observations.md` §2b for rationale.

The enrichable size bands (all four segments) are listed in `config/project.yaml` → `markets.us.enrichable_size_bands`. The Phase 4 batch-quality gate (`src/gate.py::check_batch_quality`) uses this list to catch `size IS NULL` or unexpected band values — it no longer rejects sub-51 records.

### Phase 4 Eval Thresholds — Context for verifier

Thresholds live in `config/project.yaml` → `cascade.{stage4_cost_signal, confidence_threshold, confidence_calibration_target}`. Current values:
- **Stage distribution signal**: if Stage 4 (Sonnet) accounts for more than `stage4_cost_signal` (40%) of resolved records, flag as a cost signal — the cascade is over-relying on the most expensive model.
- **Confidence calibration target**: among records where `confidence >= confidence_threshold` (0.80), at least `confidence_calibration_target` (80%) should be correct per ground truth. Below this, the pipeline is over-claiming confidence.

### Trace Artifact — Single Source of Truth

All LLM call logs go to **`data/processed/observability.jsonl`**. This is the submission's trace record. Do not create a separate `agent_traces.jsonl` — consolidate everything into `observability.jsonl`, filtered by `phase` tag when inspecting. The data-engineer agent definition of done references this file.

### Budget Enforcement

Per-phase caps live in `config/project.yaml` → `budget.per_phase_usd` (total: `budget.total_usd`). Current split: Phase 2 = $3 (agentic audit), Phase 4 = $5 (enrichment cascade + evals), all others = $0.

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
logger.warning(f"Tier C states (n<10000): {tier_c_count}")
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

## DB Schema
- Whenever the user asks you to write, debug, or optimize SQL queries, you **must** reference the schema defined in `docs/db_schema.md`.
- Ensure all column names and data types exactly match that document.