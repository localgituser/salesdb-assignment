# Part 6 — 90-Day Pod Plan
_To be written after Phase 4 — must use real numbers from Phases 1–4._  
_Format: 1–2 pages maximum. Linear-ticket work items, agent-augmented._

---

## Thesis

_One paragraph. The bet, why now, what success looks like. Fill in with Phase 4 precision/recall numbers and actual Phase 2 gap coverage percentages._

The US dataset has adequate geographic breadth (all 51 states at ADEQUATE vs. SUSB) but structural sourcing gaps in the physical economy — Construction at 5.9% and Transportation at 2.0% combined coverage vs. SUSB+NES. These are the exact sectors where Sales Intelligence buyers (freight-tech, construction-tech, equipment-finance) concentrate their outbound spend. State contractor licensing boards and the FMCSA Motor Carrier database are public, structured, and have not been systematically ingested. A 3-engineer pod running a registry-ingestion sprint over 90 days can materially close Construction coverage in the top 10 states (representing ~60% of construction employer firms) and Transportation coverage nationwide via FMCSA — moving both sectors from HIGH_GAP to ADEQUATE, unlocking list-purchase renewals and reducing churn from construction and logistics customers within the first quarter.

---

## Measurable Outcomes (Day 0 → Day 90)

| Metric | Day 0 (from audit) | Day 90 Target |
|--------|--------------------|---------------|
| Construction coverage vs. SUSB employer firms | 28.0% | ≥ 50% |
| Transportation coverage vs. SUSB employer firms | 34.5% | ≥ 55% |
| Enterprise record count (500+ employees) | 69,109 | ≥ 85,000 |

---

## Work Items (Linear-Ticket Format)

| # | Title | Effort | Dependencies | Agent augmentation |
|---|-------|--------|--------------|-------------------|
| W1 | Ingest FMCSA Motor Carrier database (national) | M | None | data-engineer runs dedup against `us_companies_clean.parquet` |
| W2 | Ingest state contractor licensing — top 10 construction states | L | None | data-engineer maps license records to NAICS 23, flags employer-level firms |
| W3 | Entity match + dedup new records against existing dataset | M | W1, W2 | data-engineer runs fuzzy match; Haiku resolves clear matches; Sonnet for ambiguous |
| W4 | Enrichment cascade on new + existing gap-sector records | M | W3 | `src/part4_pipeline.py` cascade (rules → search → Haiku → Sonnet) |
| W5 | Eval: re-run `evals/eval_runner.py` on post-ingestion batch | S | W4 | verifier subagent runs eval, compares to Phase 4 baseline |
| W6 | Update coverage-audit skill for new market runs | S | W1–W5 | — (manual update to SKILL.md) |
| W7 | Commercial review: refresh gap_findings.md with new coverage ratios | S | W5 | data-engineer subagent re-runs gap_detection.py |
| W8 | Stakeholder output: state-by-state coverage delta report | S | W7 | — (SQL query + markdown table) |

---

## 30 / 60 / 90 Day Sequencing

**Day 30 — Go/No-Go Gate**

_Must see:_
- FMCSA ingestion complete (W1) — net-new transportation records > 10K
- At least 5 state contractor licensing boards ingested (W2 partial)
- Dedup pipeline running cleanly with <1% false-merge rate (W3)

_Kill signal_: If state licensing board APIs are uniformly unavailable or require commercial licenses, pivot to franchise disclosure registries (retail Gap 3) as the 90-day target instead.

_Pivot signal_: If Transportation FMCSA delivers outsized yield but Construction state boards are slow, shift W2 resource to FMCSA depth (additional states, carrier contacts) and defer Construction to next cycle.

**Day 60** — All ingestion complete (W1–W3), enrichment cascade running on new records (W4), initial eval pass done (W5).

**Day 90** — Coverage delta confirmed (W7–W8), skill updated (W6), outcomes measured against Day 0 baseline.

---

## One Risk, One Bet

**Risk**: State contractor licensing boards in 4–6 of the top 10 construction states require a commercial data license or have no public API — forcing manual ingestion or a paid data provider, which extends W2 by 4–6 weeks and may require budget reallocation.

**Bet** (protect if budget halved): FMCSA Transportation ingestion (W1). It's a single public dataset, nationally scoped, with a well-documented bulk export. Even at half budget, FMCSA alone moves Transportation from 2.0% to a materially higher coverage level — the single highest-ROI action in the plan.
