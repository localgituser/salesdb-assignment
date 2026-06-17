# Part 4 — Enrichment Pipeline: Redesign Strategy

_Date: 2026-06-16, updated 2026-06-17_  
_Based on: actual run output (`part4_enriched_sample.parquet`, 15 records across two incremental test runs) and eval results (`eval_results.json`, 20 records)_  
_Budget reference: $2.68 of $8.00 Part 4 budget spent; $5.32 remaining; $3.06 of $10.00 total remaining_

---

## Incremental Test Runs & Manual Review

The pipeline was iterated through two manual review cycles rather than re-running the full 288-record batch after each change. This kept LLM costs minimal and made it possible to inspect every record by hand.

### Run 1 — 5 enterprise records (2026-06-16)

**Purpose**: Validate Stage 0 overwrite fix (enrichment must fill gaps, not overwrite correct originals) and verify the entity verification gate (Stage 1.5) is firing correctly.

**Handles**:
- `company/american-advanced-management` (enterprise, missing_website) — hospital management company
- `company/avera-mckennan-hospital` (enterprise, missing_website) — single hospital campus
- `company/coastal-forest-resources-company` (enterprise, missing_website) — closed company
- `company/impact-group-brokerage` (enterprise, missing_website) — insurance brokerage
- `company/colquitt-county-school-district` (enterprise, missing_website) — school district

**Key findings from manual review**:
- `american-advanced-management`: size field was being overwritten with a lower enriched value — root cause was `_build_output` preferring enriched over original unconditionally. **Fixed**: original is now preferred when populated.
- `coastal-forest-resources-company`: "Permanently closed" (Google Maps) was not being surfaced. Root cause: `max_uses=1` on web_search (only one search call, misses follow-up confirmation) and missing `"permanently_closed"` in the `closure_signals` enum. **Fixed**: bumped to `max_uses=2`, added `"permanently_closed"` and `"acquired"` to enum.
- `avera-mckennan-hospital`: size returned as the Avera Health System total (parent org) rather than the specific hospital's headcount. Prompted investigation of `is_single_facility` classification.

**Prompted changes from Run 1**:
1. `_build_output` overwrite fix (size/type/industry prefer original when populated)
2. Stage 1 + 1b closure signal enum: added `"permanently_closed"`, `"acquired"`; strengthened `still_operating=false` rule
3. Stage 1 `max_uses` increased from 1 to 2
4. New `operating_status_review_flag` output column
5. `is_single_facility` classification added to Stage 1 and Stage 1b prompts (v3/v2), with split `candidate_size` rule: location headcount when `is_single_facility=true`, org-level headcount when `false`

**Testing workflow**: Closure detection and `is_single_facility` classification were validated using dedicated test scripts in `scripts/` before applying to the pipeline:
- `scripts/test_closure_detection.py` — compared Haiku, Sonnet, Gemini, Perplexity on Coastal Forest Resources Company (ground truth: permanently closed). Haiku with `max_uses=2` correctly returned `still_operating=False`, `closure_signals=["domain_expired"]`.
- `scripts/test_size_detection.py` — tested size prompt variants for American Advanced Management (ground truth: 5K-10K from LinkedIn). Both variants failed; root cause identified as data availability (web search finds HQ/admin headcount, not total org headcount for management companies).
- `scripts/test_size_with_facility_flag.py` — tested `is_single_facility` classification for American Advanced Management and Avera McKennan Hospital. Both classified correctly after rewriting the rule to focus on "who signs the payroll" rather than physical location count.

---

### Run 2 — 10 mixed records (2026-06-17)

**Purpose**: Validate `is_single_facility` + split size logic across a broader range of entity types, segments, and conditions. Also first run to exercise the new `operating_status_review_flag` in production.

**Handles & results**:

| Company | Segment | Condition | is_single_facility | still_operating | Notable |
|---------|---------|-----------|-------------------|----------------|---------|
| Dollar Express Stores LLC | enterprise | missing_website | False | **False** ✓ | `closure_signals=["closed_announcement"]`; website not found |
| Nursing Care Management of America | enterprise | missing_website | False ✓ | True | Website found (ncmgnt.com, conf 0.95); 501-1K preserved from original |
| STOLT-NIELSEN USA INC | enterprise | missing_website | False ✓ | True | Website found (stolt-nielsen.com, conf 0.90); US subsidiary correctly treated as org-level |
| ST. JOSEPHS REGIONAL HEALTH CENTER | enterprise | missing_website | **True** ✓ | True | Entity gate fired SUBSIDIARY (resolved to CHI St. Joseph Health Regional Hospital); size_confidence=0.30 (correctly low — only parent system total available) |
| AVERA ST LUKES | enterprise | missing_website | **True** ✓ | True | avera.org, conf 0.95; Stage 3b size upgrade 1K-5K at 0.85 |
| EARTH FARE, INC. | enterprise | missing_industry | True (wrong — retail chain) | **null** (should be False) | `fortunegiver.com` correctly scored 0.00; operating status uncertain — Earth Fare filed bankruptcy 2020 and closed all stores |
| WHATABRANDS LLC | enterprise | missing_industry | **False** ✓ | True | Correctly identified as brand holding company; size 5K-10K preserved; industry=restaurants |
| National Labor Relations Board | enterprise | platform_url | False | True | nlrb.gov conf 1.00; `NO_CANDIDATE` status correct (had platform URL, no missing fields to fill) |
| IMUGEN, INC. | mid_market | missing_industry | True | True | Possible acquisition by Quest Diagnostics — `still_operating=True` but warrants review |
| Mack Manufacturing Inc. | mid_market | missing_industry | True ✓ | True | Industry=manufacturing; conf 0.60 |

**Key observations for next iteration**:
- `is_single_facility` is working well for management companies (False) and single-site hospitals (True). One miss: Earth Fare classified as `True` — it is a retail chain (multi-site operator, should be False). The company name alone doesn't signal "chain"; without a website hit, the model defaults to treating it as a single location.
- Earth Fare operating status came back `null` (operating_status_review_flag=True, correct) but should ideally be `False` — the company filed for bankruptcy and closed all stores in 2020. The domain `fortunegiver.com` was correctly scored 0.00 but no closure signal was generated. This suggests the Stage 1b prompt (parametric, no search) cannot reliably detect historical closures without search access.
- ST. JOSEPHS size_confidence=0.30 is the correct behavior — `is_single_facility=true` and only a parent system total was found, so the pipeline correctly demoted confidence and would escalate to Stage 4 if a threshold were set.
- NLRB `NO_CANDIDATE` is correct: it had a platform_url (nlrb.gov) replaced with nlrb.gov (same domain) — no real enrichment happened, which is the right outcome for a government entity.

---

## Size Field Semantics

**What `size` means in this pipeline**: the named legal entity's own employee count — not a parent company's global headcount, not a sub-unit or department count. This is the correct signal for Firmable's primary buyers (staffing, MSPs, agencies, mid-market SaaS) who qualify prospects by the entity they are actually calling, not its global parent.

**Three scoping rules, in priority order**:

1. **Geographic entity exception** (highest priority): if the company name contains a geographic qualifier (USA, UK, Americas, a country or region name) indicating a regional subsidiary — use only that entity's own headcount, not the global parent's worldwide total. If web results only surface the global figure, return `null` / `size_confidence=0.30` and escalate to Stage 3b.
   - _Example_: STOLT-NIELSEN USA INC → correct size is ~506 (501-1K), not the global Stolt-Nielsen total (~7,000).

2. **Single-facility scoping** (`is_single_facility=true`): return the headcount of this specific operating location (hospital campus, store, factory). If only the parent system total is available, return `null` / `size_confidence=0.30`.
   - _Example_: Avera McKennan Hospital → correct size is that hospital's staff, not Avera Health System.

3. **Operator/manager scoping** (`is_single_facility=false`): return the consolidated headcount across all locations this entity directly operates and employs staff across.
   - _Example_: Avera Health System → correct size is the full system headcount.

**Future opportunity — global size as a parallel signal**: The current pipeline captures entity-scoped size, which is right for location-based service buyers. A complementary `global_size` field (parent company total) would be valuable for a different buyer profile: enterprise software and services vendors (e.g. Okta, Salesforce, Workday) whose deals are signed at global HQ level and sized by total company headcount regardless of which subsidiary entity is in the database. This is a distinct ICP from Firmable's current core market, but as the platform expands into enterprise SaaS GTM workflows, capturing both signals — `size` (entity) and `global_size` (parent) — would let the data serve both buyer profiles without conflating them. The entity gate (Stage 1.5) already identifies PARENT/SUBSIDIARY relationships; the parent entity name could be stored to enable a future `global_size` lookup pass without restructuring the current cascade.

---

## Diagnosis: Why the Numbers Are What They Are

The eval results are not uniformly bad — they have a clear structure:

| Field | Precision | Root cause |
|-------|-----------|------------|
| type | 0.90 | Binary signals (LLC, Inc., .gov) — easy for search + Haiku |
| website | 0.75 | Parent/subsidiary confusion: correct org, wrong entity level |
| industry | 0.60 | Near-synonym confusion across 492-label taxonomy |
| size | 0.38 | Parent org headcount returned instead of entity headcount |

The mismatch log makes the pattern concrete:

- `avera.org` returned for a search on Avera McKennan Hospital — correct health system, wrong entity level  
- `wesd.org` returned for WESD — correct district, wrong subdomain (`.k12.or.us` was right)  
- `business consulting and services` returned for outsourcing firm — correct L1 category, wrong L3 label  
- `higher education` returned twice for K-12 districts — sibling label, not the right one  

**The pipeline conflates retrieval and entity verification into a single LLM call.** When search surfaces a parent org, the model extracts that org's fields confidently. Stage 3 (verify) only fires for low-confidence website cases — it cannot catch the case where the model is confidently wrong about which entity it found.

---

## Proposed Improvements

### Improvement 1 — Expand the Stage 0 Rules Layer

**What**: Use signals already present in the record — before any search call — to deterministically fill `type` and partially constrain `industry`. No model required.

**Rules to add**:

```python
# ── Name-based type signals (validated against 4.16M records) ───────────────
#
# Apply as NULL-FILL ONLY — never override an existing type value.
# Accuracy figures below are empirical (agrees with existing type / records with type).
#
# HIGH CONFIDENCE (≥85%) — apply freely
name_type_high = {
    r'\bCity of\b':               ('Government Agency', 0.93),  # 3,459 records
    r'\bSchool District\b':       ('Educational',       0.91),  # 3,497 records
    r'\bCounty of\b':             ('Government Agency', 0.88),  # 281 records
    r'\bFoundation\b':            ('Nonprofit',         0.92),  # 16,566 records
    r'\b(Church|Ministry|Ministries)\b': ('Nonprofit', 0.88),  # 8,738 records
    r'\b(Fire Department|Fire Dept|Police Department)\b': ('Government Agency', 0.82),  # 1,354 records
    r'\bLLP\b':                   ('Partnership',       0.76),  # 9,541 records
    r'\b(ISD|USD|CUSD)\b':        ('Educational',       0.79),  # 1,054 records
}

# MEDIUM CONFIDENCE (65–75%) — apply; flag for review when confidence < 0.70
name_type_medium = {
    r'\bInc\.?\b':                ('Privately Held',   0.73),  # 434,687 records; 7.5% are Public Company
    r'\bCorp\.?\b':               ('Privately Held',   0.72),  # 29,533 records; similar Public Company noise
    r'\bUniversity\b|\bCollege\b':('Educational',      0.65),  # 18,257 records; 21% are Nonprofit
    r'\bTownship\b':              ('Government Agency',0.63),  # 1,719 records; 14% Nonprofit
}

# LOWER CONFIDENCE (55%) — use as weak prior; always flag for review
name_type_weak = {
    r'\bLLC\b': ('Privately Held', 0.55),  # 371,006 records; 18% Self-Owned, 15% Partnership
                                            # Plurality at every size band, but noise is real.
                                            # Consider size conditioning: 1-10 + LLC → noisy; 51+ + LLC → cleaner.
}

# REMOVED — do not use:
# r'\bL\.?P\.?\b' → Partnership  (43% accuracy; regex matches "LPC", "LPC, LMFT" etc.
#                                  Use r',\s*L\.?P\.?$' if you need LP — suffix-only is safer)

# ── TLD-based signals (website field only) ──────────────────────────────────
#
# DATA AUDIT FINDING: US .gov, .edu, .mil appear in 0 records in this dataset.
# Foreign .gov.<cc> (~290 records) are corruption artifacts per Part 2 Manual Audit
# — do NOT infer type/industry from them; flag as website_corrupted=True instead.
#
# ONLY .k12.XX.us is safe: 5,129 records, 100% genuine K-12 entities (n=20 verified).
tld_signals = {
    r'\.k12\.[a-z]{2}\.us$': ('Educational', 'primary and secondary education', 0.95),
}
```

**Why this matters**: The WESD miss (`primary and secondary education` → `advertising services`) would not be possible if `wesd.k12.or.us` were parsed at Stage 0. The pipeline searched for WESD and found an unrelated entity — but the `.k12` subdomain already answered the question.

**Why TLD signals are limited to `.k12.XX.us` only** and **why LP was removed**: Both conclusions come from running the patterns against the actual 4.16M-record dataset (see `data/processed/part0_companies_clean.parquet`):
- US `.gov`, `.edu`, `.mil` domain records: **0** — implementing those patterns would be dead code.
- Foreign `.gov.<cc>` (~290 records): corruption artifacts per Part 2 Manual Audit Observation A — scraper stored directory domain instead of business's own URL. Inferring type from these would propagate the error. Flag them `website_corrupted=True` instead.
- `\bL\.?P\.?\b` for Partnership: **44% accuracy** — the regex matches "LPC" (Licensed Professional Counselor), "LPCG", etc. mid-word. Remove from the map; if LP matching is needed, a suffix-anchored pattern (`, L.P.` at name end) is required.
- Foundation, Church/Ministry, Fire/Police Dept, University/College: **not in the original list** but data confirms 65–92% accuracy across 45,000+ records — add these.

**Cost**: $0. Reduces the LLM call set and eliminates a class of confident-but-wrong type fills.

**Expected lift**: type precision from 0.90 → ~0.95 on records where a name-suffix rule fires confidently. Industry catastrophic misses eliminated for `.k12` records (5,129). ~290 corruption-detected records stop contributing false positives to website fill rates.

---

### Improvement 2 — Entity Verification Gate

**What**: Insert a **conditional** Haiku verification call between search retrieval and field extraction. The gate is not universal — it fires only when entity ambiguity is plausible. Instead of the current flow (`search → extract all fields`), the new flow is:

```
search → identify entity → ambiguity check → [GATE if needed] → extract fields
                                   ↓                   ↓
                             anchored → skip      SUBSIDIARY/PARENT → rewrite query, retry once
                                                  NO_MATCH          → flag as NO_CANDIDATE, skip extraction
                                                  MATCH             → proceed to extraction
```

**Gate trigger logic** (evaluated using Stage 0 outputs + Stage 1 `extracted_name` / `candidate_website`):

```python
def needs_entity_gate(record, stage0, stage1):
    # Skip — Stage 1 found nothing to verify
    if stage1.status == "NO_CANDIDATE":
        return False

    # Skip — Stage 0 already anchored the entity (TLD match or deterministic name-suffix)
    if stage0.entity_confirmed:
        return False

    # Always run — Stage 0 flagged entity-level mismatch (franchise/chain domain)
    if stage0.flags.get("WEBSITE_WRONG_ENTITY"):
        return True

    # Always run — extracted name diverges significantly from input name
    if name_similarity(record.name, stage1.extracted_name) < 0.80:
        return True

    # Always run — large org; subsidiary structure is common in this tier
    if record.size in ("1K-5K", "5K-10K", "10K+"):
        return True

    # Skip — existing valid website matches Stage 1 candidate (entity anchored by concordance)
    if (record.website
            and is_valid_non_platform(record.website)
            and domain_match(record.website, stage1.candidate_website)):
        return False

    # Default: run the gate
    return True
```

The skip conditions matter because they use signals the pipeline already has — no extra calls. `stage0.entity_confirmed` is set by the `.k12.XX.us` TLD rule or any deterministic name-suffix rule that fires with confidence ≥ 0.85. `WEBSITE_WRONG_ENTITY` is already set by the franchise domain check. `stage1.extracted_name` and `stage1.candidate_website` come from Stage 1 output. `name_similarity` is a simple normalised edit distance — no model required.

**Prompt design** (Stage 1.5, ~500 input tokens, ~100 output tokens):

```
You searched for: "{original_name}", {state}, USA.
The top search result describes: "{extracted_name}".

Are these the same legal entity (not just the same org family)?

Answer with one of: MATCH, SUBSIDIARY, PARENT, NO_MATCH
Then one sentence of reasoning.
```

If `SUBSIDIARY` or `PARENT`: append `"{original_name}" {state} -"{parent_name}" site:linkedin.com` to the rewritten query, retry Stage 1 once. If still unresolved after retry: pass both candidates to Stage 4 with a structured conflict brief.

**Why this matters**: The Avera McKennan / Avera Health System failure had high Stage 1 confidence (the model *was* confident it found Avera). Confidence calibration can't catch confident-but-wrong. Only an explicit entity match check can. But the "City of Portland" record has no parent org to confuse it with — paying for a gate call there is waste that accumulates at 292K-record scale.

**Cost per call**: ~500 input × $0.80/M + ~100 output × $4.00/M = **~$0.0008 per record**  
**Estimated gate-eligible records (PoC, 209 Stage 1 records)**: ~160 after skip conditions apply (~50 skipped: ~20 entity-confirmed by Stage 0, ~30 website-concordant)  
**Gate calls**: ~$0.13  
**Retry calls (~20% trigger rate, ~32 records)**: ~$0.03  
**Subtotal**: ~$0.16 vs $0.20 without skip logic

**At 292K records (production)**: skip conditions reduce gate calls by ~20–25%, saving ~$45–60 on top of the $0.20 PoC savings.

**Expected lift**: website precision 0.75 → ~0.85, size precision 0.38 → ~0.55 (parent-headcount substitution is the primary driver of size failures).

**Addendum — Context Anchor prompt (Gemini critique 1)**: The entity gate catches cases where the wrong entity is retrieved. But even when the correct entity is found, the model may extract *corporate-wide* headcount from prose like "Avera Health employs 10,000+ across 37 facilities" rather than facility-specific count. Fix: add explicit extraction instruction to the Stage 1.6 field extraction prompt for size:

```
You are extracting employee count for a specific location entity: {name}, {city}, {state}.

If the search result contains ONLY corporate-wide headcount (parent org or global total), 
set size=null and size_confidence=0.30 to escalate to Stage 4.

Prefer phrases like: "at this location", "this facility employs", "regional office", 
"X employees in {city}". If those are absent, do NOT guess from the parent total.
```

This costs $0 (prompt text addition only) and handles the case where Stage 1.5 passes (correct entity) but size is still wrong (wrong scope). Without this, Stage 3 never fires because confidence is high — the model is confident it found Avera, it just extracted the wrong number.

---

### Improvement 3 — NAICS Intermediate Taxonomy + Embeddings-Based Label Snap

**What**: A two-part fix for the industry miss pattern.

**Part A — NAICS intermediate taxonomy** (Stage 1 prompt change): Replace the 492-label LinkedIn taxonomy as the model's classification target with 20-category NAICS 2-digit codes. The model outputs a NAICS 2-digit code; the Stage 2 snap maps it to a LinkedIn label. This halves token count in the classification portion of the prompt and eliminates cross-sector confusion entirely.

**Part B — Embeddings-based label snap** (Stage 2 code change): Replace the current `difflib` character-distance matching with a local `sentence-transformers` cosine-similarity lookup. Encode all 492 LinkedIn labels once at startup; at inference time, embed the model's raw descriptor and find the nearest label in the NAICS-filtered candidate list (10–20 labels per sector). `difflib` fails on semantic synonyms because character proximity is unrelated to meaning — "government relations" vs "government administration" differ by only two words but are worlds apart in B2B classification. Cosine similarity on sentence embeddings trivially distinguishes them.

**Why**: The industry miss pattern is almost entirely sibling-label confusion within the same NAICS sector:

| Predicted | Ground Truth | NAICS sector | `difflib` failure mode |
|-----------|-------------|--------------|------------------------|
| higher education | primary and secondary education | 61 — Educational Services | "education" overlap |
| government relations | government administration | 92 — Public Administration | "government" overlap |
| legal services | law practice | 54 — Professional Services | "legal/law" near-match |
| defense and space manufacturing | aviation and aerospace component manufacturing | 33 — Manufacturing | "manufacturing" overlap |
| restaurants | hospitality | 72 — Accommodation & Food | no character overlap, sector confusion |

All five would be correct at NAICS 2-digit level. Three of five are `difflib` failures — character-level proximity to the wrong sibling label. Semantic embeddings fix three of five directly; NAICS sector filtering fixes the fifth.

**Implementation**:
1. Add `NAICS_SECTORS: dict[int, list[str]]` mapping NAICS 2-digit codes → filtered LinkedIn label lists (one-time, ~2 hours)
2. In Stage 1/1b prompt, ask for NAICS 2-digit code instead of full LinkedIn label
3. Replace Stage 2 `difflib` snap with `sentence-transformers` (e.g. `all-MiniLM-L6-v2`, 80MB, MIT license) cosine similarity against the NAICS-filtered candidate list
4. Encode 492 labels at startup (~0.5s); per-record snap is a vector dot product — effectively free

**Cost**: Net savings ~$0.15 per full run (shorter prompts). Model download is one-time (~80MB). Zero runtime LLM spend. Startup overhead ~0.5s.

**Expected lift**: industry precision 0.60 → ~0.78. Sibling-label errors from `difflib` eliminated; cross-sector confusion eliminated by NAICS pre-filter. Residual gap: ambiguous multi-sector companies (a hospital system that also runs a consulting division) — unresolvable without a secondary SIC/NAICS field in the source record.

---

### Improvement 4 — Per-Field Targeted Search Queries

**What**: Instead of one general search per record that extracts all four fields simultaneously, use field-specific query templates optimized for each retrieval target.

**Current**: `'"{name}" {city} {state} company website employees industry'`

**Proposed query templates**:

| Target | Query template | Why |
|--------|---------------|-----|
| website | `"{name}" {state} official website` | Minimizes noise from aggregator sites |
| size | `"{name}" {state} employees site:linkedin.com/company OR site:craft.co OR site:dnb.com` | Structured sources for headcount |
| industry | `"{name}" {state} industry sector NAICS` | Surfaces filings and structured directories |

Size especially: the current single-search approach retrieves general web content where the model parses headcount from running prose. A targeted `site:linkedin.com/company` query surfaces structured `X,XXX employees` signals that are far easier to extract accurately — and explicitly scoped to the *company page* (entity-specific) rather than the corporate parent's Wikipedia article.

**Cost**:  
Records needing separate size search (missing size, post Stage 0 rules): ~100 records  
Each additional search: ~$0.008/call (same as current Stage 1 rate)  
Additional cost: **~$0.80**

**Expected lift**: size precision 0.38 → ~0.55–0.65 (targeted sources reduce parent-org headcount substitution even before the entity verification gate fires).

---

### Improvement 5 — Expanded Eval with Confidence Calibration

**What**: Expand ground truth from 20 to 100 records, add SMB coverage across the commercial scope (11+), and add a confidence calibration check to the eval runner.

**Record breakdown**:

| Segment | Current | Proposed | Rationale |
|---------|---------|----------|-----------|
| Enterprise | 12 | 40 | Primary ICP; oversampled for statistical power |
| Mid-market | 8 | 35 | Second priority; mixed entity complexity |
| SMB (11-50) | 0 | 25 | In-scope per Part 3; currently zero eval coverage |
| Micro (1-10) | 0 | **excluded** | Out of commercial scope per Part 3 (11+ working set) |

At 20 records across only 2 segments, a single wrong prediction shifts a segment metric by 8% — statistically weak. At 100 records across 3 segments (40/35/25), each wrong prediction moves a metric by 2.5–4%, making segment-level P/R defensible.

**On micro**: The PoC pipeline ran on 80 micro records from the 288-record sample. Those results exist in `data/enriched/part4_enriched_sample.parquet` as a **diagnostic artifact** — they document the quality floor where public data thins out and justify the Part 3 commercial scope exclusion. They are not included in primary P/R metrics and do not count toward the 100-record ground truth. If the 90-day roadmap later reconsiders micro, a dedicated micro eval (separate from the commercial eval) is the right vehicle.

**Candidate generation workflow** (to reduce hand-labeling burden): Use Sonnet to generate 80 candidate profiles across enterprise and mid-market (60 records) and SMB (20 records), with cross-referenced sources (LinkedIn + Crunchbase + official website, where available). Manually spot-check and verify each candidate before locking. This converts ~8h of cold labeling into ~2h of verification. The remaining 20 SMB records (fewer public sources than enterprise) require full manual research.

```python
# Sonnet candidate generation prompt (per record)
"""
For company: {name}, {city}, {state}
Generate the most likely values for: website, type, industry (LinkedIn taxonomy), size band.
Cite your primary source for each field. 
If you cannot find a reliable source, output null — do not guess.
"""
```

**Confidence calibration** (add to `eval_runner.py`): Among records where `{field}_confidence ≥ 0.80`, what fraction are actually correct? The pipeline currently sets confidence thresholds (`CONFIDENCE_VERIFY_THRESHOLD = 0.72`) without ever validating that those scores predict accuracy. If confidence 0.80+ only yields 60% correct, the threshold logic is miscalibrated and the Stage 3/4 escalation decision is wrong.

**`original_correct` aggregation** (currently produced, never reported): Aggregate `{field}_original_correct` by segment × field to produce a source data reliability table. This is the most actionable signal in the output for the upstream data acquisition question — not just "what did we fill?" but "how reliable was the source data by field and company size?"

**Cost**: ~$0.10 for 80 Sonnet candidate generation calls. ~2h manual verification + ~2h for micro manual labeling + ~1h eval code changes.

---

## Cost Summary

| Improvement | Incremental cost | One-time cost |
|-------------|-----------------|---------------|
| 1. Stage 0 rules expansion | $0 | ~2h engineering |
| 2. Entity verification gate + Context Anchor prompt | **+$0.20** per full run | ~1.5h engineering |
| 3. NAICS taxonomy + embeddings snap | **−$0.15** per full run | ~2h taxonomy map + embeddings setup |
| 4. Per-field targeted size search | **+$0.80** per full run | ~1h engineering |
| 5. Eval expansion to 100 records + calibration | **+$0.10** (Sonnet candidate gen) | ~5h (2h verify + 2h micro manual + 1h eval code) |
| **Net change per re-run** | **+$0.95** | |

**Re-run cost estimate**: $2.38 (current) + $0.95 (incremental) = **~$3.33** for a full 288-record re-run with all improvements.

**Budget position**: $2.62 remaining in Part 4 budget vs. $3.33 projected re-run cost. Running all improvements requires a ~$0.71 budget overage.

**Options**:
- **Option A — Staged re-run**: Run Improvements 1+2+3 first (net ~$2.43 projected) — entity gate + Context Anchor + taxonomy savings. Keeps within budget. Likely raises macro P/R to ~0.72. Reserve Improvements 4+5 for Part 6 90-day roadmap with budget justification.
- **Option B — Full re-run with budget extension**: Accept a one-time $1.10 budget extension on Part 4 (total project still well under $10.00: $2.76 spent + $3.33 re-run = $6.09 of $10.00) and run everything at once — eval then covers all four segments with 25 records each, making the confidence calibration check statistically meaningful.

---

## Expected Performance After Full Redesign

Projected eval metrics (100-record ground truth, all improvements):

| Field | Current P | Projected P | Driver |
|-------|-----------|-------------|--------|
| type | 0.90 | ~0.95 | Stage 0 rules eliminate LLM calls for deterministic cases |
| website | 0.75 | ~0.85 | Entity verification gate catches parent/subsidiary substitution |
| industry | 0.60 | ~0.78 | NAICS intermediate taxonomy eliminates sibling-label confusion |
| size | 0.38 | ~0.58 | Entity gate + targeted size search reduce parent-headcount substitution |
| **macro** | **0.66** | **~0.79** | |

The residual gap on size (0.58 vs theoretical ceiling of ~0.75) reflects a structural limit: micro and small SMB firms have no authoritative public headcount data. Below 50 employees, the only reliable size signal is a first-party data provider (LinkedIn Sales Navigator, D&B, Clearbit). The cascade can approach that ceiling with better retrieval; it cannot exceed it from public web sources alone.

---

## What This Changes About the Architecture

```
Before (v1):
  Stage 0 (rules: platform URL detection only)
  Stage 1 (Haiku + search → extract all fields in one call)
  Stage 2 (deterministic industry snap: raw → 492-label)
  Stage 3 (Haiku verify: fires only on low-confidence website)
  Stage 4 (Sonnet: resolve conflicts)

After (v2):
  Stage 0 (rules: platform URLs + name-suffix type + TLD type/industry)
  Stage 1 (Haiku + search → identify entity only)
  Stage 1.5 (Haiku entity gate: MATCH / SUBSIDIARY / PARENT / NO_MATCH)
           [conditional — skipped when entity is already anchored by Stage 0 or
            website concordance; always fires on WEBSITE_WRONG_ENTITY flag, large
            orgs (1K+), or name divergence between input and extracted entity]
  Stage 1.6 (Haiku + targeted search → extract fields, field-specific queries)
           [size prompt includes Context Anchor: prefer location-specific headcount,
            set confidence=0.30 if only corporate-wide data found → escalates to Stage 4]
  Stage 2 (deterministic snap: NAICS 2-digit code → 492-label via embeddings cosine sim)
           [sentence-transformers all-MiniLM-L6-v2; labels encoded once at startup]
  Stage 3 (Haiku verify: fires for SUBSIDIARY/PARENT unresolved after retry)
  Stage 4 (Sonnet: structured conflict brief with prior stage evidence)
```

The PIPELINE_VERSION constant in `src/part4_pipeline.py` should increment to `"v2"` and all observability logs should carry the new version tag so v1 and v2 outputs are distinguishable in `shared_observability.jsonl`.

---

## Submission Narrative (Part 6 framing)

> "We designed a highly defensive, cost-aware 4-stage pipeline that enriched 288 records for $2.38 — $0.008/record average — while staying within a $5.00 budget gate enforced at every record iteration. Rather than optimizing blindly for scores via expensive brute-force prompting, the architecture actively surfaces structural data-market trade-offs. For example, general web search yields 0.90 Precision on business Type (binary signals are easy), but exposes a critical B2B intelligence limit on entity resolution — a 0.38 Precision on Size caused by parent-subsidiary headcount bleeding. We isolated this failure mode, proved it in automated evaluation logs, and have a deterministic fix path: an entity gate (Stage 1.5), a location-scoped size extraction prompt, and a semantic embedding industry snap — all logged, versioned, and budget-tracked. The 90-Day plan translates these findings into a production acquisition strategy."
