# Regional Data Lead Assessment — Execution Plan (v7)

**Brief source of truth**: `notes/Regional Data Lead — Market Coverage Audit & 90-Day Plan _ Notion.md`

Each phase below maps explicitly to its corresponding Part in the brief. Phase numbering (0–5) is internal; Part numbering (1–6) is what the assessors evaluate.

Total time budget: ~2-3 working days. Part 4 / Phase 4 gets the largest single share. If running behind, cut from the bottom of the priority list (Phase 5 → Phase 3 → Phase 2), never from Phase 4 or Phase 6.

Global LLM budget: **$10 total**, split per phase below. If a phase's sub-budget is exhausted, stop that phase's LLM calls, log it, and move on — never let an early overrun block Phase 4.

---

## Repo structure

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
│   ├── ground_truth.json   # 20-25 hand-labeled records — static, never regenerated
│   └── eval_runner.py
├── skills/
│   └── SKILL.md
├── notebooks/               # scratch only, nothing production lives here
├── requirements.txt
├── README.md
└── notes/
    └── strategy_v7.md
```

---

## Notion doc update schedule

Write to Notion **at the end of each phase**, not in one go at the end. Each checkpoint is listed in the phase below.

| Phase ends | Notion section to write |
|------------|------------------------|
| Phase 0 | Nothing yet — setup only |
| Phase 1 | **Part 1**: scope summary, sampling strategy, rule-vs-LLM split |
| Phase 2 | **Part 2**: top 5 gaps, traces summary |
| Phase 3 | **Part 3**: commercial framing, ICE table, top 2 picks with reasoning |
| Phase 4 | **Part 4**: PoC pipeline walkthrough, eval result (one number + one paragraph) |
| Phase 5 | **Part 5**: skill description, worked example invocation + output |
| Phase 6 | **Part 6**: 90-day pod plan (1–2 pages, uses real numbers from audit) |
| Final | Review: confirm all 6 Parts present in Notion before submitting |

---

## Phase 0 — Setup
**→ Brief: preamble / infrastructure (not a scored Part, but gates everything)**
Target: 30 min | Budget: $0

- Scaffold repo structure above.
- Load 4.25M dataset into DuckDB → Parquet (`data/processed/us_companies.parquet`).
- Pull Census CBP state/industry counts as the primary comparator.
- **5-minute sanity check only**: do state codes match format-wise? Are comparator numbers establishments or companies (rough order-of-magnitude, not a deep audit)? Note any mismatch in one sentence in `baseline_audit.md`.
- **External augmentation decision (state once, don't revisit)**: the brief explicitly permits augmenting with registry data, scraped web sources, or LinkedIn. Decision for this submission: use Census CBP as the sole comparator (free, stable, no scraping risk). Note this decision and its tradeoff (lower coverage ceiling, no entity-level enrichment from external sources) in the baseline doc.
- Set up `src/observability.py`: JSONL logger (timestamp, phase, model, tokens, cost, prompt_version, outcome) + running cost total written to `data/processed/cost_tracking.json`, checked at the start of each LLM phase script.

**Output:** working DuckDB/Parquet pipeline, logger stub, one-paragraph comparator note with augmentation decision.

**Notion:** nothing to write yet.

---

## Phase 1 — Baseline & Stratification
**→ Brief: Part 1 "Scope & Baseline"**
Target: 1-2 hrs | Budget: $0 (all rules-based)

Run aggregations: record counts, missingness, fill rates by attribute — nationwide and by state, also cut by `size` and `industry`.

**Candidate key analysis** (required by Part 1): check uniqueness of name+state, name+domain, and any synthetic ID columns. Report collision rate for each combination. Flag which combination is the most defensible candidate key and why — this is a data quality signal reviewers will look for.

Tier states by sample depth:
- **A** (≥100 records): full confidence
- **B** (30-99): directional, flag in outputs
- **C** (<30): excluded from ranked gap lists, listed in one appendix table in `baseline_audit.md`

Write `baseline_audit.md`:
- fill-rate tables (nationwide + by state)
- candidate key analysis table
- rules-vs-LLM split paragraph (e.g. URL/domain cleanup, regex normalization = rules; entity disambiguation, industry classification nuance = LLM)
- sampling/stratification approach (1 paragraph) — including *why* 15-record spot-checks per gap give a defensible signal (at expected gap prevalence ≥20%, n=15 yields ~95% power to detect the gap above noise)
- coverage parity definition: which attributes (name, website, industry, employee range, location), at what fill rates (e.g. ≥85% for name/state, ≥60% for website), at what accuracy standard, and how this varies by state tier (Tier A = full parity target, Tier B = directional target, Tier C = excluded)

**Output:** `baseline_audit.md`, `data/processed/sample_audit.parquet`

**→ Notion checkpoint (Part 1):** Write the US scope summary, sampling strategy, and rule-vs-LLM split. Keep it tight — 3–4 short sections, no prose padding. Pull numbers directly from `baseline_audit.md`.

---

## Phase 2 — Agentic Audit
**→ Brief: Part 2 "Agentic Coverage & Quality Audit"**
Target: 2-3 hrs | Budget: $3

**Separation of roles is the point here** — the brief explicitly tests trust calibration. Use the data-engineer subagent to produce gap candidates, then the verifier subagent to spot-check independently.

- **data-engineer subagent**: reads baseline tables + comparator, surfaces candidate gaps by state/industry/size. Output: `data/processed/gap_candidates.json`.
- **verifier subagent**: independently spot-checks 15 records per candidate gap against raw data. Produces `gap_findings.md`.
- Every model call logged to `data/processed/observability.jsonl` (prompt_version, model, latency, cost, outcome). This is the submission's trace artifact.
- `gap_findings.md` must contain, per gap: what's missing, how prevalent, how confident you are, and **"agent claimed X / spot-check found Y"** — even when they agree. Silent agreement suppresses a useful signal and is a trust-calibration fail.

**Output:** `gap_findings.md`, `data/processed/gap_candidates.json`, traces in `data/processed/observability.jsonl`

**→ Notion checkpoint (Part 2):** Write the agentic audit findings section. Include: top 5 gaps in a ranked table, one sentence per gap on prevalence and confidence, one paragraph on what the agent found vs what the spot-check confirmed or overturned.

---

## Phase 3 — Commercial Framing
**→ Brief: Part 3 "Commercial Framing"**
Target: 1 hr | Budget: $0 (no LLM needed)

- For each of the 5 gaps: 2-3 sentences — which ICP/persona feels it, which deals it costs, which churn signal it amplifies.
- Score using ICE (Impact / Confidence / Ease) — faster to apply than RICE under time pressure, and the brief accepts any stated framework.
- Pick top 2 gaps to close in 90 days; state reasoning in 2-3 sentences each.

**Output:** section in `gap_findings.md` or separate `commercial_framing.md`

**→ Notion checkpoint (Part 3):** Write the commercial framing section. Include the ICE table (5 rows), the top 2 picks with explicit reasoning. Compact beats comprehensive — aim for one page max.

---

## Phase 4 — PoC Enrichment Pipeline
**→ Brief: Part 4 "Build the PoC Enrichment Pipeline" (the main event)**
Target: 4-6 hrs | Budget: $5

> **Loom: start recording at the beginning of this phase.** Not after — the brief wants to see you direct agents in real time, and the Haiku→Sonnet escalation is the most assessor-relevant moment. Record in one take if possible; editing a 7-min Loom costs 30+ min you don't have. Target: capture at least one live escalation decision.

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

Hand-label **20-25 records** → `evals/ground_truth.json` (static, never regenerated programmatically).

**Required fields per labeled record:**
```json
{
  "original_name": "Acme Corp",
  "original_state": "TX",
  "enriched_field": "website",
  "ground_truth_value": "acmecorp.com",
  "pipeline_output_value": "acmecorp.net",
  "pipeline_confidence": 0.72,
  "label": "incorrect",
  "source": "manual Google search + visited site"
}
```
Labels must be one of: `"correct"` | `"incorrect"` | `"partial"`. Source must describe how you verified (not just "Google" — be specific enough that a reviewer could reproduce it).

`eval_runner.py`: precision/recall, no LLM calls. Report one number + one paragraph on where the pipeline is weakest.

**Output:** `poc_enriched_sample.parquet`, `eval_runner.py`, `ground_truth.json`, precision/recall number + paragraph

**→ Notion checkpoint (Part 4):** Write the PoC pipeline walkthrough. Include: cascade diagram or table, model choice rationale per stage, the eval result (precision/recall number), and the weakness paragraph. This is the highest-scrutiny section — don't rush it.

---

## Phase 5 — Reusable Skill
**→ Brief: Part 5 "Reusable Skill"**
Target: 1 hr | Budget: $0

Write `skills/SKILL.md` for the enrichment pipeline (more reusable than the audit — different markets can run it without modifying the audit logic).

**Required sections (all must be present):**
1. **Trigger conditions** — when should someone invoke this skill?
2. **Required inputs** — list every parameter (market/region, input file path, target enriched field, cost ceiling, model versions)
3. **Expected outputs** — file format, fields, what a "good" output looks like
4. **How to interpret results** — confidence bands, what `stage_resolved` values mean, when to trust vs. hand-check
5. **Known limitations** — where it fails, what data shapes break it
6. **Worked example** — one complete invocation with realistic inputs and the resulting output (can be a truncated sample)

**Bonus**: all market/region references must be parameterised, not hardcoded to US. A SEA analyst should be able to run this without modifying the skill file.

**Output:** `skills/SKILL.md`

**→ Notion checkpoint (Part 5):** Write the skill section. Include the trigger conditions, required inputs/outputs in a compact table, and paste the worked example invocation + output. One page max.

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

**→ Notion checkpoint (Part 6):** This phase IS the Notion write. Write it directly into Notion, keep it front-and-centre. Real numbers only — no placeholders.

---

## README.md (explicit deliverable)
**→ Brief: "setup, run, and reproduction instructions"**
Target: 20-30 min | Write last, after all phases complete

Required sections:
- **Setup**: venv creation, `pip install -r requirements.txt`, `ANTHROPIC_API_KEY` env var
- **Run**: phase-by-phase commands with expected outputs (copy from CLAUDE.md, verify they still work)
- **Reproduction**: how to re-run eval against `ground_truth.json`; how to re-run enrichment on a fresh batch
- **Data**: note that raw CSV is not in repo; include Kaggle link or download instructions
- **Cost**: note the $10 total budget and how to check current spend (`ObservabilityLogger`)

Do not skip this — it's a named deliverable in the brief's GitHub Repository section.

---

## Loom walkthrough
**→ Brief: "strongly encouraged; candidates who skip are at a disadvantage"**

Treat as mandatory. Record during Phase 4 — that's where the agentic dev loop is most visible and most relevant to the role.

- **Start**: beginning of Phase 4 (before first pipeline run)
- **Target length**: ≤7 min
- **Must show**: how you direct agents, how you read traces, how you make the Haiku-vs-Sonnet call decision in real time, the eval result
- **Do not**: edit heavily — one take is fine and honest; reviewers are assessing how you work, not production quality

---

## Trace artifact — single source of truth

All LLM call logs go to **`data/processed/observability.jsonl`**. This is the file cited in submission as the trace record. Do not create a separate `agent_traces.jsonl` — consolidate into observability.jsonl, filtered by phase tag if needed.

---

## Final assembly checklist

Before submitting, verify:

- [ ] `data/enriched/poc_enriched_sample.parquet` exists (200–1000 records)
- [ ] `evals/ground_truth.json` exists (20–25 records, hand-labeled, static)
- [ ] `data/processed/observability.jsonl` has entries for every LLM phase
- [ ] `skills/SKILL.md` has all 6 required sections
- [ ] `prompts/` has versioned prompt files referenced in observability log
- [ ] `README.md` covers setup, run, reproduction, data, cost
- [ ] Notion doc has all 6 Parts (check against brief's Notion section)
- [ ] Loom recorded and link ready
- [ ] GitHub repo link ready to share

---

## Cut list if behind schedule (in order matching brief's priority)
1. Phase 5 (Reusable Skill) — can be a stub if truly out of time
2. Phase 3 (Commercial Framing) — compress to 1-2 sentences per gap
3. Phase 2 (Agentic Audit) — reduce to top 3 gaps instead of 5
4. **Never cut Phase 4 or Phase 6**
