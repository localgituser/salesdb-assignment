# US Market Coverage Audit & 90-Day Plan

**Kunal Kalra · Regional Data Lead Assessment · June 2026**
**Tools**: Claude Code (Sonnet 4.6 + Haiku 4.5), DuckDB, Pandas, Anthropic SDK
**Repo**: [github.com/…] · **Budget spent**: $8.60 / $10.00 self-imposed ceiling

---

## Part 1 — Scope & Baseline

**Dataset**: 4.16M US company records (BigPicture 17M, filtered to US). States are the sub-region dimension — proxying APAC's country / sub-region shape exactly.

### Record counts

| Metric | Value |
|---|---|
| In-scope US records | 4,164,063 |
| Null / invalid state (excluded) | 142,792 (3.32%) |
| Effective working set | ~4.02M |

**Candidate key**: `handle` — 0 collisions, 0 nulls. Used as the stable merge key across all parts.

### Fill-rate snapshot

| Field | Missing / null-equivalent | Notes |
|---|---|---|
| Website | ~972K (23%) | ~62K additional platform/social URLs treated as null |
| Industry | ~341K (8%) | 491 labels, 3 semantic duplicate pairs covering 329K records |
| Size | ~4.49% | Clean enum, missingness only |
| State | 3.32% | Mostly rules-recoverable (case fold, city-leak fix, abbreviation expansion) |

### Sampling strategy

At 4.16M records, full-dataset LLM passes are cost-prohibitive. Stratified by state tier × industry × size band:
- **Tier A** (23 states, ≥100K records): 84.2% of records — sampled proportionally
- **Tier B** (25 states, 10K–100K): 15.2% — sampled with a floor to ensure representation
- **Tier C + territories**: excluded from gap rankings

Part 4 batch: 288 unique records (300 quota after `handle` dedup), segment-stratified: enterprise 60, mid-market 80, SMB 80, micro 80. Enterprise oversampled (population share 1.65%) to give eval statistical power on the primary ICP.

### Rules vs. LLMs

| Layer | What it handles |
|---|---|
| **Rules** (Part 1, Part 4 Stage 0) | State normalisation, URL/domain cleanup, platform-URL reclassification, industry semantic dedup, exact deduplication |
| **Haiku** (Part 4 Stage 1–3) | Entity resolution, operating status, industry classification — cheap per-call, high throughput |
| **Sonnet** (Part 4 Stage 4) | Ambiguous subsidiaries, multi-hop entity resolution, hard edge cases — fallback only |

Rules win wherever the logic is deterministic. LLMs only touch records where ambiguity exists and the commercial value justifies the cost.

### Coverage parity definition

A state is at parity when: website fill ≥70%, industry fill ≥75%, size fill ≥85% — across all enrichable size bands (11+ employees). State-level breadth gaps don't exist in this dataset (35–90% coverage across all 51 states); the real gaps are sector × state and size × state cross-cuts.

---

## Part 2 — Agentic Coverage & Quality Audit

**Agents used**: Haiku (sector ranking, 48 state × sector queries) + Sonnet (synthesis + gap narrative). All calls logged to `data/processed/shared_observability.jsonl`. **Part 2 LLM cost: $0.37**.

**Trust calibration**: Agent findings were independently re-derived by the verifier subagent using pure SQL (n=15 per gap, no LLM). Four of five gaps confirmed; one marked plausible pending sourcing data.

### Top 5 structural gaps

| Gap | Coverage | Verifier | Root cause |
|---|---|---|---|
| **1 — Transportation & Warehousing (NAICS 48-49)** | 1.99% | ✓ CONFIRMED | FMCSA / DOT carrier registries not ingested; NES inflates denominator (94% non-employers) but employer-firm gap is real |
| **2 — Construction (NAICS 23)** | 5.93% | ✓ CONFIRMED | State contractor licensing boards and permit databases not systematically ingested; 48-state uniformity signals sourcing miss, not quality issue |
| **3 — Retail Trade (NAICS 44-45)** | 6.19% | ✓ CONFIRMED | Franchise disclosure and state retail licensing not ingested; recoverable employer-firm layer is real |
| **4 — Enterprise sourcing volume (cross-cut)** | 1.65% of records | ~ PLAUSIBLE | Sourcing pipelines calibrated for SMB volume; enterprise firms require SEC, D&B, corporate hierarchy sources |
| **5 — Micro-firm website: trucking + restaurants** | 58% website fill (15–17 pts below segment avg) | ✓ CONFIRMED | Many operators are phone-first / offline; standard web discovery won't work — needs FMCSA contacts, food service licensing, reverse-phone append |

**Cross-gap pattern**: Four of five gaps share a common root — public regulatory registries (FMCSA, state licensing boards, franchise filings, SEC) have not been systematically tapped. These contain dense, employer-level signals in exactly the sectors B2B buyers prioritise.

---

## Part 3 — Commercial Framing & Prioritisation

**Framework**: MoSCoW — one question: *can we ship this data to a customer without fixing it?*

### Gap commercial impact

| Gap | ICP / Persona | Deal impact | Churn signal |
|---|---|---|---|
| Construction (Gap 2) | GC, sub-contractor, equipment finance AE | Sub-10% coverage in every state — no viable territory | CS can't run expansion playbooks; customer churns to Dodge Data or BuildZoom |
| Transportation (Gap 1) | Freight tech, fuel card, fleet service AE | Can't build a prospect list from current inventory | Outbound sequences fail; customer reports "bad data" |
| Retail (Gap 3) | POS, supply chain, staffing AE | Can't identify majority of retail SMB TAM | Quota attainment miss; AE escalates to CS |
| Enterprise sourcing (Gap 4) | ABM platform customer, enterprise AE | Not enough records to run an ABM campaign at scale | High-LTV segment disqualifies Firmable on TAM coverage |
| Micro website (Gap 5) | Last-mile logistics, restaurant supply, hospitality staffing | Systematic deliverability gaps in outbound sequences | Low reply rates; customer blames data quality |

### MoSCoW prioritisation

**Must (close before customer-facing ingest)**
1. **Construction** — 28% SUSB employer coverage, 48-state uniformity, no NES inflation ceiling. Largest recoverable population from a single registry sprint. Selected for Part 4 PoC.
2. **State null recovery** — 13K enterprise records invisible in state-filtered searches. Blocks all enrichment for those records.

**Should (next sprint)**
3. Transportation — FMCSA is a single federal API; high commercial signal for freight tech ICP.
4. Retail — franchise disclosure + state licensing; moderate complexity.

**Could**
5. Micro-firm website — alternative enrichment approach needed; lower commercial urgency than sector gaps.

**Won't (this window)**
- Enterprise sourcing volume — sourcing infrastructure change, not a pipeline fix. Cycle 2.

---

## Part 4 — PoC Enrichment Pipeline

**Target gap**: Construction + general firmographic enrichment (website, industry, type, size) across 220 records.

### Pipeline architecture

```
Record → Stage 0: Rules (blocklist, state norm, platform reclassify)
       → Stage 1: Haiku entity resolution + web search (max_uses=2)
       → Stage 1b: Domain verification (Haiku)
       → Stage 1.5: Entity verification gate (confidence threshold)
       → Stage 2: Structured enrichment extraction (Haiku)
       → Stage 3: Haiku verify (low-confidence records)
       → Stage 3b: Size re-query (>1 band delta from original)
       → Stage 3c: Closure verification
       → Stage 4: Sonnet fallback (hardest cases only)
```

**Model choice rationale**:
- **Haiku** — 85% of calls. Cheap ($0.0008/1K tokens), fast, accurate enough for entity matching and classification. Right tool for structured extraction where the answer exists in the retrieved text.
- **Sonnet** — 14% of calls (well within the 40% cost-signal threshold). Handles ambiguous subsidiaries, multi-hop entity resolution, hard edge cases where Haiku returns low confidence.
- **Rules layer** — runs before any LLM call. URL blocklist, state normalisation, platform reclassification, industry semantic dedup. Deterministic and free.

**Key design decisions made during iteration**:
- `_build_output` prefers original when populated — enrichment fills gaps, doesn't overwrite correct data
- `is_single_facility` classification gates size enrichment: hospital campuses and branch offices get location headcount, not parent org headcount
- `closure_signals` enum extended to include `"permanently_closed"` and `"acquired"` after Run 1 revealed these were being missed
- Domain-mismatch routing: when enriched website domain differs from `company_domain`, the record is flagged for manual review before ingest

### Run results (220 records)

| Metric | Value |
|---|---|
| Records processed | 220 |
| FULLY_ENRICHED | 101 (35%) |
| PARTIALLY_ENRICHED | 49 (17%) |
| NO_CANDIDATE | 138 (48%) |
| Stage 4 (Sonnet) usage | 14% ✅ (threshold: 40%) |
| Total Part 4 cost | $8.00 |

**Post-enrichment fill rate (newly filled ÷ originally null)**:

| Field | Fill rate |
|---|---|
| type | 63% |
| industry | 46% |
| website | 36% |
| size | 0% ⚠️ (pipeline issue — see eval) |

### Eval results (20 hand-labelled records)

| Field | Precision | Recall | F1 |
|---|---|---|---|
| type | 0.947 | 0.900 | **0.923** ✅ |
| industry | 0.789 | 0.750 | 0.769 |
| website | 0.750 | 0.750 | 0.750 |
| size | 0.438 | 0.438 | **0.438** ⚠️ |
| **Macro** | **0.731** | **0.710** | **0.720** |

**Where it's weak — one paragraph**:

Size is the primary failure mode. 9/9 mismatches are symmetric (equal FPs and FNs), signalling systematic miscalibration rather than random noise. Root cause: the pipeline conflates parent-org headcount with subsidiary headcount for hospital systems, division entities, and acquired companies. 67% of mismatches are off-by-one band — entity resolution quality, not a data ceiling. The fix is lower the size confidence acceptance threshold (0.55 → 0.65) and add a Stage 3b re-query when the enriched size diverges from the original by more than one band. Website calibration (70%) is below the 80% target due to parent-domain returns for subsidiaries — addressed by flagging `entity_verdict=SUBSIDIARY` records. Size is gated from customer output until precision clears 0.55.

---

## Part 5 — Reusable Skill: `coverage-audit`

**Location**: `skills/coverage-audit/SKILL.md` (symlinked from `.claude/skills/coverage-audit/SKILL.md`)

**What it does**: A two-stage market coverage audit workflow. Stage 1 runs internal data quality profiling (fill rates, null patterns, tier distribution). Stage 2 runs external gap detection against a government benchmark (SUSB, NES, ABS, BizFile — configurable). Designed so any team member or agent can invoke it on a new market by editing `config/project.yaml` — no code changes required.

**Trigger conditions**: new market onboarding, quarterly coverage refresh, pre-sales gap inquiry ("do we cover X in Y?"), post-enrichment validation.

**Inputs**: dataset path, geography column, size/industry column names, platform blocklist (from config), and optionally a comparator source for Stage 2.

**Outputs**: `docs/part1-baseline.md` (human-readable audit), `data/processed/part1_profiling_summary.json` (machine-readable counts), `data/processed/part1_sample_audit.parquet` (stratified sample for enrichment).

**Known limitations**: Stage 2 gap detection requires a comparable government benchmark — if one doesn't exist for the target market (e.g. some SEA sub-markets), Stage 1 still runs independently and produces actionable fill-rate findings. NES-based comparators inflate non-employer counts; the skill documents the correction and flags gig-economy sectors automatically.

**Example invocation**:
```
/coverage-audit market=US dataset=data/processed/part0_companies.parquet comparator=data/raw/susb_2021.csv
```
Produces gap rankings within ~$0.40 (Haiku-based audit, 48-state sweep) in under 10 minutes.

---

## Part 6 — 90-Day Pod Plan

### Thesis

The BigPicture dataset gives Firmable a 4.16M-record US starting point. This plan delivers a clean, enriched firmographic layer — not a sellable product on day 1, but the foundation of one. Success at day 90 is positive signal from at least one ANZ customer running a US motion, not revenue.

### Measurable outcomes

| Metric | Baseline (PoC) | Day 90 target |
|---|---|---|
| Website precision | P=0.75 (20-record eval) | P ≥0.85 (100-record eval) |
| Industry precision | P=0.79 (20-record eval) | P ≥0.85 (100-record eval) |
| Design partner signal | 0 | ≥1 ANZ customer with US footprint reporting positive feedback |

### Work plan

| Ticket | Size | Owner | Deps | Description |
|---|---|---|---|---|
| **T01 — Data cleanup** | XS | Data | — | Extend URL blocklist (GMB, e-commerce, URL shorteners); flag franchise domains; deduplicate 3 semantic industry label pairs across 4.16M records |
| **T02 — State null recovery** | XS | Data | T01 | Deterministic join of 124K null-state records against USPS city→state reference. Unblocks 13K enterprise records currently invisible in state-filtered searches. $0 model cost. |
| **T03 — Entity resolution spike** | M | ML | T01/T02 | Root cause the 48% NO_CANDIDATE rate and parent-vs-subsidiary conflation. Run targeted test batch against known failure cases. Goal: website P ≥0.85. |
| **T04 — Industry classification spike** | M | ML | T01 | Sibling-label confusion accounts for 5/5 industry eval mismatches. Test classification approaches. Goal: industry P ≥0.85. |
| **T05 — Deterministic type enrichment** | S | Data | — | Name-suffix rules (school districts, government agencies) + SEC ticker lookups. Reduce Sonnet/Haiku type calls by ≥30% without dropping P below 0.94. |
| **T06 — Low-signal exclusion** | XS | Data | T01 | Define and ship exclusion criteria for records with no resolvable public presence (stealth, placeholder, permanently closed). Spot-check before shipping. |
| **T07 — Eval expansion** | M | QA | T03/T04 | Expand ground truth 20 → 100 records across enterprise, mid-market, SMB. Add confidence calibration check to eval runner. At 20 records one miss moves a metric 8% — not defensible for a ship decision. |
| **T08 — Design partner validation** | S | Data+CS | T03/T04 | Route 50 enriched records to one ANZ customer with US territory. Three questions per record: website resolves? Right company? Would you use this in a sequence? |

### Sequencing

**Day 1–30 — Build & iterate**
T01, T02, T05, T06 ship in week 1 (deterministic, $0 model cost). T03 and T04 are spikes — run, measure, iterate within the sprint. Re-run the 288-record eval batch at day 20 for an updated precision score before the gate.

**Day 30 — Go / No-Go / Pivot**
- **Go**: website P ≥0.78 AND industry P ≥0.78 → proceed to Sprint 2
- **Pivot**: either metric 0.70–0.78 → one more iteration week before design partner validation
- **Kill / descope**: either metric below 0.70 → narrow to enterprise-only scope, diagnose root cause

**Day 31–60 — Validate & expand**
T07 (eval expansion) and T08 (design partner validation) run in parallel. Size spike runs if day-30 gate passes and capacity exists. Full-scale 30K pilot planned but not kicked off until design partner feedback clears.

**Day 61–90 — Ship**
30K pilot run if Sprint 2 gate passes (≥70% positive design partner feedback). Ingest into platform. Cycle 2 scoping begins: contact enrichment, `global_size` field, first-party size provider.

### Risk and bet

**Risk**: Size precision is structurally limited by public web data. If size doesn't clear 0.55 by day 30, gate it from customer output and communicate to CS before Sprint 2. The risk isn't a low score — it's shipping a low score silently.

**Bet**: If budget halves, protect T01–T04 and the 30K pilot. Website and industry are the primary ICP filter dimensions. A clean ingest with those two fields at P ≥0.85 — and size explicitly gated — is a credible first delivery. Size and contacts follow in cycle 2.

---

## Tooling & Agentic Dev Loop

| Layer | Tools used |
|---|---|
| IDE / agent orchestration | Claude Code (CLI) — main session + subagent routing |
| Data engine | DuckDB (in-process SQL), Pandas, Polars |
| LLM calls | Anthropic SDK — Haiku 4.5 (classification, extraction), Sonnet 4.6 (synthesis, fallback) |
| Observability | `shared_observability.jsonl` (per-call trace: model, tokens, cost, latency, outcome), `shared_cost_tracking.json` (running total) |
| Evals | `evals/eval_runner.py` — precision/recall against `evals/ground_truth.json` (20 hand-labelled records) |
| Version control | Git (conventional commits), GitHub |

**Subagent pattern used**: `data-engineer` produces; `verifier` checks. Never the same agent for both roles on the same part. This is how trust calibration gets demonstrated — the verifier re-derives findings independently from raw data via SQL, and marks each gap as CONFIRMED / PLAUSIBLE / REJECT before any finding is treated as fact.
