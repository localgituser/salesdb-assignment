"""
Phase 2 — Agentic Coverage & Quality Audit (data-engineer role)

Reads gap_candidates.json, aggregates to sector level, calls:
  1. Haiku  — sector ranking + root cause (one batched call, all 19 sectors)
  2. Sonnet — top-5 narrative synthesis (one call, top sectors only)

Writes:
  data/processed/phase2_audit_raw.json   — raw LLM outputs + sector summary
  data/processed/observability.jsonl     — per-call trace entries
  data/processed/cost_tracking.json      — running total update

Does NOT write gap_findings.md — that is the verifier's job after spot-checking.
"""

import json
import sys
import time
import logging
from collections import defaultdict
from pathlib import Path
from string import Template

import anthropic

sys.path.insert(0, str(Path(__file__).parent))
from config import CONFIG
from observability import ObservabilityLogger

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PHASE = "phase_2"
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_COST_PER_M_IN = 0.80
HAIKU_COST_PER_M_OUT = 4.00
SONNET_COST_PER_M_IN = 3.00
SONNET_COST_PER_M_OUT = 15.00

PHASE2_BUDGET = CONFIG.budget.per_phase_usd.get("phase_2", 3.0)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"
GAP_CANDIDATES_PATH = PROCESSED_DIR / "gap_candidates.json"
AUDIT_RAW_PATH = PROCESSED_DIR / "phase2_audit_raw.json"


def load_gap_candidates() -> dict:
    with open(GAP_CANDIDATES_PATH) as f:
        return json.load(f)


def build_sector_summary(all_cells: list[dict]) -> list[dict]:
    """Aggregate cell-level gap data to sector level for the Haiku prompt."""
    sectors: dict = defaultdict(lambda: {
        "HIGH_GAP": 0, "MODERATE_GAP": 0, "ADEQUATE": 0,
        "ratios": [], "naics_code": "",
        "total_our_records": 0, "total_comparator": 0,
        "total_susb": 0, "total_nes": 0,
    })

    for cell in all_cells:
        s = cell["naics_desc"]
        t = cell.get("tier", "ADEQUATE")
        sectors[s][t] = sectors[s].get(t, 0) + 1
        sectors[s]["ratios"].append(cell["coverage_ratio"])
        sectors[s]["naics_code"] = cell["naics_code"]
        sectors[s]["total_our_records"] += cell["our_records"]
        sectors[s]["total_comparator"] += cell["comparator_records"]
        sectors[s]["total_susb"] += cell.get("susb_firms", 0)
        sectors[s]["total_nes"] += cell.get("nes_nonemployers", 0)

    summary = []
    for naics_desc, st in sectors.items():
        ratios = sorted(st["ratios"])
        median_ratio = ratios[len(ratios) // 2]
        overall_ratio = (
            st["total_our_records"] / st["total_comparator"]
            if st["total_comparator"] > 0 else 0.0
        )
        nes_share = (
            st["total_nes"] / st["total_comparator"]
            if st["total_comparator"] > 0 else 0.0
        )
        summary.append({
            "naics_code": st["naics_code"],
            "naics_desc": naics_desc,
            "states_analyzed": len(st["ratios"]),
            "high_gap_states": st.get("HIGH_GAP", 0),
            "moderate_gap_states": st.get("MODERATE_GAP", 0),
            "adequate_states": st.get("ADEQUATE", 0),
            "median_coverage_pct": round(median_ratio * 100, 2),
            "overall_coverage_pct": round(overall_ratio * 100, 2),
            "nes_share_of_comparator_pct": round(nes_share * 100, 1),
            "our_records": st["total_our_records"],
            "comparator_total": st["total_comparator"],
        })

    return sorted(summary, key=lambda x: x["overall_coverage_pct"])


def compute_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    if "haiku" in model:
        return (input_tokens * HAIKU_COST_PER_M_IN + output_tokens * HAIKU_COST_PER_M_OUT) / 1_000_000
    return (input_tokens * SONNET_COST_PER_M_IN + output_tokens * SONNET_COST_PER_M_OUT) / 1_000_000


def render_prompt(template_path: Path, **kwargs) -> str:
    text = template_path.read_text()
    for key, value in kwargs.items():
        placeholder = "{{" + key.upper() + "}}"
        text = text.replace(placeholder, value)
    return text


def call_llm(
    client: anthropic.Anthropic,
    obs: ObservabilityLogger,
    model: str,
    prompt: str,
    prompt_version: str,
    metadata: dict,
) -> tuple[str, dict]:
    """Call LLM, log to observability, return (text_response, usage_dict)."""
    budget_used = obs.get_phase_cost(PHASE)
    if budget_used >= PHASE2_BUDGET:
        logger.error(f"Phase 2 budget exhausted (${budget_used:.4f} >= ${PHASE2_BUDGET}). Aborting.")
        sys.exit(1)

    t0 = time.time()
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = int((time.time() - t0) * 1000)

    text = response.content[0].text
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    cost = compute_cost(usage["input_tokens"], usage["output_tokens"], model)

    try:
        json.loads(text)
        outcome = "success"
    except json.JSONDecodeError:
        outcome = "invalid_json"
        logger.warning(f"LLM returned non-JSON for {prompt_version}")

    obs.log_call(
        phase=PHASE,
        model=model,
        tokens=usage["input_tokens"] + usage["output_tokens"],
        cost=cost,
        prompt_version=prompt_version,
        outcome=outcome,
        metadata={**metadata, "latency_ms": latency_ms, **usage},
    )
    logger.info(f"{model} {prompt_version}: {usage['input_tokens']}in/{usage['output_tokens']}out "
                f"${cost:.4f} {latency_ms}ms → {outcome}")
    return text, usage


def build_top5_sector_detail(gap_candidates: list[dict], top5_codes: list[str]) -> list[dict]:
    """Collect all gap candidates for the top 5 NAICS codes for Sonnet synthesis."""
    code_set = set(top5_codes)
    by_code: dict = defaultdict(list)
    for c in gap_candidates:
        if c["naics_code"] in code_set:
            by_code[c["naics_code"]].append({
                "state": c["state"],
                "state_tier": c["state_tier"],
                "our_records": c["our_records"],
                "coverage_pct": c["coverage_pct"],
                "tier": c["tier"],
                "caveats": c.get("caveats", []),
            })
    result = []
    for code in top5_codes:
        cells = by_code.get(code, [])
        result.append({
            "naics_code": code,
            "cell_count": len(cells),
            "cells": cells,
        })
    return result


def main():
    logger.info("Phase 2 audit starting")
    obs = ObservabilityLogger()
    client = anthropic.Anthropic()

    data = load_gap_candidates()
    all_cells = data.get("all_cells", [])
    gap_candidates = data.get("gap_candidates", [])

    if not all_cells:
        logger.error("all_cells missing from gap_candidates.json — cannot build sector summary")
        sys.exit(1)

    sector_summary = build_sector_summary(all_cells)
    logger.info(f"Built sector summary: {len(sector_summary)} sectors")

    # --- Call 1: Haiku sector ranking ---
    haiku_prompt = render_prompt(
        PROMPTS_DIR / "audit_v1.txt",
        sector_summary_json=json.dumps(sector_summary, indent=2),
    )
    haiku_raw, haiku_usage = call_llm(
        client, obs, HAIKU_MODEL, haiku_prompt,
        prompt_version="audit_v1",
        metadata={"sector_count": len(sector_summary)},
    )

    try:
        haiku_output = json.loads(haiku_raw)
    except json.JSONDecodeError:
        logger.error("Haiku returned invalid JSON. Aborting.")
        sys.exit(1)

    top5_codes = haiku_output.get("top_5_for_synthesis", [])
    logger.info(f"Haiku top 5 for synthesis: {top5_codes}")

    # --- Call 2: Sonnet top-5 synthesis ---
    top5_detail = build_top5_sector_detail(gap_candidates, top5_codes)
    sonnet_prompt = render_prompt(
        PROMPTS_DIR / "audit_synthesis_v1.txt",
        haiku_rankings_json=json.dumps(haiku_output, indent=2),
        top5_sector_detail_json=json.dumps(top5_detail, indent=2),
    )
    sonnet_raw, sonnet_usage = call_llm(
        client, obs, SONNET_MODEL, sonnet_prompt,
        prompt_version="audit_synthesis_v1",
        metadata={"top5_codes": top5_codes},
    )

    try:
        sonnet_output = json.loads(sonnet_raw)
    except json.JSONDecodeError:
        logger.error("Sonnet returned invalid JSON. Aborting.")
        sys.exit(1)

    # --- Write raw output ---
    raw_output = {
        "phase": PHASE,
        "sector_summary": sector_summary,
        "haiku_ranking": haiku_output,
        "sonnet_synthesis": sonnet_output,
        "total_phase2_cost": obs.get_phase_cost(PHASE),
    }
    AUDIT_RAW_PATH.write_text(json.dumps(raw_output, indent=2))
    logger.info(f"Wrote {AUDIT_RAW_PATH}")
    logger.info(f"Phase 2 total cost: ${obs.get_phase_cost(PHASE):.4f}")
    logger.info("Phase 2 audit complete. Run phase2_verify.py next (verifier role).")


if __name__ == "__main__":
    main()
