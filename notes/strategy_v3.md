# Regional Data Lead Assessment — Execution Plan (v6)

**Brief source of truth**: `notes/Regional Data Lead — Market Coverage Audit & 90-Day Plan _ Notion.md`

Each phase below maps explicitly to its corresponding Part in the brief. Phase numbering (0–5) is internal; Part numbering (1–6) is what the assessors evaluate.

Total time budget: ~2-3 working days. Part 4 / Phase 4 gets the largest single share. If running behind, cut from the bottom of the priority list (Phase 5 → Phase 3 → Phase 2), never from Phase 4 or Phase 6.

LLM budget: **self-imposed $10 ceiling** (the brief sets no budget — this is a discipline constraint). Per-phase caps live in `config/project.yaml` → `budget.per_phase_usd`. The phase headers below mirror those values; if they diverge, the YAML wins. If a phase's sub-budget is exhausted, stop that phase's LLM calls, log it, and move on — never let an early overrun block Phase 4.

**Tunable parameters** (gap-tier thresholds, geography tier cutoffs, platform blocklist, cascade thresholds, batch size limits, run scope, market dataset/comparator paths) all live in `config/project.yaml`. To rerun this plan against a different market, edit that YAML — no code changes required.

---

## Repo structure

```
├── config/
│   └── project.yaml          # all tunable parameters — single source of truth
├── data/
│   ├── raw/
│   ├── processed/
│   │   ├── us_companies.parquet        # Phase 0 output (raw, never modified)
│   │   ├── us_companies_clean.parquet  # Phase 1.5 output (rules-cleaned)
│   │   ├── sample_audit.parquet        # Phase 1 stratified sample
│   │   ├── gap_candidates.json         # Phase 1.6 output (annotated by Phase 2 data-engineer)
│   │   ├── observability.jsonl         # all LLM call traces
│   │   └── cost_tracking.json          # running cost totals
│   └── enriched/
│       └── poc_enriched_sample.parquet # Phase 4 output
├── src/
│   ├── config.py             # typed loader for project.yaml
│   ├── ingestion.py
│   ├── sampling.py
│   ├── rules.py              # Phase 1.5 deterministic cleanup
│   ├── comparator.py         # SUSB state-level comparison
│   ├── nes_comparator.py     # SUSB+NES combined industry comparison
│   ├── gap_detection.py      # Phase 1.6 state×industry cross-tab → gap_candidates.json
│   ├── pipeline.py           # Phase 4 cascade enrichment
│   ├── gate.py               # batch quality gate (Phase 4)
│   └── observability.py
├── prompts/
│   ├── audit_v1.txt
│   └── enrichment_v1.txt
├── evals/
│   ├── ground_truth.json     # 20-25 hand-labeled records (static)
│   └── eval_runner.py
├── notes/
│   ├── part1_baseline_observations.md
│   ├── gap_findings.md       # Phase 2 verifier output
│   └── strategy_v3.md        # this file
├── .claude/
│   ├── agents/               # data-profiler, data-engineer, verifier specs
│   └── skills/coverage-audit/SKILL.md
├── notebooks/                # scratch only, nothing production lives here
├── requirements.txt
└── README.md
```

---

## Phase 0 — Setup
**→ Brief: preamble / infrastructure (not a scored Part, but gates everything)**
Target: 30 min | Budget: $0

- Scaffold repo structure above.
- Load 4.25M dataset into DuckDB → Parquet (`data/processed/us_companies.parquet`).
- Pull external comparators: **SUSB 2022** (Statistics of U.S. Businesses — employer firms) + **NES 2023** (Nonemployer Statistics — sole proprietors/self-employed). Combined ~36.9M business universe.
- **Census CBP rejected**: CBP counts physical establishment locations, not legal companies. A multi-location company appears as N CBP records but 1 SUSB record — wrong denominator for a company-level audit.
- **5-minute sanity check only**: do state codes match format-wise? Are comparator numbers in the right order of magnitude? Note any mismatch in one sentence in `baseline_audit.md`.
- **External augmentation decision (state once, don't revisit)**: Decision for this submission: use SUSB + NES as the sole comparators (free, stable, no scraping risk). Tradeoff: NES 2023 / SUSB 2022 vintage mismatch means ratios are directional only; NES counts legal entities, our dataset may count practitioners individually. Documented in `data/processed/baseline_audit.md`.
- Set up `src/observability.py`: JSONL logger (timestamp, phase, model, tokens, cost, prompt_version, outcome) + running cost total written to `data/processed/cost_tracking.json`, checked at the start of each LLM phase script.

**Output:** working DuckDB/Parquet pipeline, logger stub, one-paragraph comparator note with augmentation decision.

---

## Phase 1 — Baseline & Stratification
**→ Brief: Part 1 "Scope & Baseline"**
Target: 1-2 hrs | Budget: $0 (all rules-based)

Run aggregations: record counts, missingness, fill rates by attribute — nationwide and by state, also cut by `size` and `industry`.

**Candidate key analysis** (required by Part 1): check uniqueness of name+state, name+domain, and any synthetic ID columns. Report collision rate for each combination. Flag which combination is the most defensible candidate key and why — this is a data quality signal reviewers will look for.

Tier states by sample depth:
- **A** (≥50,000 records): full confidence
- **B** (10,000–49,999): directional, flag in outputs
- **C** (<10,000): excluded from ranked gap lists, listed in one appendix table in `baseline_audit.md`

_Authoritative source: `.claude/skills/coverage-audit/SKILL.md` Geography tiering table. If these numbers diverge, the skill wins._

Write `baseline_audit.md`:
- fill-rate tables (nationwide + by state)
- candidate key analysis table
- rules-vs-LLM split paragraph (e.g. URL/domain cleanup, regex normalization = rules; entity disambiguation, industry classification nuance = LLM)
- sampling/stratification approach (1 paragraph) — including *why* 15-record spot-checks per gap give a defensible signal (at expected gap prevalence ≥20%, n=15 yields ~95% power to detect the gap above noise)
- coverage parity definition: which attributes (name, website, industry, employee range, location), at what fill rates (e.g. ≥85% for name/state, ≥60% for website), at what accuracy standard, and how this varies by state tier (Tier A = full parity target, Tier B = directional target, Tier C = excluded)

**Phase 1.5 — Deterministic Cleanup Gate** (no LLM, $0): Run `src/rules.py` before Phase 2 to produce `us_companies_clean.parquet`. Rules: state normalisation (case, abbreviation, city-leak recombine), website platform/institutional-TLD reclassification, founded pre-1800 null-out, name garbage/sentinel null-out, city junk null-out. Adds `rules_flags` column + three boolean flag columns (`has_non_latin_name`, `implausible_size_founded`, `has_shared_domain`). All Phase 2–4 scripts read from the clean parquet, not the raw one.

**Phase 1.6 — Deterministic Gap Detection** (no LLM, $0): Run `src/gap_detection.py` to produce the ranked gap candidate list via pure arithmetic — `our_count / SUSB_count` per state×industry and state×size band. Output: `data/processed/gap_candidates.json` (gap tier per cell: HIGH/MODERATE/ADEQUATE). This is SQL/Python only; no judgment calls. Phase 2 consumes this file as input — it does not re-derive gaps from SUSB.

**Output:** `baseline_audit.md`, `data/processed/sample_audit.parquet`, `data/processed/us_companies_clean.parquet`, `data/processed/gap_candidates.json`

---

## Phase 2 — Agentic Audit
**→ Brief: Part 2 "Agentic Coverage & Quality Audit"**
Target: 2-3 hrs | Budget: $3

**Separation of roles is the point here** — the brief explicitly tests trust calibration. The deterministic gap list already exists from Phase 1.6; Phase 2 is purely LLM judgment and spot-checks on top of it.

- **Input**: `data/processed/gap_candidates.json` (from Phase 1.6). Do not re-derive gaps from SUSB — that work is done.
- **data-engineer subagent**: for each gap candidate, uses LLM to add commercial reasoning, assess whether the gap is a sourcing gap vs. enrichment opportunity, and assign a confidence score. Annotates `gap_candidates.json` in-place (adds `reasoning`, `gap_type`, `confidence` fields).
- **verifier subagent**: independently spot-checks 15 records per candidate gap against raw data. Produces `notes/gap_findings.md`.
- Every model call logged to `data/processed/observability.jsonl` (prompt_version, model, latency, cost, outcome). This is the submission's trace artifact.
- `gap_findings.md` must contain, per gap: what's missing, prevalence, confidence, "agent claimed X / spot-check found Y" — even when they agree. Silent agreement suppresses a useful signal.

**Output:** `notes/gap_findings.md`, annotated `data/processed/gap_candidates.json`, traces in `data/processed/observability.jsonl`

---

## Phase 3 — Commercial Framing
**→ Brief: Part 3 "Commercial Framing"**
Target: 1 hr | Budget: $0 (no LLM needed)

- For each of the 5 gaps: 2-3 sentences — which ICP/persona feels it, which deals it costs, which churn signal it amplifies.
- Score using ICE (Impact / Confidence / Ease) — faster to apply than RICE under time pressure, and the brief accepts any stated framework.
- Pick top 2 gaps to close in 90 days; state reasoning in 2-3 sentences each.

**Output:** section in `gap_findings.md` or separate `commercial_framing.md`

---

## Phase 4 — PoC Enrichment Pipeline
**→ Brief: Part 4 "Build the PoC Enrichment Pipeline" (the main event)**
Target: 4-6 hrs | Budget: $5

Build cascade in `src/pipeline.py`. **Fill this table in before writing code:**

| Stage | Task | Model | Why |
|---|---|---|---|
| 1 | Deterministic rule match (regex, domain reconstruction) | none | rules win on structured, predictable patterns |
| 2 | Targeted search/lookup | none (API/search) | cheap, deterministic retrieval |
| 3 | Verify search result matches company name/location | Haiku | cheap classification, high volume, low ambiguity |
| 4 | Resolve ambiguous/conflicting cases | Sonnet | nuanced judgment, lower volume |
| (optional) | Hardest edge cases only | frontier | rare, highest cost — only if Sonnet confidence low |

**Retries and fallbacks — explicit state machine** (required by Part 4):
- Stage 3 low confidence → escalate to Stage 4 (Sonnet) exactly once
- Stage 4 uncertain → mark `status: unresolved`, move on; do not retry
- Source missing at Stage 2 → skip to Stage 3 with null evidence; Haiku notes evidence gap
- Cost ceiling hit mid-batch → stop cleanly, write `status: budget_exhausted` for remaining records, log in observability

- Structured output per record: enriched fields + `confidence` score + `stage_resolved` + `status`
- Rule layer (Stage 1) must run before any model call — no exceptions
- Run on 200-1000 records → `data/enriched/poc_enriched_sample.parquet`

### Eval (included in above block)
- Hand-label **20-25 records** → `evals/ground_truth.json` (static, never regenerated programmatically)
- `eval_runner.py`: precision/recall, no LLM calls. One number + one paragraph on weakness.

**Output:** `poc_enriched_sample.parquet`, `eval_runner.py`, `ground_truth.json`, precision/recall number + paragraph

---

## Phase 5 — Reusable Skill
**→ Brief: Part 5 "Reusable Skill"**
Target: 1 hr | Budget: $0

- `.claude/skills/coverage-audit/SKILL.md` for the enrichment pipeline (more reusable than the audit — different markets can run it without modifying the audit logic).
- Must cover: trigger conditions, required inputs, expected outputs, how to interpret results, known limitations, one worked example invocation + output.
- Bonus: the skill should be runnable on a different market (e.g., SEA country) without modification — parameterise market/region, not hardcode US.

**Output:** `.claude/skills/coverage-audit/SKILL.md`

---

## Phase 6 — 90-Day Pod Plan
**→ Brief: Part 6 "The 90-Day Pod Plan"**
Target: 1-2 hrs | Budget: $0

Write **last**, using real numbers from Phases 1-4. Must match brief's exact format (1-2 pages max):

- **Thesis** — 1 paragraph. The bet, why now, what success looks like.
- **3 measurable outcomes** — metric, starting value (from audit), day-90 target.
- **6-8 work items** — Linear-ticket format, effort (S/M/L), dependencies noted. Each item must specify the agent or tool augmenting it (e.g. "data-engineer subagent runs nightly gap scan") — the brief specifies "agent-augmented work items," not just human tasks.
- **30/60/90 sequencing** — with explicit go/no-go gate at day 30 (continue / kill / pivot criteria).
- **One risk, one bet** — what could break the plan; what you'd protect if budget halved.

**Output:** section in Notion doc (1-2 pages max)

---

## Loom walkthrough
**→ Brief: "strongly encouraged; candidates who skip are at a disadvantage"**

Treat as near-mandatory. Record while building Phase 4 — that's where the agentic dev loop is most visible and most relevant to the role. Target ≤7 min. Show: how you direct agents, how you read traces, how you make the Haiku-vs-Sonnet call decision in real time.

---

## Trace artifact — single source of truth

All LLM call logs go to **`data/processed/observability.jsonl`**. This is the file cited in submission as the trace record. Do not create a separate `agent_traces.jsonl` — consolidate into observability.jsonl, filtered by phase tag if needed.

---

## Final assembly

- `README.md`: setup, run instructions, reproduction steps
- Notion doc: Parts 1-6 in brief's order, tight
- Loom (≤7 min): record during Phase 4, show the agentic loop live

---

## Cut list if behind schedule (in order matching brief's priority)
1. Phase 5 (Reusable Skill) — can be a stub if truly out of time
2. Phase 3 (Commercial Framing) — compress to 1-2 sentences per gap
3. Phase 2 (Agentic Audit) — reduce to top 3 gaps instead of 5
4. **Never cut Phase 4 or Phase 6**
