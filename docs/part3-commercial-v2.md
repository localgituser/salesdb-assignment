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

_See `docs/part4-enrichment.md` for the full cascade design (rules → Haiku search → Haiku verify → Sonnet fallback), output schema, eval results, and cost breakdown. What follows is a summary of the dependency sequencing that informed the Part 4 PoC scope._

### Phase 0 — Deterministic cleanup (runs before any enrichment spend)

Two Must items have free, deterministic solutions and no dependencies. Both must complete and produce a clean `part0_companies_clean.parquet` before the pipeline runs.

**Cleanup pre-pass** — Extend blocklist with the categories identified above (site builders, GMB, e-commerce platforms, content/media, community platforms, URL shorteners, email-as-URL). Franchise domains flagged as `WEBSITE_WRONG_ENTITY` and routed to enrichment queue — not nullified. Cost: $0.

**State null recovery (deterministic path)** — Join null-state records against USPS city→state crosswalk. Unique matches applied deterministically. Ambiguous cities logged as `STATE_AMBIGUOUS`. No model call. Cost: $0.

### Phase 1 — Enrichment pipeline (Part 4 PoC)

The three Must items (cleanup pre-pass, state recovery, website enrichment) resolve in dependency order. Website unblocks industry and type inference — they run in the same cascade pass, not separately. See `docs/part4-enrichment.md` for the stage-by-stage design, model choices, cost breakdown ($2.38 actual for 288 records), and eval results (website P=0.75, type P=0.90, industry P=0.60, size P=0.38).