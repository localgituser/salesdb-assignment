# Regional Data Lead Assessment — Execution Plan (v5, working copy)

Total time budget: assume ~2-3 working days. Part 4 gets the largest single share. If running behind, cut from the bottom of the priority list (Part 5 → Part 3 → Part 2), never from Part 4.

Global budget: **$10 total**, split per phase below. If a phase's sub-budget is exhausted, stop that phase's LLM calls, log it, and move on — never let an early overrun block Part 4.

---

## Repo structure (final — no ambiguity)

```
├── data/
│   ├── raw/
│   ├── processed/
│   └── enriched/
├── src/
│   ├── ingestion.py
│   ├── sampling.py
│   ├── rules.py
│   ├── pipeline.py
│   └── observability.py
├── prompts/
│   ├── audit_v1.txt
│   └── enrichment_v1.txt
├── evals/
│   ├── ground_truth.json   # 20-25 hand-labeled records
│   └── eval_runner.py
├── skills/
│   └── SKILL.md
├── notebooks/               # scratch only, nothing production lives here
├── requirements.txt
└── README.md
```

---

## Phase 0 — Setup (target: 30 min, budget: $0)

- Scaffold repo structure above.
- Load 4.25M dataset into DuckDB → Parquet (`data/processed/us_companies.parquet`).
- Pull one comparator (e.g. Census CBP state/industry counts).
- **5-minute sanity check only**: do state codes match format-wise? Are comparator numbers establishments or companies (rough order-of-magnitude check, not a deep audit)? Note any mismatch in one sentence in `baseline_audit.md` — don't build fallback logic, just flag it.
- Set up `src/observability.py`: simple JSONL logger (timestamp, phase, model, tokens, cost, prompt_version, outcome) + a running cost total written to a file, checked at the start of each phase script.

**Output:** working DuckDB/Parquet pipeline, logger stub, one-paragraph comparator note.

---

## Phase 1 — Baseline & Stratification (target: 1-2 hrs, budget: $0, all rules-based)

- Run aggregations: record counts, missingness, fill rates by attribute — nationwide and by state, also cut by `size` and `industry`.
- Tier states by sample depth:
  - **A** (≥100 records): full confidence
  - **B** (30-99): directional, flag in outputs
  - **C** (<30): excluded from ranked gap lists, listed in one appendix table in `baseline_audit.md`
- Write `baseline_audit.md`:
  - fill-rate tables
  - rules-vs-LLM split paragraph (e.g. URL/domain cleanup, regex normalization = rules; entity disambiguation, industry classification nuance = LLM)
  - sampling/stratification approach (1 paragraph)
  - definition of "coverage parity" (attributes + target fill rate + how it varies by state — 1 paragraph)

**Output:** `baseline_audit.md`, `data/processed/sample_audit.parquet`

---

## Phase 2 — Agentic Audit (target: 2-3 hrs, budget: $3)

- Single audit agent reads baseline tables + comparator, surfaces candidate gaps by state/industry/size.
- Fixed spot-check: **15 records per candidate gap**, regardless of gap size (no scaled-depth logic — simplicity over completeness here).
- Log every call to `data/processed/agent_traces.jsonl` (prompt_version, model, latency, cost, outcome).
- Write `gap_findings.md`:
  - top 5 gaps, each with: what's missing, prevalence, confidence
  - explicit "agent claimed X / spot-check confirmed Y" table

**Output:** `gap_findings.md`, `agent_traces.jsonl`

---

## Phase 3 — Commercial Framing (target: 1 hr, budget: $0, no LLM needed)

- For each of the 5 gaps: 2-3 sentences — which ICP/persona feels it, which deals it costs, which churn signal it amplifies.
- Score with a stated framework (recommend ICE: Impact/Confidence/Ease — faster to apply than RICE under time pressure).
- Pick top 2, state reasoning in 2-3 sentences each.

**Output:** section in `gap_findings.md` or separate `commercial_framing.md`

---

## Phase 4 — PoC Enrichment Pipeline (target: largest single block — 4-6 hrs, budget: $5)

Build cascade in `src/pipeline.py`. **Model assignment table — fill this in first, before writing code:**

| Stage | Task | Model | Why |
|---|---|---|---|
| 1 | Deterministic rule match (regex, domain reconstruction) | none | rules win on structured, predictable patterns |
| 2 | Targeted search/lookup | none (API/search) | cheap, deterministic retrieval |
| 3 | Verify search result matches company name/location | Haiku | cheap classification, high volume, low ambiguity |
| 4 | Resolve ambiguous/conflicting cases | Sonnet | nuanced judgment, lower volume |
| (optional) | Hardest edge cases only | frontier | rare, highest cost — only if Sonnet confidence low |

- Build the cascade per the diagram (rules → search → Haiku verify → Sonnet/frontier fallback).
- Structured output per record: enriched fields + confidence score + which stage resolved it.
- Cost controls: per-record cost cap, fallback to "unresolved, flagged" status if exceeded.
- Run on 200-1000 records → `data/enriched/poc_enriched_sample.parquet`.

### Eval (target: included in above block)
- Hand-label **20-25 records** (not 50, not 500 — matches brief, realistic for time budget) → `evals/ground_truth.json`.
- `eval_runner.py`: precision/recall, no LLM calls. One number + one paragraph on weakness.

**Output:** `poc_enriched_sample.parquet`, `eval_runner.py`, `ground_truth.json`, one precision/recall number + paragraph

---

## Phase 5 — Reusable Skill (target: 1 hr, budget: $0)

- `skills/SKILL.md` for either the audit pipeline or enrichment pipeline (pick whichever is more reusable — likely enrichment).
- Must cover: trigger conditions, required inputs, expected outputs, how to interpret results, known limitations, one worked example invocation + output.

**Output:** `skills/SKILL.md`

---

## Phase 6 — 90-Day Pod Plan (target: 1-2 hrs, budget: $0)

Write this **last**, using real numbers from Phases 1-4. Must match brief's exact format:

- **Thesis** — 1 paragraph
- **3 measurable outcomes** — metric, starting value (from your audit), day-90 target
- **6-8 work items** — Linear-ticket sized, effort estimate (S/M/L), dependencies noted
- **30/60/90 sequencing** — with explicit go/no-go gate at day 30 (what you'd need to see to continue/kill/pivot)
- **One risk, one bet** — what could break the plan; the one thing you'd protect if budget halved

**Output:** section in Notion doc (1-2 pages max)

---

## Final assembly

- `README.md`: setup, run instructions, reproduction steps
- Notion doc: Parts 1-6 in brief's order, tight
- Loom (≤7 min): record while building Phase 4 if possible — most valuable part to show

## Cut list if behind schedule (in order)
1. Phase 5 (skill) — can be a stub if truly out of time
2. Phase 3 (commercial framing) — compress to 1-2 sentences per gap
3. Phase 2 (audit) — reduce to top 3 gaps instead of 5
4. Never cut Phase 4 or Phase 6