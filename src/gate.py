"""
Quality gates for phase boundary enforcement.
Raises GateFailure on hard stops; GateResult carries pass/fail detail per check.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pandas as pd

from src.observability import ObservabilityLogger

PHASE_BUDGETS = {
    "phase_2": 3.00,
    "phase_4": 5.00,
}
TOTAL_BUDGET = 10.00

PLATFORM_BLOCKLIST = {
    "yelp.com", "facebook.com", "instagram.com", "linkedin.com", "twitter.com",
    "linktr.ee", "bit.ly", "hub.biz", "wixsite.com", "weebly.com",
    "wordpress.com", "squarespace.com", "google.com", "amazon.com", "youtube.com",
}

RUN1_SIZE_BANDS = {"51-200", "201-500", "501-1K", "1K-5K", "5K-10K", "10K+"}

STAGE4_COST_SIGNAL_THRESHOLD = 0.40


class GateFailure(Exception):
    """Hard stop — phase must not proceed."""


@dataclass
class GateResult:
    passed: bool
    gate: str
    detail: str
    warnings: List[str] = field(default_factory=list)


def _file_gate(path: str, label: str) -> GateResult:
    if Path(path).exists():
        return GateResult(True, "file_exists", f"{label} found")
    return GateResult(False, "file_exists", f"{label} not found at {path}")


def _budget_gate(phase: str, logger: ObservabilityLogger) -> GateResult:
    spent = logger.get_phase_cost(phase)
    cap = PHASE_BUDGETS[phase]
    if spent >= cap:
        return GateResult(False, "budget_headroom", f"{phase} budget exhausted: ${spent:.4f} of ${cap:.2f} spent")
    return GateResult(True, "budget_headroom", f"{phase} budget OK: ${spent:.4f} spent, ${cap - spent:.4f} remaining")


def _total_budget_gate(logger: ObservabilityLogger) -> GateResult:
    total = logger.total_cost
    if total >= TOTAL_BUDGET:
        return GateResult(False, "total_budget", f"Total budget exhausted: ${total:.4f} of ${TOTAL_BUDGET:.2f}")
    return GateResult(True, "total_budget", f"Total budget OK: ${total:.4f} of ${TOTAL_BUDGET:.2f} spent")


def check_phase2_entry() -> List[GateResult]:
    """Pre-conditions before running Phase 2 gap detection."""
    logger = ObservabilityLogger()
    return [
        _file_gate("data/processed/us_companies.parquet", "us_companies.parquet"),
        _file_gate("data/processed/sample_audit.parquet", "sample_audit.parquet"),
        _budget_gate("phase_2", logger),
        _total_budget_gate(logger),
    ]


def check_phase4_entry(
    gap_candidates_path: str = "data/processed/gap_candidates.json",
) -> List[GateResult]:
    """Pre-conditions before running Phase 4 enrichment."""
    results: List[GateResult] = []
    logger = ObservabilityLogger()

    candidates_gate = _file_gate(gap_candidates_path, "gap_candidates.json")
    results.append(candidates_gate)

    if candidates_gate.passed:
        with open(gap_candidates_path) as f:
            candidates = json.load(f)
        n = len(candidates)
        if n < 3:
            results.append(GateResult(
                False, "min_gap_candidates",
                f"Only {n} gap candidate(s) — need ≥3 before Phase 4",
            ))
        else:
            results.append(GateResult(True, "min_gap_candidates", f"{n} gap candidates present"))

    # Verifier must have run before Phase 4 starts
    findings_gate = _file_gate("notes/gap_findings.md", "gap_findings.md (verifier sign-off)")
    if not findings_gate.passed:
        findings_gate = GateResult(
            False, "verifier_signoff",
            "notes/gap_findings.md missing — run verifier on Phase 2 output before Phase 4",
        )
    results.append(findings_gate)

    results.append(_budget_gate("phase_4", logger))
    results.append(_total_budget_gate(logger))
    return results


def check_batch_quality(batch_path: str) -> List[GateResult]:
    """Validate the enrichment batch before the cascade loop starts."""
    results: List[GateResult] = []

    file_gate = _file_gate(batch_path, "enrichment batch")
    results.append(file_gate)
    if not file_gate.passed:
        return results

    df = pd.read_parquet(batch_path)
    n = len(df)

    if n < 200:
        results.append(GateResult(False, "batch_size", f"Batch too small: {n} records (min 200)"))
    elif n > 1000:
        results.append(GateResult(False, "batch_size", f"Batch too large: {n} records (max 1000)"))
    else:
        results.append(GateResult(True, "batch_size", f"Batch size OK: {n} records"))

    if "size" in df.columns:
        out_of_scope = df[~df["size"].isin(RUN1_SIZE_BANDS)]
        if len(out_of_scope):
            results.append(GateResult(
                False, "run1_size_scope",
                f"{len(out_of_scope)} records outside Run 1 scope (size <51 employees)",
            ))
        else:
            results.append(GateResult(True, "run1_size_scope", "All records in 51+ size bands"))

    if "website" in df.columns:
        def _is_platform(url) -> bool:
            if not isinstance(url, str):
                return False
            stripped = url.lower().lstrip("https://").lstrip("http://").lstrip("www.")
            return any(stripped.startswith(d) for d in PLATFORM_BLOCKLIST)

        hits = df["website"].apply(_is_platform).sum()
        if hits:
            results.append(GateResult(
                False, "rules_applied",
                f"{hits} records still carry platform URLs — apply rules.py before Phase 4",
            ))
        else:
            results.append(GateResult(True, "rules_applied", "No platform URLs in batch"))

    if "handle" in df.columns:
        nulls = int(df["handle"].isna().sum())
        dupes = int(df["handle"].duplicated().sum())
        if nulls or dupes:
            results.append(GateResult(
                False, "primary_key",
                f"handle integrity failure: {nulls} nulls, {dupes} duplicates",
            ))
        else:
            results.append(GateResult(True, "primary_key", "handle unique and non-null"))

    return results


def check_cascade_health(enriched_path: str) -> List[GateResult]:
    """Post-cascade health check — call after the enrichment loop completes."""
    results: List[GateResult] = []

    file_gate = _file_gate(enriched_path, "enriched output")
    results.append(file_gate)
    if not file_gate.passed:
        return results

    df = (
        pd.read_parquet(enriched_path)
        if enriched_path.endswith(".parquet")
        else pd.read_json(enriched_path, lines=True)
    )

    if "stage_resolved" in df.columns:
        resolved = df[df["stage_resolved"].notna()]
        if len(resolved):
            stage4_share = (resolved["stage_resolved"] == 4).sum() / len(resolved)
            if stage4_share > STAGE4_COST_SIGNAL_THRESHOLD:
                results.append(GateResult(
                    False, "stage_distribution",
                    f"Stage 4 (Sonnet) resolved {stage4_share:.1%} — exceeds 40% cost threshold",
                    warnings=["Lower Stage 3 confidence threshold or improve search quality to reduce Sonnet escalations"],
                ))
            else:
                results.append(GateResult(True, "stage_distribution", f"Stage 4 share {stage4_share:.1%} — within threshold"))

    if "status" in df.columns:
        missing = int(df["status"].isna().sum())
        if missing:
            results.append(GateResult(False, "no_silent_drops", f"{missing} records have no status"))
        else:
            results.append(GateResult(True, "no_silent_drops", "All records have a status"))

    logger = ObservabilityLogger()
    spent = logger.get_phase_cost("phase_4")
    cap = PHASE_BUDGETS["phase_4"]
    if spent > cap:
        results.append(GateResult(False, "budget_compliance", f"Phase 4 over-budget: ${spent:.4f} vs ${cap:.2f} cap"))
    else:
        results.append(GateResult(True, "budget_compliance", f"Phase 4 within budget: ${spent:.4f} of ${cap:.2f}"))

    return results


def enforce(results: List[GateResult], label: str) -> None:
    """Print all gate results, raise GateFailure if any failed."""
    failures = [r for r in results if not r.passed]

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.gate}: {r.detail}")
        for w in r.warnings:
            print(f"         warning: {w}")

    if failures:
        raise GateFailure(
            f"{label}: {len(failures)} gate(s) failed — resolve before proceeding."
        )
    print(f"  → All {len(results)} gate(s) passed.\n")
