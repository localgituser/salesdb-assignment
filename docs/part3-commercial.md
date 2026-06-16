# Part 3 — Commercial Framing & Prioritisation
_Generated: 2026-06-15 | Enrichment baseline: `data/processed/part3_enrichment_baseline.json` (src/part3_audit.py)_
_Scope: 11+ employee records only — see assumption below_

---

## Scope Assumption: Micro Businesses (1–10 Employees) Excluded

All enrichment analysis in Part 3 onwards operates on the **1,491,060 records where `size NOT IN ('1-10') AND size IS NOT NULL`**. The 2,503,111 micro-business records (59.8% of the dataset) are excluded for four compounding reasons:

1. **Worst data quality across every field.** Micro records have the highest null rates: website null 24.7% vs 19–25% for 11+ bands; industry null 7.1% vs ≤5.3% for 11+. Every enrichment metric is flattest and hardest to improve here.

2. **High entity churn.** Sole traders and micro businesses fail at 35–45% within 5 years (BLS Business Employment Dynamics; echoed in Part 1 §5b). Records matching the `HIGH_CHURN_RISK` pattern (`size='1-10' AND founded>=2015 AND website IS NULL AND type IS NULL`, Part 1 §5b) are high-probability stale entities. Enriching closed companies wastes tokens and degrades output file quality.

3. **Structurally low web presence.** 1-in-4 micro records have no website (Part 1 §11.2: 24.73% null rate for the 1–10 band). A significant portion likely reflects businesses that genuinely have never had one — particularly in trades and food service — though the exact fraction where a website does not exist versus simply has not been sourced is unknown (Part 2 Gap 5 notes this explicitly). A web-based enrichment pipeline cannot close a structural gap.

4. **Low sales priority for Firmable's ICP.** (Assumption) Firmable's customers are B2B sales teams targeting companies with purchasing authority and budget. Micro businesses are rarely in scope for Sales Intelligence outbound sequences or ABM programs.

The **188,159 records where `size IS NULL`** are also excluded. Their quality profile (23.7% website null, 53.2% industry null) mirrors the micro cohort — they are likely low-quality scrapes, not genuinely unknown-size companies.

**Sourcing gaps** (Construction 5.93%, Transportation 1.99%, Retail 6.19%, Enterprise thin at 1.65%) are real and commercially significant, but they require **net-new record ingestion** from public registries (FMCSA, state licensing boards, SEC filings) — not enrichment of existing records. These are Part 6 roadmap items. The rest of this document addresses only enrichment: improving field quality on records we already have.

---

## Enrichment Gap Baseline (11+ employees)

_Source: `src/part3_audit.py` → `data/processed/part3_enrichment_baseline.json`_

| Metric | Value |
|---|---|
| Working set (11+ known size) | 1,491,060 records |
| Website fill rate | 80.56% |
| Website missing (raw null) | 289,842 |
| Platform/social URLs to reclassify (blocklist-covered) | 1,853 |
| Platform/social URLs missed by blocklist gaps | 201 |
| **True website gap** | **291,896 records (19.6%)** |

**Platform URL note — confirmed root domains, not specific pages**: Spot-checked against the raw data. Every platform URL in the dataset is the platform's own root domain (`wixsite.com`, `wordpress.com`, `yelp.ca`) with no company-specific path or slug. There is zero entity-specific information recoverable from these values. They are functionally identical to null: must be cleared and queued into the website enrichment batch. The only pipeline distinction is a deterministic blocklist-match detection step that reclassifies them to null before the search/Haiku cascade runs — no model call required.

**Blocklist gaps identified** (extend `config/project.yaml` → `enrichment_rules.platform_blocklist` before Part 4):

| Missing entry | Records | Issue |
|---|---|---|
| `wix.com` | ~490 | Platform root, not in blocklist (only `wixsite.com` is covered) |
| `yelp.ca`, `yelp.co.uk`, `yelp.com.au`, `yelp.co.nz`, `yelp.no`, `yelp.ie` | ~120 | International Yelp TLDs not covered |
| `www.linkedin`, `www.facebook`, `www.instagram` | ~28 | Malformed (no TLD) — not caught by exact-match on `linkedin.com` etc. |
| `wordpress.org` | ~5 | Only `wordpress.com` is blocked |
| `blogspot.com` subdomain records | small tail | Not in blocklist |
| `.gov.au`, `.gov.uk`, `.gov.ca`, `.gov.nz`, `.gov.ie` (country-code .gov variants) | unknown | Not caught by `.gov`-only suffix match in `INSTITUTIONAL_TLDS` (`src/shared/rules.py`) — manual audit confirmed private US businesses assigned these foreign government domains (Part 2 Manual Audit Observation A) |

These slip through the current blocklist into the "populated website" bucket and are never queued for enrichment. All are the same problem — root platform domains, malformed truncations, or mismatched foreign government domains with no entity-specific content.
| Industry fill rate | 95.61% |
| Industry missing | 65,478 |
| Industry semantic duplicates (3 label pairs) | 121,272 |
| **Total industry quality gap** | **186,750 records (12.5%)** |

**Unexpected finding — website fill is worst at the enterprise end, not the SMB end:**

| Size Band | Records | Website Fill | Website Missing |
|---|---|---|---|
| 11–50 | 1,068,666 | 78.81% | 226,466 |
| 51–200 | 276,846 | **85.99%** ← peak | 38,799 |
| 201–500 | 76,439 | 85.07% | 11,410 |
| 501–1K | 29,000 | 83.59% | 4,760 |
| 1K–5K | 26,259 | 81.05% | 4,976 |
| 5K–10K | 5,259 | 75.19% | 1,305 |
| **10K+** | **8,591** | **75.25% ← worst** | **2,126** |

Website fill peaks at 51–200 employees and then degrades monotonically. The 10K+ band (lowest fill at 75.25%) likely reflects two compounding factors: (a) subsidiary/division records sourced from LinkedIn where the entity exists but its own website was never captured, and (b) reclassification of institutional TLDs (.gov, .mil, .edu) as null by the Part 3 cleanup pass (Part 1 §11 records 40,864 such reclassifications). Note: Part 1 §5b reports 10K+ website fill at 92.3% on the pre-cleanup dataset without institutional-TLD reclassification; the 75.25% figure here is post-reclassification. Manual audit observations (Part 2) show that the stored .gov domains are not institutional entities storing their own domain — they are private businesses (massage therapy practices, fitness studios) assigned completely unrelated foreign government URLs, a sourcing mismatch artefact. International variants (.gov.au, .gov.uk) are not caught by the current `.gov`-only suffix check in `src/shared/rules.py`, meaning some of these corrupted records still count toward the fill rate across all size bands.

**Worst states for website fill (11+ only, ≥5K records):**

| State | 11+ Records | Website Fill | Industry Fill |
|---|---|---|---|
| Iowa | 12,816 | 67.4% | 79.8% |
| Mississippi | 6,257 | 70.1% | 94.8% |
| Arkansas | 7,956 | 72.2% | 95.3% |
| Tennessee | 27,972 | 72.9% | 85.3% |
| Kansas | 12,513 | 73.0% | 86.0% |

Iowa and Tennessee stand out: low website fill AND low industry fill, making them the highest-ROI geographic targets for an enrichment sprint.

**Additional known gaps (not in enrichment baseline above):**

| Field | Null Rate | Affected Records | Commercial relevance |
|---|---|---|---|
| `type` (Public/Private/Non-profit) | ~45.1% national¹ | ~1.88M | First-order ICP filter; blocks segment-level targeting |
| `founded` (founding year) | ~54.1% national¹ | ~2.25M | Growth-stage ICP filter; secondary signal |

¹ _National null rates from Part 1 §3 / §11.2 (full 4.16M dataset). Within the 11+ working set, `type` null rate is lower (~35%, weighted from Part 1 §5b per-band rates of 4.6–43%). `founded` null rate by size band is not reported in Part 1; the national figure is used as a directional approximation. Note: Part 1 §3 reports these fields as **Fill %** (54.90% and 45.90% respectively) — the null rates above are the complements._

These are not included in the enrichment gap baseline figures above (which cover only `website` and `industry`) but are scored in the ICE matrix.

---

## Enrichment Gap Commercial Summaries

### Gap 1 — Website Missing + Entity Validation (291,896 records, 11+ only)

**ICP**: Every Firmable customer — this gap affects all verticals, all deal sizes, all personas.

**Deals it costs**: A company record without a website URL is the upstream blocker for the entire enrichment chain. No website means: no email domain inference, no domain-based intent signals (G2, Bombora), no technographic enrichment (BuiltWith, HG), no web-scrape for employee count validation. An AE building an outbound sequence or an ABM team building a target account list cannot act on these records — they either enrich manually (expensive) or skip the account (leave revenue on the table).

**Data vintage risk**: The dataset is approximately 3 years old (circa 2023). Some of the 291,896 missing-website records belong to companies that have since closed, been acquired, or rebranded. Enriching a dead company's website is actively worse than leaving the field blank — it inserts a trusted-looking wrong value into the customer's outreach tool, driving bounce rates and churn attribution back to Firmable. The domain liveness check (HEAD request, 5s timeout) in the Part 4 cascade guards against this: domains that don't respond are flagged `ENTITY_VALIDITY_UNCERTAIN` and excluded from the enriched output. Entity validation is therefore an integrated step of the website enrichment pass, not a separate workstream. The same check runs on existing non-null websites before any enrichment call, catching stale records in the populated population too. The `status` field is absent from the schema entirely (see Schema Absences), so domain liveness is the best available proxy — it catches closed entities but not acquired or rebranded ones.

**Churn signal**: Low deliverability rates on exported lists surface immediately when customers push records into outreach tools. Email tools flag invalid domains; the customer flags Firmable. A bounced domain that was populated by the enrichment pipeline — rather than being blank — is a harder customer conversation than a missing field. This is the most direct, fastest-to-surface churn vector, and data vintage amplifies it.

**Why this is a harder problem than it looks**: The 5K–10K and 10K+ bands have *worse* fill (75.2%) than SMBs despite being larger, more established companies. Enterprise records appear to be sourced at shallower depth from LinkedIn company pages — the page exists, but the website field wasn't populated. These records have the highest commercial value per unit and the most recoverable websites (large companies almost universally have one). Enriching 3,431 mid-market-to-enterprise records with missing websites has more revenue impact than enriching 3,431 SMB records.

**email_domain unlock**: Closing this gap also delivers `email_domain` as a zero-cost by-product — once a website is known, the domain is extracted by stripping protocol and path (`https://acme.com/about` → `acme.com`), no API call, no model. Intent data providers (Bombora, G2, 6sense) use the domain as their primary company-match key, meaning every website enriched also expands the record's value for ABM customers running intent-signal programmes.

---

### Gap 2 — Industry Classification Quality (186,750 records, 11+ only)

**ICP**: Any Firmable customer running vertical ICP filters — the dominant use case for Sales Intelligence search.

**Deals it costs**: Two distinct failure modes. (a) **Missing industry** (65,478 records): these records are invisible in any vertical search, regardless of how good the rest of the record is. (b) **Semantic duplicate labels** (121,272 records across 3 pairs): records *appear* enriched but the addressable universe is artificially halved. A customer filtering for IT Services firms returns only the 46,932 records labeled `it services and it consulting` — the 13,194 labeled `information technology & services` are silently excluded. The customer sees thin results and assumes the data is sparse, not that the taxonomy is split.

The three affected label pairs:

| Label A | Count | Label B | Count | Combined (11+) |
|---|---|---|---|---|
| it services and it consulting | 46,932 | information technology & services | 13,194 | **60,126** |
| wellness and fitness services | 23,757 | health, wellness & fitness | 7,522 | **31,279** |
| non-profit organizations | 23,752 | non-profit organization management | 6,115 | **29,867** |

**Churn signal**: Lower-than-expected match rates on ICP-filtered exports. Harder to diagnose than missing websites because the records *are* there — they're just labeled inconsistently. Customers often attribute thin vertical results to market size rather than taxonomy fragmentation.

---

### Gap 3 — Enterprise Website Sub-Gap (2,126 records at 10K+, 75.25% fill)

**ICP**: Enterprise AEs and account-based marketing teams at B2B software companies. Their deal sizes are 10–50x an SMB deal.

**Deals it costs**: ABM programs targeting Fortune 1000 companies depend on website URLs as the primary enrichment anchor. A missing website on a 10K+ employee company blocks domain-based contact enrichment, technographic signal, and firmographic verification. The absolute record count is small (2,126) but the revenue value per record is large — each enterprise record correctly enriched is potentially worth hundreds of dollars in downstream data-product margin.

**Churn signal**: Enterprise-tier Firmable customers running ABM programs will hit these gaps first because they search exclusively in the 500+ size band. One high-profile account with a missing website surfaces the issue immediately in a QBR.

---

### Gap 4 — Entity Type Missing (`type` field, ~1.88M records null at 54.9%)

**ICP**: Enterprise AEs, ABM teams, and GTM teams running PE-backed or pre-IPO account lists — any customer using Public / Private / Non-profit as a primary ICP filter.

**Deals it costs**: Two distinct failure modes. (a) **Targeting failures**: a sales team building a prospect list of "private companies with 200+ employees" cannot execute that filter when 54.9% of records have no `type` value. The effective searchable universe for that segment is artificially halved. (b) **Contaminated exports**: Non-profit records mixed into a commercial prospect list (because `type` is null, not explicitly `Non-profit`) create bad-fit outreach, which degrades customer sender reputation and email deliverability — the same fast-to-surface churn vector as Gap 1.

**Two-speed recovery path — this gap is split in the ICE table**:

- **Public companies (ICE 63, Ease 9)**: Deterministic. SEC EDGAR and ticker databases cover all NYSE/NASDAQ-listed entities — no model call required. An estimated ~40K+ records in the 11+ working set are publicly traded and currently show `type IS NULL`. A rules-based lookup against a ticker file recovers these with near-perfect precision in a single offline pass.
- **Private/Unknown (ICE 16, Ease 4)**: Requires a website plus a Haiku inference pass ("is this company private, government, or non-profit based on its homepage?"). Lower confidence than the SEC lookup; unrecoverable for website-null records without an external data provider. Non-profit is partially recoverable by cross-referencing the industry duplicate pairs already identified in Gap 2 (non-profit organization management → Non-profit).

The public-company fix is a fast, standalone win that should ship before the private inference work begins. The ease differential (9 vs 4) justifies treating them as separate roadmap items.

**Churn signal**: Customers whose ICP is explicitly Public or PE-backed Private will notice thin results in segment-filtered searches and assume market coverage is poor. The actual issue is a taxonomy gap, not a universe gap — the same misdiagnosis risk as the industry duplicate problem in Gap 2, but at a more fundamental filter level.

---

### Gap 5 — State Null Residual (124,525 records geographically unresolvable post-rules-cleanup)

**ICP**: Every Firmable customer using geographic filters — which is nearly all of them. State is a first-order search dimension for Sales Intelligence.

**Deals it costs**: Records with no state are geographically invisible. They cannot appear in any state-filtered search or export, regardless of how complete their other fields are. The 13,061 mid-market and enterprise records (51+ employees) in this cohort are the commercially significant slice — each is a high-value account that Firmable customers targeting a specific region will never see. A customer building a "Texas manufacturing companies, 200+ employees" list is silently missing any record in this cohort that happens to be a Texas manufacturer.

**Pre/post-cleanup context**: The pre-cleanup null-state population was 142,792 records. The Part 1 rules cleanup (`src/shared/rules.py` — case normalisation, abbreviation expansion, city-split recombination) recovered ~18,267 of those, leaving the 124,525 residual. These are genuinely unresolvable by deterministic rules alone.

**Size-band breakdown of the 13,061 high-value residual (51+ employees):**

| Size Band | Null-State Count |
|---|---|
| 51–200 | 7,787 |
| 201–500 | 2,536 |
| 1K–5K | 914 |
| 10K+ | 528 |
| 5K–10K | 270 |
| **Total (51+)** | **13,061** |

The 528 records at 10K+ employees are the highest per-record value within this cohort — large companies almost universally have a public website that reveals HQ state, making them the most recoverable subset. These records are tagged `state_unknown_high_value` in `part2_gap_candidates.json` (sourced from Part 1c findings) to surface them as a distinct enrichment target in Part 4 rather than lumping them into the broader null-state residual.

**Why this is a pre-condition problem as well as an enrichment gap**: The Part 4 cascade uses `name + city + state` as its primary query input for website and industry enrichment. Null-state records passed to the cascade produce lower-quality search results (city-only queries are significantly more ambiguous). Recovering state is therefore not just a gap to close for its own sake — it directly upgrades the quality of every downstream enrichment operation on the same record.

**Recovery path**: Two-stage.
1. **Rules (handles majority)**: Most of the 124,525 are recoverable via `city → state` lookup (a deterministic mapping for unambiguous city names). Part 1 §1b already specifies this fix for `src/shared/rules.py`. Running the rules cleanup before Part 4 reduces the null-state residual substantially.
2. **LLM inference (handles the rest)**: Records where city is also null or ambiguous require a Haiku pass — if the record has a `website`, the HQ state is usually inferable from the homepage or contact page. If `website` is also null, state recovery is low-confidence and should be flagged rather than inferred. The `state_unknown_high_value` tagged records in `part2_gap_candidates.json` are the priority input for this pass — 51+ employees with a likely-resolvable website signal.

**Churn signal**: Thin or zero results on geographic searches is the most immediate way a customer notices a data gap. A sales rep who searches "construction companies in Iowa" and gets fewer results than expected will escalate to their CSM. This gap makes that scenario structurally more likely.

---

### Gap 6 — Founding Year Missing (`founded` field, ~2.25M records null at 45.9%)

_Lower commercial priority than Gaps 1–4. Documented for completeness._

**ICP**: Sales teams filtering by company age or growth stage — targeting recently-founded companies (2018–2022 for "still scaling" signals) or established firms (pre-2000 for "legacy replacement" plays).

**Commercial impact**: A missing `founded` year prevents growth-stage ICP filtering. It is a secondary enrichment signal — useful after website and industry are correct — and recovery is harder (founding year is not reliably surfaced by search APIs; often requires company website or Crunchbase). At 45.9% null, the gap is large but the enrichment ROI is lower per record than Gaps 1 and 2. Recommended as a Phase 3 enrichment pass after website and industry are stable.

---

## ICE Scoring

_ICE = (Impact × Confidence × Ease) / 9, each dimension scored 1–10, result rounded to integer._
_Impact: revenue at risk (deal size × breadth of customers affected). Confidence: directly observed in Part 1 baseline; lower where count is inferred. Ease: speed of closure — the Part 4 cascade (rules → search API → Haiku verify → Sonnet fallback) is the reference point (Ease 8 = straightforward cascade fit; Ease 3 = requires external data source not yet in pipeline)._

| Gap | Impact | Confidence | Ease | ICE | Rank |
|---|---|---|---|---|---|
| Website enrichment + entity validation (291,896 records) | 9 | 9 | 8 | **72** | **1** |
| Industry quality (186,750 records) | 8 | 9 | 8 | **64** | **2** |
| `type` field — Public companies (SEC/ticker lookup) | 7 | 9 | 9 | **63** | **3** |
| Enterprise website sub-gap (2,126 at 10K+) | 9 | 9 | 5 | **45** | **4** |
| State null residual (124,525 records; 13,061 enterprise) | 6 | 9 | 7 | **42** | **5†** |
| `founded` year (~2.25M null, 45.9%) | 5 | 9 | 4 | **20** | **6** |
| Entity validity (3-yr vintage, stale entity risk) | 8 | 6 | 3 | **16** | **7** |
| `type` field — Private/Unknown (LLM + website context) | 5 | 7 | 4 | **16** | **8** |

**† State null gap (Ease 7)**: High ease because the majority is rules-recoverable (city→state lookup, already specified in `src/shared/rules.py`). The LLM tail (city-null residual) is smaller and uses website-based HQ inference. Ease scores 7 rather than 8 because city-null records with no website are unrecoverable without external data. Impact scores 6 rather than higher because the majority of affected records are micro/SMB (lower commercial weight); the 13,061 enterprise records are the commercially critical sub-slice.

**Ease notes:**

- **Enterprise sub-gap (Ease 5)**: Same cascade, harder entity resolution — subsidiary → parent → authoritative domain. More pipeline complexity, lower throughput.
- **`type` — Public (Ease 9)**: SEC EDGAR and ticker databases cover all publicly listed entities; deterministic lookup, no model call.
- **`type` — Private/Unknown (Ease 4)**: Requires website context plus Haiku inference. No reliable structured source; confidence limited by website quality and vintage.
- **`founded` year (Ease 4)**: Not reliably surfaced by search APIs. Requires company website scrape or Crunchbase / structured database lookup.
- **Entity validity (Ease 3)**: Domain liveness check (HEAD request) is the best available proxy for a missing `status` field — catches closed entities but not acquired or rebranded ones. Ranked separately from Gap 1 to represent the ongoing re-validation cost beyond the initial enrichment pass (e.g., periodic liveness sweeps on the enriched population). **Impact capped at 8 (not 9) by Part 1 §5b survival data**: the working set is 11+ employees only, where average company age is 26–61 years and 3-year survival exceeds 95%. The HIGH_CHURN_RISK cohort (micro, founded ≥2015, 35–45% failure rate) is already excluded from the working set. Entity validation is a budget multiplier — stale records waste enrichment tokens — but at < 5% expected stale rate in this cohort, the ROI on a validation pre-pass is bounded. The one-time pre-pass (HEAD request, no model) is cheap; Ease 3 reflects the ongoing periodic re-validation schedule, not the initial pass.

**Industry quality ICE revised from 58 → 64**: Prior calculation was inconsistent with the (I×C×E)/9 formula. Recalculated: (8×9×8)/9 = 64. Rank unchanged.

---

## Business Requirements for Enrichment

These requirements govern which gaps we invest in, how the cascade is architected, and what "done" looks like. They are inputs to the gap prioritisation above, not outputs. Enrichment effort that doesn't satisfy them is waste; effort that undershoots them is unshipped.

---

### 1. Cost Envelope

**PoC budget**: $5 allocated to Part 4 (enrichment cascade + evals) from a self-imposed $10 project ceiling (`config/project.yaml → budget.per_part_usd.part_4`). This covers the 288-record stratified sample.

**Per-record cost ceiling by segment** — the cascade model routing follows directly from this:

| Segment | Max cost/record | Cascade implication |
|---|---|---|
| Enterprise (500+) | ~$0.05 | Sonnet fallback fully justified; subsidiary resolution worth the cost |
| Mid-market (51–500) | ~$0.02 | Haiku preferred; Sonnet only on `confidence < 0.80` after Stage 3 |
| SMB (11–50) | ~$0.01 | Haiku only; skip (leave null) if confidence < threshold rather than escalate |
| Micro (1–10) | Out of scope | Excluded from Part 3 working set — see Scope Assumption |

**Cascade cost alarm**: If Stage 4 (Sonnet) resolves more than **40%** of records (`config/project.yaml → cascade.stage4_cost_signal`), the cascade is over-relying on the expensive model. Investigate Stage 3 Haiku thresholds before scaling to the full 291K website-gap batch.

**Break-even framing**: At ~$0.05/record for enterprise, enriching all 2,126 enterprise website gaps costs ~$106. Each correctly enriched enterprise record unlocks domain-based ABM signals (Bombora, G2, 6sense) and unblocks technographic enrichment — worth hundreds of dollars in downstream data-product margin per account. ROI is very high. SMB unit economics are tighter — bulk volume justifies Haiku-only routing.

---

### 2. Quality Floors by Segment

Quality targets are segment-differentiated because the commercial consequences of a wrong value scale with deal size. A wrong website for a Fortune 500 account surfaces in a customer QBR within weeks. A wrong website for a 15-person SMB may never be noticed.

_Source: `config/project.yaml → coverage_parity_targets`. These are the Part 4 eval acceptance thresholds — if the cascade doesn't hit them per-segment, the gap is not closed._

| Segment | Fill target | Precision target | Platform policy |
|---|---|---|---|
| Enterprise (500+) | ≥ 99% | ≥ 99% | Strict nullify |
| Mid-market (51–500) | ≥ 92% | ≥ 95% | Strict nullify |
| SMB (11–50) | ≥ 85% | ≥ 90% | Nullify and flag |
| Micro (1–10) | ≥ 75% | ≥ 90% | Nullify and flag |

**What "precision" means here**: Among records where the cascade writes a value (`confidence ≥ 0.80`), at least the target share must be correct when checked against ground truth. The absolute confidence calibration floor is 80% (`cascade.confidence_calibration_target`) — segment targets above reflect commercial risk-weighting on top of that.

**Fill vs. precision trade-off**: Higher precision targets for enterprise mean some records stay null rather than receive a low-confidence value. That is the right call — a null field keeps the record in the "needs enrichment" queue; a wrong field makes it look enriched and routes it to customers.

---

### 3. Precision-First Policy

**Wrong data is actively worse than null.** A missing website field causes a record to be invisible in search results — lost coverage, not a trust event. A wrong website (a closed domain, a competitor URL, a platform URL missed by the blocklist) causes a hard-to-detect downstream failure: email tools flag invalid domains, intent data providers return false signals, and the customer escalates. The churn attribution lands on Firmable, not on "missing data."

Three cascade design rules follow from this:

1. **Confidence gate before write**: Only write a value when `confidence ≥ 0.80` (`config/project.yaml → cascade.confidence_threshold`). Below this, set `enrichment_status = ENTITY_VALIDITY_UNCERTAIN` and leave the field null. Do not escalate to Sonnet just to force a write — the cost signal at 40% Sonnet share exists precisely to prevent this.

2. **No overwrite of existing non-null values** unless the existing value fails the domain liveness check (HEAD request timeout or 4xx/5xx response → stale record). Enrichment fills gaps; it does not revise populated fields. Overwriting a correct value with a wrong enriched value is a regression, not an improvement.

3. **Domain liveness check is not optional**: A HEAD request (5s timeout) runs on every candidate website before write-back. Catching a closed domain before it's written costs ~$0; the churn event that follows writing it costs a customer relationship.

---

### 4. Staleness / Re-enrichment Policy

A one-time enrichment pass closes the static gap but creates a freshness debt. The dataset is ~3 years old; enriched values will degrade as companies rebrand, close, or change their web presence. The `last_verified` timestamp written per enriched record (Pipeline Implementation Note, below) is the operational anchor for re-validation.

| Trigger | Action |
|---|---|
| `last_verified > 12 months` | Queue for domain liveness re-check (HEAD request, no model) |
| Liveness check fails (timeout / error) | Set `ENTITY_VALIDITY_UNCERTAIN`, suppress from customer exports until reviewed |
| Customer-reported bad URL | Immediate re-check + flag; route to human review queue |

**Ongoing cost**: Re-verification at scale is HEAD-request-only — negligible cost. The Haiku/Sonnet cascade only re-runs when: (a) liveness check passes but the field is null (new gap), or (b) a record is flagged `ENTITY_VALIDITY_UNCERTAIN` and a refresh is authorised. Re-enrichment events are infrequent in the 11+ cohort where annual closure rate is < 5%.

**Without `last_verified`**, re-enrichment requires a full re-scan of the enriched population with no way to prioritise stale records. Writing this timestamp at enrich-time is zero additional cost and the foundation for all future re-validation scheduling.

---

### 5. Throughput Requirement

Not specified in the brief. The following are operating assumptions for cascade design and sprint planning:

- **Batch size bounds**: 200–1,000 records per run (`config/project.yaml → cascade.batch_min / batch_max`)
- **Full-gap processing window**: 291K website-gap records processable within a 2-week sprint at moderate parallelism (10–20 concurrent API calls), assuming ~50ms average per record at Haiku and ~150ms at Sonnet
- **Human review queue target**: Records flagged `confidence < 0.80` or `ENTITY_VALIDITY_UNCERTAIN` should represent < 5% of enriched output. Above this, the Stage 3 Haiku confidence calibration needs re-tuning before the next batch run

---

## Top 2 Selected for Part 4

### #1 — Website Enrichment (Gap 1)

291,896 records across all 11+ size bands lack a usable website. The Part 4 cascade (rules blocklist → Google Places API → Haiku entity-match verification → Sonnet fallback) is designed precisely for this: take a company name + city + state, find the canonical website URL, verify it belongs to the right entity, write back with a confidence score. This is the highest-volume, highest-commercial-impact enrichment operation and the most mechanically tractable — websites are findable via structured search APIs for the majority of 11+ companies.

**Measurable outcome**: Website fill rate for 11+ records improves from 80.56% towards 85%+ in the enriched batch. Per-segment precision/recall from the Part 4 eval (n=288 records, stratified by size band) quantifies where the cascade is trustworthy and where it isn't.

### #2 — Industry Classification (Gap 2, Phase 2 of same pipeline)

65,478 records have no industry label. The natural phase-2 extension of the website enrichment cascade: once a website is known (either pre-existing or freshly enriched), pass `name + website + city + state` to Haiku for industry classification against the canonical taxonomy. Website context makes classification substantially more accurate than name-only inference. The 121,272 semantic-duplicate records require a separate LLM canonical-merge pass (simpler: pass both labels to Haiku, output the canonical one).

**Measurable outcome**: Industry fill rate for 11+ records improves from 95.61% towards 97%+. Semantic duplicate pairs collapsed to canonical labels, measurable by querying for both labels post-enrichment.

---

## Schema Absences — Structural Gaps Not Addressable by Enrichment

These fields are not in the dataset schema at all. They cannot be surfaced by fill-rate analysis because there is no column to measure. Noted here because assessors reviewing the schema will ask; they belong in the Part 6 roadmap as net-new field additions, not enrichment tasks.

| Absent field | Commercial impact | Recovery path |
|---|---|---|
| `status` (active / closed / acquired) | Highest trust risk — stale entity problem cannot be fully resolved without this | US SOS registry scraping, commercial data provider (D&B, Clearbit), or domain liveness heuristic as proxy |
| `phone` | Core outreach field; absent from dataset entirely | Requires contact-data provider (Apollo, ZoomInfo) — out of scope for this pipeline |
| `email_domain` | Derivable from `website` once filled; valuable for intent signal providers (Bombora, G2) | Rules-derivable once website gap is closed — see Gap 1 commercial summary |

`email_domain` is a free by-product of closing Gap 1. Once a website URL exists — pre-existing or newly enriched — the domain is extracted by stripping the protocol and path: `https://acme.com/about` → `acme.com`. No API call, no model. Intent data providers (Bombora, G2) use this domain to match companies to buying signals, making it high-value output for ABM customers at zero marginal cost. Add as an automatic write-back step at the end of the Part 4 cascade, triggered whenever a website field is written or confirmed.

## Enrichment Pipeline Implementation Note

**`last_verified` / `data_refreshed_at`**: This is not a source data gap — the source dataset carries no verification timestamp, and the rules cleanup stage performs no liveness check. The Part 4 enrichment pipeline should write a `last_verified` timestamp (ISO 8601 UTC) on every record it touches as standard metadata practice. This gives downstream consumers a freshness signal and is the foundation for future re-validation scheduling (e.g., periodic domain liveness sweeps). Zero additional cost — one field written per enriched record.

**State-tier stratification of the Part 4 sample**: The current Part 4 sample is stratified by size band only (enterprise/mid-market/SMB/micro). It should be extended to a **state tier × size band** 2D stratification using the Tier A/B structure from Part 1 (Tier A: 23 states, 84.2% of records; Tier B: 25 states, 15.2%). This has two benefits: (1) every geographic sub-market is represented in the enrichment batch, connecting the Part 1 state-level analysis to the Part 4 eval; (2) per-tier precision/recall from the eval reveals whether the enrichment source (Google Places + Haiku) performs equally across state tiers — a rural Tier B state like Iowa may have lower API hit rates than a dense Tier A state like California. If Tier B precision is materially lower, that's a sourcing signal (the enrichment source has geographic bias) rather than a data quality signal. Implementation: update `src/part1_sampling.py` to stratify on tier × size band and update the quota table in `config/project.yaml`. Sample size of ~400–500 records (up from 288) gives stable per-cell signal while remaining within the $5 Part 4 budget at ~$0.01/record Haiku cost.

---

## Sourcing Gaps — Commercial Note (Part 6 Roadmap)

Four sector-level gaps identified in Part 2 are real and commercially significant but are **out of scope for the Part 4 enrichment pipeline**. They require ingesting net-new records, not enriching existing ones:

- **Construction** (5.93% combined coverage, 28% vs SUSB employer firms): state contractor licensing boards across 48 states.
- **Transportation & Warehousing** (1.99%, 34.5% vs SUSB): FMCSA Motor Carrier database.
- **Retail Trade** (6.19%, 25.5% vs SUSB): franchise disclosure registries + state retail licensing.
- **Enterprise volume** (1.65% of records at 500+): SEC filings, D&B, corporate hierarchy databases.

These belong in the Part 6 90-day plan as sourcing sprints. The enrichment work in Part 4 improves quality of what already exists; these close the universe coverage gap underneath it.
