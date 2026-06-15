# Part 5 — Reusable Skill

The coverage-audit skill is defined at:

```
.claude/skills/coverage-audit/SKILL.md
```

Also accessible via the root symlink:

```
skills/coverage-audit/SKILL.md
```

---

## What the skill does

A two-stage market coverage audit workflow:

1. **Internal profiling** — field-type-aware quality checks, null pattern analysis, cardinality validation (runs deterministically, no LLM)
2. **External gap detection** — compares internal record counts against a government benchmark (SUSB + NES) to surface sourcing gaps by industry and sub-region

Designed to run on any market by editing `config/project.yaml` — no code changes required.

---

## Key design properties

- **Market-parameterised**: swap `markets.us` for `markets.au` in the YAML and the skill runs against ANZ data with the same pipeline
- **Rules-first**: deterministic profiling runs before any LLM call; LLM is only invoked for NAICS label mapping and gap synthesis
- **Traced**: every LLM call logged to `data/processed/shared_observability.jsonl` with prompt_version, model, cost, latency, outcome
- **Verifier-separated**: data-engineer produces gap candidates; verifier spot-checks independently (n=15 per gap, pure SQL)

---

## Example invocation

```
Use the coverage-audit skill on the current market dataset.
Inputs: data/processed/part0_companies_clean.parquet, config/project.yaml (markets.us)
Run internal profiling first, then external gap detection vs. SUSB+NES.
Output part2_gap_candidates.json and gap_findings.md.
```

See the full skill spec (trigger conditions, inputs, outputs, limitations, worked example) at `.claude/skills/coverage-audit/SKILL.md`.
