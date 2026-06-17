# Part 6 — 90-Day Pod Plan

_Team: 3 engineers (data/ML, backend, QA) | Based on Parts 1–4 audit and PoC eval_

---

## Thesis

The BigPicture dataset gives Firmable a 4.25M-record US starting point. This plan delivers a clean, enriched firmographic layer good enough for ingest and initial customer validation — not a sellable product, but the foundation one. Success at day 90 is positive signal from at least one ANZ customer running a US motion, not revenue.

---

## Measurable Outcomes

| Metric | Baseline | Day 90 Target |
|--------|----------|--------------|
| Website precision on enriched records | P=0.75 (PoC, 20-record eval) | P ≥0.85 (100-record eval) |
| Industry precision on enriched records | P=0.79 (PoC, 20-record eval) | P ≥0.85 (100-record eval) |
| Design partner signal | 0 — not yet ingested | ≥1 ANZ customer with US footprint reporting positive feedback |

_PoC post-enrichment coverage (220-record run): website 63%, industry 98%, type 95%. Size fill 0% — pipeline issue, not a data ceiling; gate from customer output until pipeline is fixed and P ≥0.55. First-party size provider scoped to cycle 2._

---

## Work Plan

**T01 — Data cleanup** `XS` · no deps · Data
Agent runs blocklist audit across 4.16M records. Extend URL blocklist (GMB, e-commerce, URL shorteners), review and flag performance for franchise domains in the enrichment queue, deduplicate 3 semantic industry label pairs. Output: clean dataset ready for enrichment pipeline.

**T02 — State null recovery** `XS` · after T01 · Data
Deterministic join of 124K null-state records against USPS city→state reference. No model cost. Unblocks website enrichment — state is a required search parameter and 13K enterprise records are currently invisible in state-filtered searches.

**T03 — Entity resolution spike** `M` · after T01/T02 · ML
The PoC's primary failure mode: pipeline returns the right organisation at the wrong entity level (parent instead of subsidiary). Agent runs targeted test batch against known failure cases. Ship what raises precision; iterate next sprint. Also investigate the 48% NO_CANDIDATE rate — entity resolution quality and retrieval failure share the same root cause. Understand how much is legitimately unresolvable vs. a fixable pipeline gap before closing the spike. Goal: website P ≥0.85.

**T04 — Industry classification spike** `M` · after T01 · ML
Sibling-label confusion accounts for most industry misses (5/5 eval mismatches were adjacent labels). Agent tests classification approaches. Goal: industry P ≥0.85. Also surface-test against cross-sector misclassification before adding any additional complexity.

**T05 — Deterministic type enrichment** `S` · independent · Data
Type is already the strongest field: P=0.947, 95% post-enrichment coverage in the PoC. T05's value is cost reduction — name-suffix rules (school districts, government agencies, foundations) and SEC ticker lookups catch the obvious cases for $0 before any LLM call fires. Goal: reduce Sonnet/Haiku usage on type by ≥30% without dropping precision below P=0.94.

**T06 — Low-signal exclusion** `XS` · after T01 · Data
Define and ship exclusion criteria for records with no resolvable public presence (stealth, placeholder, permanently closed). Spot-check a sample before shipping — no legitimate company should be excluded on name pattern alone.

**T07 — Eval expansion** `M` · after T03/T04 · QA
Agent generates 80 candidate records; QA verifies. Expand ground truth from 20 → 100 records across enterprise, mid-market, and SMB segments. Add confidence calibration check to eval runner. At 20 records, one miss moves a segment metric by 8% — not defensible for a ship decision.

**T08 — Design partner validation** `S` · after T03/T04 · Data + CS
Route 50 enriched records to one ANZ customer with a confirmed US territory. Three questions per record: website resolves? Right company? Would you use this in a sequence? Gate for full-scale run.

---

## Sequencing

**Day 1–30** · _Build & iterate_
T01, T02, T05, T06 ship in week 1 (deterministic, no model cost). T03 and T04 are spikes — run, measure, iterate within the sprint. Re-run the 288-record eval batch at day 20 to get an updated precision score before the gate.

**Day 30 — Go / No-Go / Pivot**
- **Go**: website P ≥0.78 AND industry P ≥0.78 on updated eval → proceed to Sprint 2
- **Pivot**: either metric between 0.70–0.78 → one more iteration week before design partner validation
- **Kill / descope**: either metric below 0.70 → diagnose root cause; consider narrowing to enterprise-only scope

**Day 31–60** · _Validate & expand_
T07 (eval expansion) and T08 (design partner validation) run in parallel. Size spike (targeted retrieval approaches) runs if day-30 gate passes and engineering has capacity. Full-scale 30K pilot planned but not kicked off until design partner feedback clears.

**Day 61–90** · _Ship_
30K pilot run if Sprint 2 gate passes (≥70% positive design partner feedback). Ingest into platform. Cycle-2 scoping begins: contact enrichment, `global_size` field, first-party size provider.

---

## Risk and Bet

**Risk** — Size precision is structurally limited by public web data. The entity resolution spike (T03) should lift it, but the ceiling from open web sources is ~0.60. If size doesn't clear 0.55 by day 30, gate it from customer output and communicate to CS before Sprint 2. The risk isn't a low score — it's shipping a low score silently.

**Bet** — If budget halves, protect T01–T04 and the 30K pilot. Website and industry are the primary ICP filter dimensions. A clean ingest with those two fields at P ≥0.85 — and size explicitly gated — is a credible first delivery. Size and contacts follow in cycle 2.
