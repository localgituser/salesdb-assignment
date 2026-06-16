# Part 3 — Commercial Framing & Gap Prioritisation (v2)
_Revised: 2026-06-16 | Supersedes: `docs/part3-commercial.md` (ICEE framework)_
_Scope: 11+ employee records — 1,491,060 working set. Micro (1–10) excluded; see v1 §Scope Assumption for rationale._

---

## Framework

**MoSCoW** — each gap classified into one of four buckets based on a single question: _can we ship this data to a customer without fixing it?_

- **Must** — no. Shipping without fixing this actively harms customers or wastes all downstream enrichment spend.
- **Should** — yes, but the product is measurably worse. Fix in the next sprint.
- **Could** — beneficial but low commercial urgency. Backlog.
- **Won't** — out of scope for this pipeline window. Explicitly accepted.

Within **Must**, no further priority ranking is needed — all items must be resolved before the enriched dataset is customer-facing. Sequencing within Must is driven by the dependency map below, not by rank.

---

## Cleanup Pre-Pass (runs before gap sizing)

Domain distribution analysis (DuckDB query on `part0_companies_clean.parquet`) revealed the blocklist is significantly incomplete. These are not enrichment gaps — they are misclassified records currently counted as "has website" that must be reclassified to null before any gap count is meaningful.

### Platform and builder URLs (null-equivalent — no entity-specific content)

| Category | Domains | Records (11+) |
|---|---|---|
| Site builders (current blocklist) | `wixsite.com`, `wordpress.com`, `weebly.com`, `webs.com`, `wix.com` | ~2,138 |
| Site builders (missing from blocklist) | `godaddysites.com`, `webflow.io`, `carrd.co`, `homestead.com`, `tripod.com` | ~234 |
| Google My Business | `business.site` | ~287 |
| E-commerce platforms | `etsy.com`, `myshopify.com`, `square.site` | ~109 |
| Content / media platforms | `medium.com`, `substack.com`, `vimeo.com`, `tumblr.com`, `spotify.com`, `buzzsprout.com` | ~97 |
| Community platforms | `meetup.com`, `wildapricot.org` | ~108 |
| Directory / reference | `bbb.org` (BBB listing stored as company website) | ~89 |
| URL shorteners | `tinyurl.com` | ~84 |
| Email addresses stored as URLs | `gmail.com` | ~44 |
| International `.gov` variants | `.gov.au`, `.gov.uk`, `.gov.ca` etc. — not caught by `.gov`-only suffix check | Unknown |
| International Yelp TLDs | `yelp.ca`, `yelp.co.uk` etc. | ~26 |
| Blogspot subdomains | `*.blogspot.com` | ~238 |

All of the above are null-equivalent: reclassify to null and add to the enrichment queue.

### NFP Platform


`thetopperson.com` — 641 records. This is a global charity and digital publishing platform that operates a free Ambassador Program. It primarily focuses on helping individuals and businesses boost their social media visibility, particularly on LinkedIn, by providing digital tools, strategies, and networking opportunities with decision-makers.

### Franchise / parent brand domains (different problem — entity is real, URL is wrong)

| Domain | Records (11+) | Issue |
|---|---|---|
| `marriott.com`, `hilton.com`, `hyatt.com` | ~1,326 | Hotel property records assigned the parent brand's corporate domain |
| `apple.com` | ~32 | Apple Store locations assigned the corporate domain |
| `expresspros.com` | ~215 | Staffing agency branch locations assigned the parent domain |
| `ajg.com` | ~149 | Arthur J. Gallagher insurance agent locations |

These are not null-equivalent. The entity is real and operating; the website value is wrong (it resolves to the parent brand, not the specific location). They require discovery enrichment to find the location-specific URL — they should be flagged and routed to the website enrichment queue, not silently reclassified to null.



### Industry taxonomy cleanup

| Item | Records | Effect |
|---|---|---|
| Semantic dedup — 3 label pairs (`it services and it consulting` / `information technology & services`, `wellness and fitness services` / `health, wellness & fitness`, `non-profit organizations` / `non-profit organization management`) | 121,272 | Shrinks apparent industry gap from 186K to 65K genuinely missing records |

### Post-cleanup gap baseline

These are the numbers that matter. The website gap figure is a **lower bound** — the full blocklist extension above has not been applied programmatically; exact post-cleanup count pending.

| Gap | Records (11+ scope) |
|---|---|
| Website missing (true, post-cleanup — lower bound) | ~292,131 + blocklist extension delta |
| Industry missing (genuinely null, post-dedup) | 65,478 |
| State null residual (post Part 1.5 rules recovery) | 124,525 total / 13,061 enterprise (51+) |
| Type missing — public companies | ~40,000 (estimated) |
| Type missing — private / unknown | Remainder of ~45.1% null `type` cohort |
| Founded year missing | ~2.25M (national; 11+ rate not separately measured) |

---

## Field Dependency Map

Arrows show what a resolved gap unlocks. Sequencing within Must follows these arrows.

```
Cleanup pre-pass (blocklist extension, semantic dedup)
    └──> makes gap counts accurate
    └──> removes platform/franchise URL noise before enrichment

State recovery (deterministic: city→state)
    └──> improves website enrichment query precision (name+city+state vs name+city only)
    └──> must complete before website enrichment runs

Data trust characterisation (Spike)
    └──> confirms whether clean-domain population is trustworthy
    └──> informs Part 4 cascade design (or becomes Part 4 if Spike succeeds)

Website enrichment
    └──> unlocks industry inference (homepage is the primary classification context)
    └──> unlocks email_domain (rules-derivable, $0 marginal cost, no API call)
    └──> unlocks entity type inference for private/unknown (homepage signal)
    └──> unblocks state recovery LLM path for city-null records (website HQ inference)

Industry semantic dedup (cleanup)
    └──> reduces mislabel noise in industry inference prompts
    └──> makes industry gap count accurate before enrichment runs
```

---

## MoSCoW Gap Classification

### Must

| Gap | Rationale |
|---|---|
| **Cleanup pre-pass** (full blocklist extension, semantic dedup, franchise domain flagging) | Distorts gap sizing and enrichment queue composition if unfixed. Must complete before any gap is measured or actioned. The blocklist is materially larger than previously documented — see table above. |
| **Data trust characterisation** (LLM comparison Spike) | Before spending enrichment budget, confirm the clean-domain population is trustworthy and the LLM-from-Name+City+State approach is viable. URL liveness is not a valid substitute — it is a hosting signal, not an entity signal. This Spike either becomes Part 4 or defines its cascade architecture. |
| **State null recovery — deterministic path (city→state lookup)** | Two reasons. (1) Geographic visibility: 13,061 enterprise records are invisible in any state-filtered search. (2) Cascade pre-condition: the website enrichment query uses `name + city + state`; null state degrades query precision and raises wrong-entity match risk. Deterministic lookup is $0 and covers the majority of the 124,525 residual. Must complete before website enrichment runs. |
| **Website enrichment** | Upstream blocker for the entire enrichment chain. No website means: no email domain inference, no industry classification via homepage, no entity type signal, no intent data match key. Affects 292K+ records across all 11+ size bands. Every customer is affected regardless of vertical or ICP. |
| **Industry — missing labels (genuinely null, post-dedup)** | 65,478 records are invisible in any vertical ICP filter — the primary search dimension for Sales Intelligence. Recoverable via homepage inference once website is known; natural phase-2 step in the same cascade as website enrichment. |

---

### Should

| Gap | Rationale |
|---|---|
| **Type — public companies (SEC/ticker lookup)** | Deterministic, free, near-perfect precision. ~40K records in the 11+ working set are publicly traded with `type IS NULL`. An offline ticker file join closes this with no model calls. Narrow scope but zero cost — ship as soon as the lookup file is sourced. |
| **State null recovery — LLM tail (city-null records with website)** | Smaller volume than the deterministic path. Requires a website to be present (homepage HQ inference). Blocked until website enrichment has run — cannot be sequenced until Must items are complete. |

---

### Could

| Gap | Rationale |
|---|---|
| **Founded year missing (~2.25M null)** | Secondary ICP signal. Not a first-order search filter. Recovery requires a structured database (Crunchbase, D&B) or per-record website scrape — no deterministic path. Low ROI relative to Must gaps; revisit after website and industry are stable. |

---

### Won't (this window)

| Gap | Rationale |
|---|---|
| **Type — private / unknown (LLM inference)** | Blocked on website availability for most affected records. Low confidence without a structured source. Accept as null for now. |
| **Phone** | Not in dataset schema. Requires a contact-data provider (Apollo, ZoomInfo). Out of scope. |
| **Founded year via paid API** | Expensive per-record cost with no deterministic fallback. Won't in this window. |

---

## Implementation Approach

### Phase 0 — Deterministic cleanup (runs before any enrichment spend)

Two Must items have free, deterministic solutions and no dependencies. Both must complete and produce a clean `part0_companies_clean.parquet` before the pipeline runs.

**Issue 1 — Cleanup pre-pass**

Extend `config/project.yaml → enrichment_rules.platform_blocklist` with the categories identified above (site builders, GMB, e-commerce platforms, content/media, community platforms, directory listings, URL shorteners, email-as-URL). Add regex support to `src/shared/rules.py` for subdomain patterns (`*.blogspot.com`) and international suffix variants (`.gov.au`, `yelp.ca` etc.). Franchise domains (`marriott.com`, `hilton.com`, `expresspros.com`, `ajg.com`) are flagged as `WEBSITE_WRONG_ENTITY` and routed to the enrichment queue — not nullified, because the entity is real.

`thetopperson.com` (641 records): null-equivalent — it provides no entity-specific URL content. Reclassify to null and add to enrichment queue.

Cost: $0.

**Issue 3 — State null recovery (deterministic path)**

Join null-state records against an offline US city→state lookup (USPS City/State file or Census ZCTA crosswalk) on normalised city name. Unique matches are applied deterministically. Ambiguous city names (multiple states) are logged as `STATE_AMBIGUOUS` and deferred to the Should-tier LLM tail. Does not require a model call.

Cost: $0.

---

### Phase 1 — Enrichment pipeline (Part 4 PoC)

**Why Issues 2, 4, and 5 collapse into one run**

The original plan treated the data trust Spike (Issue 2) as a separate pre-step. It is not. The Spike's purpose is to validate that the search → LLM verify cascade produces reliable output before spending enrichment budget. The correct way to do that is to *run the cascade on records where we already know the answer* (clean-website population) and measure how often it's right — which is the same run as the Part 4 PoC, just on a different input slice. Separating them doubles the engineering work for no additional signal.

The merged run produces three outputs in one pass:
1. **Reliability scores on existing values** — for records that already have values, the pipeline runs and compares its findings to the stored values. Match → confirmed. Mismatch → flag as `{FIELD}_SUSPECT`.
2. **Enriched values for null fields** — website, type, industry, and size filled where missing.
3. **Per-segment precision/recall** — stratified sample (enterprise / mid-market / SMB / micro) tells us which size bands the cascade is trustworthy for at full scale.

**Target fields and their system taxonomies**

Each field Gemini extracts must use the exact enumeration already in the dataset — no free-text, no synonyms.

| Field | Allowed values (exact) |
|---|---|
| `type` | `Privately Held`, `Self-Owned`, `Nonprofit`, `Partnership`, `Public Company`, `Self-Employed`, `Educational`, `Government Agency` |
| `size` | `1-10`, `11-50`, `51-200`, `201-500`, `501-1K`, `1K-5K`, `5K-10K`, `10K+` |
| `industry` | 491 lowercase labels (see taxonomy note below) |

**Industry taxonomy note**: 491 labels is too large to enumerate in Gemini's prompt as a constrained enum — the token overhead is ~2,000 tokens per call and Gemini's grounding-based extraction doesn't benefit from a closed label list at retrieval time. The split is:
- **Gemini Stage 1**: extracts `industry_raw` as a short free-text description of what the company does (2–4 words, from web sources).
- **Haiku Stage 2**: maps `industry_raw` → the nearest valid taxonomy label, with the full 491-label list passed in the system prompt. Haiku is well-suited to this: it's a classification task on short text with a fixed label space, not a web retrieval task.

`type` and `size` are included directly in Gemini's JSON schema as constrained enums — small enough (~8 values each) to enforce at the extraction layer without token cost.

**Cascade design**

```
Stage 0 — Rules layer ($0)
  Input:  name, city, state, existing field values
  Output: email_domain derived from known website (regex, $0)
          WEBSITE_WRONG_ENTITY flag for franchise domains → enrichment queue
          Skip fields that are already confirmed clean (post-cleanup)
          Pass-through: carry existing non-null values so Stage 1 can
          score their reliability even when not filling a gap.

Stage 1 — Search + multi-field extraction (Gemini Flash + Google Search Grounding)
  Input:  name, city, state
  Output (structured JSON, enforced by schema):
    candidate_website:    string | null
    candidate_type:       enum[type values] | null
    candidate_size:       enum[size bands] | null
    industry_raw:         string (free-text, 2–4 words) | null
    field_confidences:    { website: 0–1, type: 0–1, size: 0–1, industry: 0–1 }
    search_citations:     string[]

  Why Gemini Flash: Google Search Grounding means retrieval is from live web
  results, not parametric memory — correct for SMB/micro that Haiku/Sonnet
  would not have seen during training. Structured output API enforces the JSON
  schema. ~$0.075/M tokens; per-call cost ~$0.0002 (larger prompt than before).
  Fallback: if grounding returns no usable results, all candidates null,
  stage=NO_CANDIDATE.

Stage 2 — Verification + industry taxonomy snap (Claude Haiku)
  Input:  original record fields, Stage 1 candidates, industry_raw
  Output:
    website_verified:     yes / no / uncertain
    type_verified:        yes / no / uncertain  (or accepted if record had no prior value)
    size_verified:        yes / no / uncertain
    industry_label:       canonical taxonomy label (snapped from industry_raw)
    industry_confidence:  0–1
    per_field_confidence: { website: 0–1, type: 0–1, size: 0–1, industry: 0–1 }
    reasoning:            one sentence per uncertain field

  Full 491-label taxonomy passed in Haiku system prompt for industry snapping.
  Haiku is NOT doing web recall — it is (a) judging Gemini's candidates against
  the record's known identity context, and (b) mapping industry_raw to the
  nearest label in the closed taxonomy.
  Per-call cost ~$0.0006 (slightly larger input due to taxonomy list).

Stage 3 — Disagreement resolution (Claude Sonnet) [conditional]
  Fires when: any field has Haiku verdict = uncertain, OR Gemini and Haiku
  confidences conflict by > 0.3 on the same field.
  Input:  full context — original record, Stage 1 candidates + citations,
          Stage 2 verdicts + reasoning
  Output: final values for disputed fields, final_confidence per field,
          resolution_note
  Why Sonnet: nuanced judgment on ambiguous cases — e.g., a company that
  operates in two industries, or a franchise location where size and type
  conflict with the parent brand's signal.
  Expected to fire on ~15–20% of records. Per-call cost ~$0.004.
```

**Confidence tiers and field-level output schema**

Confidence is tracked per field, not per record — a record can have HIGH confidence on `website` and LOW on `size` simultaneously.

| Tier | Condition | Action |
|---|---|---|
| **HIGH** | Gemini ≥ 0.7 AND Haiku verified AND confidence ≥ 0.8 | Ship field — no further review |
| **MEDIUM** | Both agree but one below threshold | Ship field with `review_flag = true` |
| **LOW / ESCALATE** | Haiku uncertain or conflict → Sonnet fires | Ship Sonnet output if ≥ 0.7; else retain existing value (or null if was already null) |
| **NO_CANDIDATE** | Stage 1 found nothing for this field | Retain existing value unchanged; log |

Every output record carries the following schema. Fields marked **[per field]** repeat for each of `website`, `type`, `industry`, `size`.

| Column | Type | Description |
|---|---|---|
| `handle` | string | Primary key — join key back to source dataset |
| `enriched_at` | ISO 8601 timestamp | When this pipeline run produced the record |
| `pipeline_version` | string | Version tag of the cascade script (for reproducibility) |
| `{field}_original` | string \| null | **[per field]** Value as it existed before this run |
| `{field}_enriched` | string \| null | **[per field]** Value the pipeline produced (null if NO_CANDIDATE) |
| `{field}_final` | string \| null | **[per field]** Value to write back: enriched if original was null; original if pipeline deferred |
| `{field}_original_correct` | bool \| null | **[per field]** Did the pipeline agree with the original value? `true` = confirmed, `false` = conflict flagged, `null` = original was null (no prior value to validate) |
| `{field}_confidence` | float 0–1 | **[per field]** Confidence in `{field}_final` |
| `{field}_pipeline_stage` | string | **[per field]** Which stage produced the final answer: `rules`, `gemini`, `haiku`, `sonnet`, `NO_CANDIDATE` |
| `{field}_review_flag` | bool | **[per field]** True if medium-confidence or conflict — needs human spot-check |
| `enrichment_status` | string | Record-level summary: `FULLY_ENRICHED`, `PARTIALLY_ENRICHED`, `NO_CANDIDATE`, `CONFLICT` |

The `{field}_original_correct` column is the data validity audit trail. Over time, aggregate correctness rates by field × size band give a live measure of how reliable the source population is — not just what's missing, but how wrong the existing values are.

The `handle` is the join key back to the source dataset.

**Eval**

20+ records hand-labelled before the pipeline runs — populates `evals/ground_truth.json` (currently empty). Stratified: 5 enterprise, 5 mid-market, 5 SMB, 5 micro. Ground truth covers all four target fields (website, type, industry, size) so precision/recall is reportable per field per segment.

Ground truth must be hand-labelled — not generated by any model. Using LLM output as ground truth to validate LLM output is circular.

**Cost estimate (288-record PoC)**

| Stage | Calls | Unit cost | Total |
|---|---|---|---|
| Stage 1 — Gemini Flash | 288 | ~$0.0002 | ~$0.06 |
| Stage 2 — Haiku | 288 | ~$0.0006 | ~$0.17 |
| Stage 3 — Sonnet (~18% of records) | ~52 | ~$0.004 | ~$0.21 |
| **Total** | | | **~$0.44** |

Well within the $5 Part 4 budget. Remaining budget covers iteration and re-runs.

**Full-scale projection (292K website-null records, post-PoC approval)**

| Stage | Total cost |
|---|---|
| Stage 1 — Gemini Flash | ~$58 |
| Stage 2 — Haiku | ~$175 |
| Stage 3 — Sonnet (~18%) | ~$215 |
| **Total** | **~$448** |

Industry and type/size null populations partially overlap with the website-null population, so many records get all four fields filled in a single pipeline pass — no separate industry or type enrichment run needed for those records.

---