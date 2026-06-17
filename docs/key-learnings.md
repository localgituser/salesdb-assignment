# Key Learnings & Build Journal
**Regional Data Lead Assessment | Kunal Kalra**

---

## Pre-work: System Setup

Before writing any pipeline code, the scaffolding went in first.

- 4 agent definitions in `.claude/agents/` — each locked to a single lane. `data-engineer` produces; `verifier` re-derives from raw SQL independently. When the verifier caught its own key-reference bug before it could check the engineer's work, that was the separation working.
- `config/project.yaml` — all tunable numbers in one place. Different market = change the YAML, not the code.
- `prompts/` — versioned. Changing a prompt = new version, logged in the trace.
- `data/processed/shared_observability.jsonl` — single JSONL file for all model calls, filtered by `part` tag. Easier to audit, easier to diff a re-run.
- Self-imposed **$10 budget ceiling** — the brief set no limit. The ceiling forced real Haiku vs Sonnet tradeoffs. Without one you can't know if the pipeline is commercially viable.

---

## Part 1 — Baseline & Stratification

**What I built**: `part1_baseline.py` profiled 4.16M records for fill rates, null patterns, and field quality. `part1_invalid_states.py` categorised every invalid/null state value — most were rules-fixable (case mismatch, city leaked into state field, abbreviation variants). `part1_sampling.py` built the stratified sample used downstream. `part1_comparator.py` + `part1_nes_comparator.py` ran the external benchmark comparison.

**Benchmark selection took three iterations**:
1. Census CBP — rejected. Counts physical locations, not legal companies. Wrong unit.
2. SUSB alone — misses ~30M non-employer firms. Sectors heavy in self-employment would show false gaps.
3. **SUSB + NES combined** — correct denominator. Changed which sectors read as real gaps vs. sourcing limits.

Write the benchmark rationale before running any comparisons. Getting it wrong at this step poisons everything downstream.

**Key gate added**: invalid-state exclusion rate rises with company size — 7.2% of 10K+ firms excluded. Flagged as a commercial gap before proceeding, not just a data cleaning footnote.

---

## Part 2 — Agentic Coverage & Quality Audit

**What I built**: `part2_audit.py` ran two models — Haiku for sector ranking (cheap classification), Sonnet for gap synthesis. `part2_verify.py` re-derived each gap candidate from raw SQL with no LLM calls. Total cost: $0.37.

**Pre-step** Step 1.6 data cleanup using deterministic means

**Decisions on field inspection**: Enum fields like `industry` — look at the tail (low-frequency values signal typos or duplicates). Free-text fields like `website` — look at high-recurrence values (scraper artefacts repeat). Applying the wrong lens to a field misses real signal.

**Blocklist gap caught during manual spot-check**: A massage practice and fitness studio both carried foreign government URLs (`betterhealth.vic.gov.au`, `wirral.gov.uk`) as their website. Blocklist only checked `.gov`; `.gov.au` and `.gov.uk` weren't caught. Found by reading actual records, not aggregate stats.

**Haiku without search = parametric guessing**: The model was classifying from company name alone. Without grounding to the company's actual web presence, confident outputs were still just inference from the name. Grounding is not optional.

**Small business records surfaced a deeper issue**: A meaningful share had no search results at all, appeared permanently closed, or were listed under a different name. Not an enrichment gap — no current web presence exists. The pipeline can't fix what isn't there.

**Verifier rule**: spot-checks are pure SQL, n=15 per gap, independently re-derived. No LLM in the verification pass. When verifier and engineer reach the same conclusion by different routes, confidence goes up. When they diverge, that's where you look.

---

## Part 3 — Commercial Framing

**What I built**: Gap prioritisation across the top 5 findings from Part 2, with a pre-pass domain audit that ran before any gap sizing.

**Pre-pass first**: Before framing any gap commercially, ran a DuckDB query across `part0_companies_clean.parquet` to find all platform/builder/social URLs counted as "has website." Found ~30 domain patterns that are null-equivalent — `godaddysites.com`, `business.site`, `myshopify.com`, BBB listings, email addresses stored as URLs, international `.gov` variants. These weren't in the original blocklist. Reclassifying them changed the true missing-website count before any gap was sized.

**Switched from ICE to MoSCoW**: ICE scores a ranking; MoSCoW asks the right question for a data product — *can we ship this to a customer without fixing it?* Must = no, we'd damage trust. Should = yes, but measurably worse. That distinction is more honest about what the product team actually needs to decide.

---

## Part 4 — PoC Enrichment Pipeline

**What I built**: A 4-stage cascade over 220 records — rules → Haiku + search → Haiku verify → Sonnet fallback. Every record exits with a `status`, `confidence`, and a log of which stage resolved it. Total cost: $8.00.

**Spike scripts before the full pipeline**: Built small test scripts in `scripts/` — one each for closure detection, size classification, and the facility flag. Ran each against 2–3 known cases. Model choices were based on observed output, not assumptions.

**Grounding fight**: The data-engineer agent kept defaulting to classifying from name alone, no web search. Had to push it explicitly to use Haiku with `web_search`. A model reading a company's actual website is a different thing to a model guessing from its name.

**`is_single_facility` flag**: Avera McKennan Hospital was returning Avera Health System's total headcount (~16K) instead of the hospital's (~1–5K). The prompt couldn't distinguish. Added the flag — when true, use location headcount; when false, use org-level. Caught via a specific named case.

**`coastal-forest-resources-company` bug**: Flagged "permanently closed" in Google Maps but pipeline returned null. Root cause: `max_uses=1` on the search call and `"permanently_closed"` not in the closure signals enum. Fixed both before scaling.

**`original_correct` field**: Asked the LLM to log whether it was filling a gap or correcting an existing value. Enterprise size in the source was correct only 32% of the time. Turned enrichment into a data quality benchmark on the source.

**Eval: 20 hand-labelled records** (enterprise + mid-market oversampled to ~21% of batch vs 1.65% of population — statistical power where the ICP is):

| Field | Pre → Post fill | F1 | Conf calibration (≥0.80) |
|---|---|---|---|
| industry | 70% → 98% | 0.77 | 77.8% |
| type | 35% → 95% | 0.92 | 94.1% ✅ |
| website | 34% → 63% | 0.75 | 70.0% ⚠️ |
| size | 100% → 100% | 0.44 ⚠️ | 57.1% ⚠️ |

**Size was gated, not shipped**: F1 of 0.44, but the real signal was confidence calibration — 57% correct at ≥0.80 confidence against an 80% target. The pipeline was claiming high confidence on wrong predictions. A field that ships with false confidence is worse than a missing field.

**Two size failure modes that look the same in aggregate**:
1. *Office vs. company*: "Office of Governor Josh Shapiro" — pipeline returned 11–50 at 85% confidence; ground truth was 201–500.
2. *Wrong size concept*: headcount at a specific office vs. total employees globally. Different numbers, often unsourceable from the same signal. This needs a product decision, not a better prompt.

---

## What I'd Carry Into an APAC Run

- Run a 5-line data shape check before any analysis — the global dataset mismatch should have been step zero.
- Write benchmark rationale before running comparisons. Three iterations on the US run; that reasoning should be first, not retrospective.
- Require loud failure in agent definitions from day one — one missing key caused a silent verifier failure. "Always write output explaining why you stopped" catches it immediately.
- Don't trust fill rate until platform URLs are stripped — true missing-website count was ~972K, not the headline number.
