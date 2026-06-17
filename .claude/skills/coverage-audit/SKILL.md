# Skill: coverage-audit
_Version: 2.0 | Updated: 2026-06-13_

A market coverage audit workflow that runs in two stages: internal data quality profiling, then external gap detection against a government benchmark. Designed to be run on any new market by editing `config/project.yaml` — no code changes required.

> **Parameters are loaded from `config/project.yaml`** (gap tier thresholds, geography tier thresholds, platform blocklist, market dataset/comparator paths, run scope, size-stratified coverage targets). The numbers in this document mirror that file as of the version above; if they diverge, `config/project.yaml` wins.

---

## When to trigger

- **New market onboarding** — establish a coverage baseline before any enrichment work begins
- **Quarterly coverage refresh** — re-run to measure movement after an enrichment cycle
- **Pre-sales gap inquiry** — "do we cover X sector in Y region?" requests from Sales or CS
- **Post-enrichment validation** — confirm a Phase 4 enrichment run improved fill rates in targeted segments

---

## Inputs

### Stage 1 — Internal Profiling (no external dependencies)

| Input | Type | Description |
|---|---|---|
| `dataset_path` | file path | Parquet file containing company records |
| `geography_col` | string | Column name for sub-region dimension (`state` for US, `country` for APAC) |
| `size_col` | string | Column name for company size band (`size`) |
| `industry_col` | string | Column name for industry label (`industry`) |
| `platform_blocklist` | list | Domains to treat as missing websites (loaded from `config/project.yaml` → `enrichment_rules.platform_blocklist`) |

**Platform blocklist source of truth**: `config/project.yaml` → `enrichment_rules.platform_blocklist`. Treat any website matching one of those domains as NULL for fill-rate purposes. Institutional TLDs (`.edu`, `.mil`, `.gov`) are also excluded at the rules layer.

### Stage 2 — External Gap Detection (requires a comparator source)

All Stage 1 inputs, plus:

| Input | Type | Description |
|---|---|---|
| `comparator_path` | file path | Benchmark file (SUSB CSV for US, ABS for AU, BizFile for SG, etc.) |
| `comparator_format` | string | `susb_csv`, `nes_txt`, or `custom` |
| `comparator_join_key` | string | Column in comparator that maps to `geography_col` |
| `employer_only` | bool | Whether the comparator counts only employer firms (true for SUSB, false for NES). Affects HIGH_GAP thresholds for gig/sole-operator sectors. |

**Note**: Stage 2 can be skipped when no comparator exists for a new market. Stage 1 still produces actionable fill-rate findings and null pattern classifications independently.

---

## Outputs

### Stage 1 outputs

| Artifact | Path | Description |
|---|---|---|
| Baseline observations | `notes/part1_baseline_observations.md` | Human-readable audit with fill-rate tables, tier distribution, null pattern classification, quality flags |
| Profiling summary | `data/processed/part1_profiling_summary.json` | Machine-readable counts for each finding — used by `src/rules.py` |
| Stratified audit sample | `data/processed/part1_sample_audit.parquet` | Stratified sample for Phase 2 and Phase 4 (see Sampling Strategy below) |

### Stage 2 outputs

| Artifact | Path | Description |
|---|---|---|
| Gap candidates | `data/processed/part2_gap_candidates.json` | **Unranked** candidate list. Schema per record: `{gap_id, dimension, slice, our_records, comparator_records, comparator_source, coverage_pct, tier, confidence, status: "unverified", caveats[]}`. See `.claude/agents/data-engineer.md` for field definitions. Ranking happens downstream in the verifier. |
| Gap findings (verified) | `notes/gap_findings.md` | Final ranked list after verifier spot-check — do not write directly, this is the verifier's output |

---

## Executor agents

| Stage | Agent | Role |
|---|---|---|
| Stage 1 | `data-profiler` | Runs all internal quality checks — field-type-aware distribution, cross-field consistency, null pattern analysis |
| Stage 2 | `data-engineer` | Runs comparator join, computes coverage ratios, surfaces gap candidates |
| Verification | `verifier` | Spot-checks 15 records per gap candidate against raw data — independent of data-engineer conclusions |

**Invocation pattern** (Claude Code):
```
Use the data-profiler subagent for Stage 1 coverage audit on data/processed/part0_companies.parquet
Use the data-engineer subagent for Stage 2 gap detection against data/raw/us_state_6digitnaics_2022.csv
Use the verifier subagent to spot-check the gap candidates in data/processed/part2_gap_candidates.json
```

---

## Interpretation guide

### Geography tiering

Geographies are tiered by record depth before any gap analysis. Only Tier A and Tier B are included in ranked gap lists. Thresholds: `config/project.yaml` → `geography_tiering.{tier_a_min, tier_b_min}`.

| Tier | Threshold (current US config) | Treatment |
|---|---|---|
| Tier A | ≥ `tier_a_min` (50,000) | Full confidence — include in all ranked gap lists |
| Tier B | `tier_b_min` ≤ n < `tier_a_min` (10,000–49,999) | Directional — flag in outputs, include with caveat |
| Tier C | < `tier_b_min` (10,000) | Exclude from ranked lists — flag only |

Excluded subregions and territories are listed under `markets.<id>.excluded_subregions` and `excluded_territories` in `config/project.yaml`.

### Gap tiers (coverage ratio = our records / benchmark firm count)

Thresholds: `config/project.yaml` → `gap_tiers.{high_gap_max, moderate_gap_max}`.

| Tier | Coverage Ratio (current config) | Meaning |
|---|---|---|
| HIGH_GAP | < `high_gap_max` (10%) | Structural under-representation — sourcing gap, not enrichable |
| MODERATE_GAP | `high_gap_max` ≤ r < `moderate_gap_max` (10%–30%) | Partial coverage — enrichment can improve |
| ADEQUATE | ≥ `moderate_gap_max` (30%) | Represented — focus on fill rate quality, not breadth |

**Employer-only benchmark caveat**: When the comparator counts employer firms only (e.g., SUSB), sectors dominated by sole proprietors and gig workers (Transportation, Other Services, Real Estate, Construction) will appear as HIGH_GAP even when coverage is real. Always pair an employer-only comparator with a non-employer source (NES for US) before finalising gap rankings for these sectors.

### Enterprise weighting for enrichment prioritisation

Not all gaps are equal commercially. When ranking enrichment targets:
- Enterprise (500+ employees): weight **3×**
- Mid-market (51–500): weight **2×**
- SMB (11–50): weight **1×**
- Micro (<11): weight **0.5×** — high churn risk, lower ROI

### Coverage parity targets (by size band)

A geography reaches coverage parity when all four size bands meet their respective completeness (fill rate) and correctness (precision) thresholds. These are loaded from `config/project.yaml` under `coverage_parity_targets`:

| Size Band | Website Fill Target | Industry Fill Target | Size Fill Target | Website Precision | Industry Precision | Size Precision | Platform URL Policy |
|---|---|---|---|---|---|---|---|
| Enterprise (500+) | ≥ 99% | ≥ 99% | ≥ 99% | ≥ 99% | ≥ 95% | ≥ 98% | Strict Zero-Tolerance (nullify) |
| Mid-market (51–500) | ≥ 92% | ≥ 97% | ≥ 98% | ≥ 95% | ≥ 90% | ≥ 95% | Strict Exclusion (nullify) |
| SMB (11–50) | ≥ 85% | ≥ 93% | ≥ 96% | ≥ 90% | ≥ 85% | ≥ 95% | Clean Domain Priority (nullify & flag) |
| Micro (1–10) | ≥ 75% | ≥ 85% | ≥ 93% | ≥ 90% | ≥ 85% | ≥ 93% | Platform-Only Recognition (nullify & flag) |

### Null pattern classification

| Pattern | Enrichment implication |
|---|---|
| MCAR (uniform null rate across all dimensions) | Apply enrichment uniformly |
| MAR (null rate correlates with geography or size) | Stratify enrichment — prioritise worst-coverage geographies |
| MNAR (missing values are structurally absent) | Enrichment is harder — no anchor field to infer from |

---

## Sampling strategy

At 4M+ records, a full LLM pass is not feasible within typical budgets. The audit sample is stratified by geography tier and industry sector:

| Geography Tier | Records per geography | Total |
|---|---|---|
| Tier A | ~100 | ~2,300 |
| Tier B | ~50 | ~1,250 |
| **Total** | — | **~3,550** |

Within each geography, stratify by industry sector (proportional) and over-sample enterprise records (minimum 50 per Tier A, 20 per Tier B) to prevent enterprise gaps from being diluted by micro-business volume.

---

## Known limitations

1. **Employer-only benchmark blind spot**: SUSB and most national business registries count employer firms. The gig/non-employer economy (30M+ entities in the US alone) is invisible until you add a non-employer comparator (NES, ABR non-employer extract, etc.). Without it, Transportation, Other Services, and Real Estate will always appear as coverage failures.

2. **Coverage ratios are directional**: The denominator (benchmark firm count) counts legal firms; our data counts records which may include duplicates. Ratios above 100% indicate either dataset bias or non-employer entities being captured — investigate before labelling as "over-indexed."

3. **Vintage mismatch**: A 1–2 year gap between dataset vintage and benchmark vintage is acceptable. Gaps >3 years introduce noise — a sector that was ADEQUATE in 2020 may be HIGH_GAP in 2024 due to business churn, not enrichment failure.

4. **NES gig-economy sectors are sourcing gaps, not enrichment opportunities**: Transportation (Uber/Lyft drivers), Other Services (solo repair workers), and Admin/Support (cleaning services) are structurally HIGH_GAP because the source platform (LinkedIn) doesn't capture gig workers as company entities. Enriching existing records cannot close these gaps — additional sources (trade registers, contractor licenses, gig platform data) are required.

5. **Industry label quality degrades Stage 2 accuracy**: If the dataset has ~341K null industry records and ~329K records split across semantic duplicate label pairs, the coverage ratios per industry sector are understated. Run Stage 1 industry canonicalisation (LLM merge of semantic duplicate pairs) before Stage 2 for more accurate sector-level gap detection.

---

## Worked example — US market (2026-06-12)

### Invocation

```
Use the data-profiler subagent for Stage 1 coverage audit.
Dataset: data/processed/part0_companies.parquet
Geography column: state
Size column: size
Industry column: industry
Apply default platform blocklist.
Append findings to notes/part1_baseline_observations.md
```

```
Use the data-engineer subagent for Stage 2 gap detection.
SUSB comparator: data/raw/us_state_6digitnaics_2022.csv (employer firms, susb_csv format)
NES comparator: data/raw/nonemp23st.txt (non-employer, nes_txt format)
Run both comparators and report combined gap tier per sector.
Output to data/processed/part2_gap_candidates.json
```

### Stage 1 key findings

| Field | True fill rate (after blocklist) | Null pattern | Priority |
|---|---|---|---|
| `website` | 76.7% (910K missing + 62K platform URLs reclassified) | MAR by state and size | Critical |
| `industry` | 91.8% | MAR/MNAR | High |
| `size` | 95.5% | MAR (weak) | Medium |

Geography tier distribution: 23 Tier A states (84.2% of records), 25 Tier B (15.2%), 7 Tier C / territories excluded.

Worst-coverage geographies: Iowa (81.9% avg fill), Kansas (83.5%), West Virginia (83.8%).

### Stage 2 key findings (SUSB + NES combined) — post-verifier ranked output

Engineer outputs `part2_gap_candidates.json` unranked. The table below is the verifier's ranked top-N after spot-check, written to `notes/gap_findings.md`.

| Sector | Combined coverage | Gap tier | Enrichable? |
|---|---|---|---|
| Transportation & Warehousing | 2.0% | HIGH_GAP | No — gig-worker sourcing gap |
| Other Services | 2.3% | HIGH_GAP | No — solo-operator sourcing gap |
| Admin & Support | 3.6% | HIGH_GAP | No — sourcing gap |
| Real Estate | 4.5% | HIGH_GAP | No — individual agent sourcing gap |
| Construction | 6.0% | HIGH_GAP | Partial — solo contractors, but mid-market enrichable |
| Retail Trade | 6.3% | HIGH_GAP | Yes — missing records, enrichable via web |
| Wholesale Trade | 18.6% | MODERATE_GAP | Yes — enrichable |
| Accommodation & Food | 27.9% | MODERATE_GAP | Yes — enrichable |

**Interpretation**: The HIGH_GAP sectors split into two categories: sourcing gaps (gig/solo-operator sectors that cannot be closed by enriching existing records) and enrichable gaps (Retail, Wholesale, Accommodation where records exist but are incomplete). Phase 4 enrichment should target the latter. Sourcing gaps require new data acquisition.

### Cost

- Stage 1 (data-profiler): $0 — deterministic, no LLM calls
- Stage 2 industry NAICS mapping (one-time, Haiku batch): $0.012
- Stage 2 comparator join: $0 — deterministic SQL
- Verifier spot-check: $0 — deterministic
- **Total: $0.012**

## Maintenance policy

**Promotion gate**: only update this skill or an agent spec when a finding would change how you\\'d run the audit
on a *different dataset or market*. If it only applies to the current dataset, it belongs in \`CLAUDE.md\`. If it
would only belong in a single worked example, add it there instead.

**Anti-bloat check**: once something passes the promotion gate, express it in the minimum form — one table row or one sentence. If you're writing a paragraph or adding an inline example, the example belongs in the Worked example section instead. Prefer a new table row over prose.

**Approval required**: never edit this file or any \`.claude/agents/*.md\` without first showing the user: (1) what triggered the update, (2) the exact proposed diff, (3) why it passes the promotion gate. Wait for explicit sign-off before writing changes.

**Version bump convention**: minor bump (e.g. 1.0 → 1.1) for new worked examples or clarifications; major bump (e.g. 1.x → 2.0) for threshold changes or new market support. Update the version header on every approved change.