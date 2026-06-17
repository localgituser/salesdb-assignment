# US Market Coverage Audit & 90-Day Plan

**Kunal Kalra · Regional Data Lead Assessment · June 2026**

**Tools**: Claude Code (Sonnet 4.6 + Haiku 4.5), DuckDB, Pandas, Anthropic SDK
**Repo**: [[github](https://github.com/localgituser/salesdb-assignment)] 
**Loom**: [https://www.loom.com/share/9e813cdf76214c97bd8ede64da39ccd9]
**Budget spent**: $8.60 / $10.00 self-imposed ceiling

The brief asked for a working PoC over a polished deck. I built the pipeline first, wrote the plan second, and let the eval results shape both. The self-imposed $10 budget was a discipline constraint — it forced early decisions about where rules beat LLMs and where sampling beats exhaustive passes. Everything below is grounded in what the pipeline actually produced.

---

## Part 6 — 90-Day Pod Plan

### Thesis

The BigPicture dataset gives Firmable a 4.16M-record US starting point. This plan delivers a clean, enriched firmographic layer — not a sellable product on day 1, but the foundation of one. Success at day 90 is positive signal from at least one ANZ customer with US footprint, not revenue.

The PoC showed that website (P=0.75) and industry (P=0.79) are already within striking distance of a shippable threshold. The 90-day plan is structured around closing that gap with a focused entity resolution spike, then validating with a design partner before scaling.

PS: Firmable already has US data. This is a hypothetical scenario created for the purpose of this case study.

### **Core Assumption**

This plan was developed in isolation, without understanding Firmable’s current velocity or development stack. It should be reviewed by the team executing it to ensure it’s grounded in reality and not under- or over-estimating effort.

### Measurable outcomes

| Metric | Baseline (PoC) | Day 90 target |
|---|---|---|
| Website precision | P=0.75 (20-record eval) | P ≥0.85 (100-record eval) |
| Industry precision | P=0.79 (20-record eval) | P ≥0.85 (100-record eval) |
| Design partner signal | 0 | ≥1 ANZ customer with US footprint reporting positive feedback |

Size is explicitly excluded from day 90 targets — open web data has a structural ceiling and shipping a miscalibrated field silently is worse than shipping without it.

### Work plan

Three swim lanes: **Eng-1** (data/infra), **Eng-2** (ML/enrichment), **Eng-3** (product-facing/partner).

| Ticket | Size | Owner | Deps | Description |
|---|---|---|---|---|
| **T01 — Data cleanup + blocklist** | XS | Eng-1 | — | URL blocklist extension (GMB, .gov.au/.gov.uk foreign domains, shorteners); dedup 3 semantic industry label pairs; USPS city→state join for 124K null-state records (unblocks 13K mid-market and enterprise records, $0 model cost). Ships day 3. |
| **T02 — Schema mapping + ingest gate** | S | Eng-1 | T01 | Map BigPicture fields → Firmable canonical schema (enums, field names, nullability). Run cross-dataset entity match sample (BigPicture `handle` vs. Firmable's existing US entity graph) to size net-new vs. conflict population. Defines upsert strategy before any data touches production. Required before the 30K pilot has anywhere to land. |
| **T03 — Entity resolution spike (agent-run)** | M | Eng-2 | T01 | Root-cause the 48% NO_CANDIDATE rate. Agent loop: sample 50 known-failure records, iterate prompt + search strategy, score automatically after each cycle — human reviews results, not mid-loop execution. All iterations logged to `shared_observability.jsonl`. Target: website P ≥0.85. |
| **T04 — Industry classification spike (agent-run)** | M | Eng-2 | T01 | 5/5 industry eval mismatches are sibling-label confusion. Agent-driven classification test: feed the 20-record eval set through candidate prompt variants, score automatically, surface top-2 approaches for human sign-off. Target: industry P ≥0.85. |
| **T05 — Deterministic type enrichment** | S | Eng-1 | — | Name-suffix rules (school districts, government agencies) + SEC ticker lookups. Reduces Haiku/Sonnet type calls by ≥30% without dropping P below 0.94. |
| **T06 — Eval expansion + automated harness** | S | Eng-2 | T03/T04 | Expand ground truth 20 → 100 records (enterprise/mid-market/SMB/micro split). Wire `eval_runner.py` to run automatically on every enrichment batch and post results to the team channel. At 20 records one miss moves a segment metric 8% — not a ship decision. |
| **T07 — Staging ingest + quality gate** | M | Eng-3 | T02/T06 | Write enriched batch to a staging table. Automated checks: null rate delta, enum coverage, confidence distribution, fill rate vs. baseline. Fail batch if any metric regresses >5pp. Promote to prod only on pass. Required before 30K pilot. |
| **T08 — Design partner validation** | S | Eng-3 | T03/T04 | Route 50 enriched records to one ANZ customer with US territory. Three questions per record: website resolves? Right company? Would you use this in a sequence? ≥70% positive = Sprint 2 trigger. |

### Sequencing

**Day 1–30 — Build & iterate**
T01 and T05 ship in week 1 (deterministic, $0 model cost). T02 (schema mapping) runs in parallel — must complete before any pilot ingest. T03 and T04 are agent-run spikes with a human review gate every two days; agent logs all iterations, human reviews results. Re-run the 288-record eval batch at day 20 for an updated precision score before the gate.

**Day 30 — Go / No-Go / Pivot**
- **Go**: website P ≥0.78 AND industry P ≥0.78 → proceed to Sprint 2
- **Pivot**: either metric 0.70–0.78 → one more iteration week before design partner validation
- **Kill / descope**: either metric below 0.70 → narrow to enterprise-only scope, diagnose root cause

**Day 31–60 — Validate & expand**
T06 (eval expansion + automated harness), T07 (staging ingest gate), and T08 (design partner validation) run in parallel. 30K pilot scoped but not kicked off until T07 passes and T08 returns ≥70% positive feedback.

**Day 61–90 — Ship**
30K pilot runs through T07 staging gate → production ingest. Cycle 2 scoping begins: contact enrichment, `global_size` field, first-party size provider.

### Risk and bet

**Risk**: Size precision is structurally broken — P=0.44 in the PoC, with 43% of predictions wrong at ≥0.80 confidence. A miscalibrated confidence score is worse than no score; it gives downstream consumers false certainty. Size stays gated from customer output until it clears P≥0.55 with a calibrated confidence floor. If it doesn't clear by day 30, communicate to CS before Sprint 2 and scope it to Cycle 2 with a first-party data source.

**Bet**: If budget halves, protect T01, T03, T04, and T07. Website and industry are the primary ICP filter dimensions. A clean ingest at P≥0.85 on those two fields — with size explicitly gated and a staging gate preventing silent regression — is a credible first delivery. Contacts and size follow in Cycle 2.

---

## Part 1 — Scope & Baseline

**Goal**: Understand what we're working with before any enrichment spend. At 4.16M records you can't audit by hand, and you can't LLM-pass everything. The stratification strategy is itself a product decision.

**Dataset**: 4.16M US company records (BigPicture 17M, filtered to US). States are the sub-region dimension — proxying APAC's country / sub-region shape exactly.

| Field | Missing / null-equivalent | Notes |
|---|---|---|
| Website | ~972K (23%) | ~62K platform/social URLs also treated as null |
| Industry | ~341K (8%) | 491 labels; 3 semantic duplicate pairs covering 329K records |
| Size | ~4.49% | Clean enum, missingness only |
| State | 3.32% | Mostly rules-recoverable (case fold, city-leak, abbreviation expansion) |

**Candidate key**: `handle` — 0 collisions, 0 nulls. Used as the stable merge key across all parts.

**Sampling**: Stratified by state tier × industry × size band; Tier C states and territories excluded from gap rankings. Part 4 batch: 288 records across enterprise (60), mid-market (76), SMB (73), micro (79) — enterprise oversampled relative to its 1.65% population share to give the eval statistical power on the primary ICP. Full methodology in `docs/part1-baseline.md`.

**Coverage parity definition**: Website P ≥0.85, industry P ≥0.85 across Tier A/B states; size excluded from parity targets pending first-party data source. Tier C states and territories are excluded from gap rankings and parity measurement — coverage there requires registry ingestion, not enrichment. State fill rate ≥99% (rules-recoverable to that level deterministically).

**Rules vs. LLMs**:

| Layer | What it handles |
|---|---|
| **Rules** (Stage 0) | State normalisation, URL/domain cleanup, platform-URL reclassification, industry semantic dedup |
| **Haiku** (Stages 1–3) | Entity resolution, operating status, industry classification — cheap per-call, high throughput |
| **Sonnet** (Stage 4) | Ambiguous subsidiaries, multi-hop entity resolution — fallback only |

One counter-intuitive finding: the naive website fill rate (77%) overstates coverage because ~62K records store a platform URL (LinkedIn, GMB, Wix, URL shorteners) that passes format validation but resolves to no entity-specific content. The true missing-website count is ~972K — a 3× difference that changes every downstream gap prioritisation. Similarly, three semantic industry label pairs cover 329K records and inflate the apparent industry gap from ~65K to ~186K within the 11+ employee working set before deduplication.

---

## Part 2 — Agentic Coverage & Quality Audit

**Goal**: Surface structural gaps in coverage using agents, not by hand. Direct the agent, calibrate trust, verify independently before treating any finding as fact.

**Agents**: Haiku (sector ranking, 48-state × sector sweep) + Sonnet (synthesis). All calls logged to `shared_observability.jsonl`. **Part 2 cost: $0.37**.

**Trust calibration**: A separate verifier subagent re-derived every gap independently from raw data using pure SQL (n=15 per gap, no LLM), and assigned CONFIRMED / PLAUSIBLE / REJECT before any finding was treated as fact. Four of five gaps confirmed; one marked plausible. Over-trusting the agent and under-trusting it are both failure modes — the SQL spot-check is the checkpoint between them.

### Top 5 structural gaps

| Gap | Coverage | Verifier | Root cause |
|---|---|---|---|
| **1 — Transportation & Warehousing (NAICS 48-49)** | 1.99% | ✓ CONFIRMED | FMCSA / DOT carrier registries not ingested; employer-firm gap is real despite NES inflating the denominator (94% non-employers) |
| **2 — Construction (NAICS 23)** | 5.93% | ✓ CONFIRMED | State contractor licensing boards and permit databases not ingested; 48-state uniformity signals a sourcing miss, not a quality issue |
| **3 — Retail Trade (NAICS 44-45)** | 6.19% | ✓ CONFIRMED | Franchise disclosure and state retail licensing not ingested; recoverable employer-firm layer is real |
| **4 — Enterprise sourcing volume (cross-cut)** | 1.65% of records | ~ PLAUSIBLE | Sourcing pipelines calibrated for SMB volume; enterprise firms require SEC, D&B, corporate hierarchy sources |
| **5 — Micro-firm website: trucking + restaurants** | 58% fill (15–17 pts below segment avg) | ✓ CONFIRMED | Many operators are phone-first / offline; standard web discovery won't work — needs FMCSA contacts, food service licensing, reverse-phone append |

Four of five gaps share a single root cause: public regulatory registries (FMCSA, state licensing boards, franchise filings, SEC) have never been systematically tapped. That changes how you staff the fix — one sourcing pipeline engineer, not five separate enrichment projects. NES comparator choice is load-bearing for Transportation specifically: NES includes non-employer firms, making the gap look like 98% vs. the SUSB employer-firm gap of 65%. The distinction determines which gaps are recoverable via registry ingestion vs. structurally uncloseable without reaching sole operators.

### Manual spot-check observations

Two findings surfaced during hands-on record inspection and Google search verification — independent of the agent and Haiku passes.

**Website field corruption: private US businesses assigned foreign government domains.** Manual inspection found private US businesses with completely unrelated foreign government URLs stored as their `website` value: Better Health Massage Therapy had `betterhealth.vic.gov.au` (Victorian state government health portal, Australia); Aerobics Plus (Endicott, NY) had `wirral.gov.uk` (Wirral Council, UK local government). These passed through the rules stage uncaught because the `INSTITUTIONAL_TLDS` check only matches `.gov` — not `.gov.au` or `.gov.uk`. This is a precision risk, not just a coverage risk: the 80%+ "has website" fill rate includes an unknown count of corrupted domains the current blocklist doesn't catch. The 291K enrichment-queue figure is a lower bound.

**Small business records: low web presence confirmed by manual search.** Google searches on a sample of 1–50 employee records found a significant share returning no results at all, appearing only as a Google Maps listing with no associated website, appearing under a different name (rebrand/acquisition), or appearing to have closed entirely. This goes further than Gap 5's fill-rate signal — it confirms that for a material fraction of micro and small business records, a website to find doesn't exist, not just hasn't been sourced. Running website enrichment at scale against this cohort risks populating stale or wrong URLs at high volume.

---

## Part 3 — Commercial Framing & Prioritisation

**Goal**: Translate Part 2's sector gaps into a field-level fix sequence. One question per gap: *can we ship this data to a customer without fixing it?*

**Framework**: MoSCoW. Part 2 surfaced *where* coverage is thin (Construction 6%, Transportation 2%, Retail 6%). Part 3 reframes to *what to fix* — because the field dependency map determines sequencing more than sector priority does.

**Field dependency map**:
```
Cleanup pre-pass (blocklist extension, semantic dedup)
    └──> makes gap counts accurate; removes platform URL noise before enrichment runs

State recovery (deterministic city→state join)
    └──> unblocks website enrichment query precision (name + city + state vs. name + city only)

Website enrichment  ← upstream blocker for everything below
    └──> unlocks industry classification (homepage is the primary signal)
    └──> unlocks email_domain ($0, rules-derivable)
    └──> unlocks entity type inference for private/unknown
```

Website is the upstream blocker. Fixing Construction's sector gap without first fixing website fill rates means building on a distorted baseline. The enrichment cascade in Part 4 follows this map directly.

| Gap | Records affected | Commercial impact | MoSCoW | Rationale |
|---|---|---|---|---|
| **Cleanup pre-pass** (blocklist extension, semantic dedup, franchise domain flagging) | ~3K+ reclassified; 329K industry labels deduped | Every downstream metric is wrong without it — gap counts, enrichment queue size, fill rates | **Must** | $0; ships day 1; prerequisite for accurate gap measurement |
| **State null recovery** (deterministic city→state join) | 124K total / 13K enterprise | 13K enterprise records invisible in any state-filtered search; degrades website query precision for all enrichment | **Must** | $0 deterministic fix; no model calls |
| **Website enrichment** | ~972K missing (true count post-cleanup) | Upstream blocker for all other enrichment. No website = no industry signal, no email domain, no type inference. Every customer is affected regardless of vertical or ICP | **Must** | Selected for Part 4 PoC |
| **Industry enrichment** (genuinely null post-dedup) | 65K records | 65K records invisible in vertical ICP filters — the primary search dimension for Sales Intelligence | **Must** | Natural phase 2 of the same cascade as website |
| **Type — public companies** (SEC/ticker lookup) | ~40K | Deterministic, free, near-perfect precision. Closes a visible gap for ABM and securities-linked workflows | **Should** | Offline ticker join; $0 model cost; no dependencies |
| **Founded year** | ~2.25M | Secondary ICP signal; not a first-order filter; requires a paid structured source to recover | **Could** | Low ROI relative to the Must stack |
| **Type (private/unknown), Phone, Contacts** | — | Blocked on website availability or requires an external contact-data provider | **Won't** | Out of scope this window |

**On sector gaps (Part 2 findings)**: Construction, Transportation, and Retail share a single root cause — public regulatory registries (FMCSA, state licensing boards, franchise filings) have never been tapped. That is a **sourcing pipeline problem**, not a field enrichment problem. Closing Construction's 6% sector coverage requires registry ingestion in Cycle 2, not enrichment. Fixing website and industry fill rates improves every sector uniformly and is the prerequisite for any sector-specific work.

---

## Part 4 — PoC Enrichment Pipeline

**Goal**: Build a working agentic enrichment pipeline that executes the field cascade from Part 3 (website → industry → type → size) on a real batch, with structured outputs, confidence scores, retries, cost controls, and a lightweight eval.

**Target**: General firmographic enrichment (website, industry, type, size) across 220 records, drawn from the size-stratified sample spanning all sectors.

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

The pipeline was iterated through with multiple cycles of small batch runs and manual reviews before running the full batch. This kept cost low and made it possible to inspect every decision before scaling.

**Model choices**:
- **Haiku** — 85% of calls. Cheap, fast, accurate enough for entity matching and structured extraction where the answer exists in the retrieved text.
- **Sonnet** — 14% of calls (well within the 40% cost-signal threshold). Handles ambiguous subsidiaries and multi-hop entity resolution where Haiku returns low confidence.
- **Rules layer** — runs before any LLM call. Deterministic and free.

**Key design decisions from iteration**:
- `_build_output` prefers original when populated — enrichment fills gaps, doesn't overwrite correct data
- `is_single_facility` classification gates size enrichment: hospital campuses and branch offices get location headcount, not parent org headcount
- `closure_signals` enum extended to `"permanently_closed"` and `"acquired"` after Run 1 revealed misses
- Domain-mismatch routing: when enriched website domain differs from `company_domain`, record is flagged for manual review before ingest

### Run results (220 records, $8.00)

| Status | Count | % |
|---|---|---|
| FULLY_ENRICHED | 101 | 35% |
| PARTIALLY_ENRICHED | 49 | 17% |
| NO_CANDIDATE | 138 | 48% |
| Stage 4 (Sonnet) usage | 31 | 14% ✅ |

The 48% NO_CANDIDATE rate is primarily records with no resolvable public web presence — closed companies, stealth entities, government sub-units — not pipeline failures. T03 and T06 in the 90-day plan address the recoverable fraction.

**Post-enrichment fill rate (newly filled ÷ originally null)**:

| Field | Fill rate |
|---|---|
| type | 63% |
| industry | 46% |
| website | 36% |
| size | 0% ⚠️ (pipeline issue — gated from output) |

### Eval (20 hand-labelled records)

| Field | Precision | Recall | F1 |
|---|---|---|---|
| type | 0.947 | 0.900 | **0.923** ✅ |
| industry | 0.789 | 0.750 | 0.769 |
| website | 0.750 | 0.750 | 0.750 |
| size | 0.438 | 0.438 | **0.438** ⚠️ |
| **Macro** | **0.731** | **0.710** | **0.720** |

**Where it's weak**: Size is the primary failure mode — 9/9 mismatches are symmetric (equal FPs and FNs), signalling systematic miscalibration, not random noise. Root cause: the pipeline conflates parent-org headcount with subsidiary headcount for hospital systems, division entities, and acquired companies. 67% of mismatches are off-by-one band — entity resolution quality, not a data ceiling. Fix: lower the size confidence acceptance threshold (0.55 → 0.65) and add a Stage 3b re-query when the enriched size diverges from the original by more than one band. Website calibration (70%) is below the 80% target due to parent-domain returns for subsidiaries — addressed by flagging `entity_verdict=SUBSIDIARY` records. Size is gated from customer output until precision clears 0.55.

Two findings worth flagging: (1) the rules layer moved more records than expected — blocklist extension and platform-URL reclassification alone shifted thousands of records from "has website" to "needs enrichment" before any LLM call fired, which had a downstream effect on every fill-rate metric; (2) confidence calibration is the harder problem — the pipeline returned size predictions at ≥0.80 confidence that were wrong 43% of the time, worse than random. A miscalibrated confidence score is actively harmful to downstream consumers and was the primary reason size is gated from output.

### Manual spot-check observations (Part 4)

Three issues surfaced from hands-on inspection of enriched records:

- **Size: office headcount vs. global headcount conflation.** "Office of Governor Josh Shapiro" (Harrisburg, PA) was returned at 85% confidence as 11–50 employees; the more accurate bracket is 201–500. Separately, `clientele-inc` had its original 51–200 estimate echoed back at 0.65 confidence when the actual headcount is likely under 10. The pipeline is pulling org-level or search-result headcount rather than the specific entity's count. This links to a product decision: customers targeting local job sourcing need office headcount; SaaS products like Okta or Workday need total global employees. The right size definition depends on the ICP, and the pipeline needs to be explicit about which it's returning. Needs further investigation before size is unblocked from customer output.

- **Low-information records need an exclusion signal.** "Startup (in Stealth Mode)" has no retrievable public presence and is low-value regardless of enrichment effort. The pipeline should produce a `low_signal` flag (no web results, no industry inference possible, name is a placeholder) to let downstream consumers exclude these before ingest rather than enriching noise.

- **Industry misclassification at high confidence.** VIVAGE QUALITY HEALTH PARTNERS was returned as "personal care product manufacturing" — the original "hospitals and health care" label was correct. The failure mode is the model confidently picking a surface-level keyword match over the entity's actual sector. Complements T04 in the 90-day plan.

---

## Part 5 — Reusable Skill: `coverage-audit`

**Location**: `skills/coverage-audit/SKILL.md`

A two-stage market coverage audit workflow. Stage 1: internal data quality profiling (fill rates, null patterns, tier distribution). Stage 2: external gap detection against a government benchmark (SUSB, NES, ABS, BizFile — configurable). Any team member or agent can run it on a new market by editing `config/project.yaml` — no code changes required.

**Trigger**: new market onboarding, quarterly coverage refresh, pre-sales gap inquiry, post-enrichment validation.

**Inputs**: dataset path, geography column, size/industry column names, platform blocklist (from config), and optionally a comparator source for Stage 2. Stage 2 can be skipped when no government benchmark exists for the target market.

**Outputs**: `docs/part1-baseline.md` (human-readable audit with gap table), `data/processed/part1_profiling_summary.json` (machine-readable counts), `data/processed/part1_sample_audit.parquet` (stratified sample ready for enrichment).

**Known limitations**:
- NES-based comparators inflate non-employer counts; the skill auto-flags gig-economy sectors and documents the correction. For Transportation specifically, NES makes the gap look like 98% vs. the SUSB employer-firm gap of 65% — comparator choice is load-bearing.
- Stage 2 requires a government benchmark file. For SEA markets without a clean SUSB/ABS equivalent, skip Stage 2 and use Stage 1 fill-rate findings alone — still actionable.
- Post-enrichment validation (running the skill after a pipeline run to check fill-rate improvement) requires the enriched Parquet, not the raw dataset. Running it against raw data after enrichment will revert gap sizes to baseline figures.

**Example invocation**:
```
/coverage-audit market=US dataset=data/processed/part0_companies.parquet comparator=data/raw/susb_2021.csv
```

**Example output** (truncated):
```
coverage-audit v2.0 | market=US | 4,164,063 records | 2026-06-15 02:17 UTC
Stage 1 complete — fill rates: website 77.1%, industry 91.8%, size 95.5%, state 96.7%
Stage 2 complete — SUSB comparator loaded (51 states, employer firms only)

TOP GAPS (by SUSB employer coverage ratio):
  HIGH_GAP  Transportation & Warehousing  1.99% coverage  confidence=0.92
  HIGH_GAP  Construction                  5.93% coverage  confidence=0.90
  HIGH_GAP  Administrative & Support      3.51% coverage  confidence=0.85
  HIGH_GAP  Retail Trade                  6.19% coverage  confidence=0.87
  HIGH_GAP  Other Services                2.25% coverage  confidence=0.78

Cost: $0.37 | Runtime: 8m 42s | Traces: shared_observability.jsonl
```

---

## Tooling & Agentic Dev Loop

| Layer | Tools |
|---|---|
| IDE / orchestration | Claude Code (CLI) — main session + explicit subagent routing |
| Data engine | DuckDB (in-process SQL), Pandas, Polars |
| LLM calls | Anthropic SDK — Haiku 4.5 (classification, extraction), Sonnet 4.6 (synthesis, fallback) |
| Observability | `shared_observability.jsonl` (per-call trace: model, tokens, cost, latency, outcome) |
| Evals | `evals/eval_runner.py` — precision/recall against 20 hand-labelled records |
| Version control | Git (conventional commits), GitHub |

The agentic dev loop ran a strict produce/check split throughout: a `data-engineer` subagent produced gap candidates and enriched records; a separate `verifier` subagent re-derived findings independently from raw data via SQL before any result was treated as fact. The key discipline was never letting the same agent do both roles for the same part — the separation is what makes trust calibration demonstrable rather than claimed.

The biggest productivity gain was treating Claude Code as an orchestration layer, not a code generator. The most valuable sessions were the ones where I directed agents with explicit constraints (model choice, cost ceiling, output schema) and reviewed the traces to catch drift — rather than asking for code and running it blindly.
