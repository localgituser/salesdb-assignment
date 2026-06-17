"""
Test closure detection for three scenarios using the pipeline's actual stage functions.
All tests use stage1_search or stage3c_closure_verify — no standalone prompts.

1. Stage 1 — Coastal Forest Resources Company, Havana FL (Google Maps: permanently closed)
2. Stage 3c — Earth Fare Inc., Fletcher NC (chain bankrupt+closed; Stage 1b returned null)
3. Stage 1 regression — Progressive Pet Training, Columbia SC
   (pipeline v3 false positive: returned still_operating=true despite Yelp/BringFido "CLOSED")
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

COMPANY = "Coastal Forest Resources Company"
CITY = "Havana"
STATE = "FL"


def print_result(r: dict) -> None:
    print(f"\n{'='*60}")
    print(f"MODEL: {r['model']}")
    print(f"{'='*60}")
    if r.get("error"):
        print(f"  ERROR: {r['error']}")
    elif r["parsed"]:
        p = r["parsed"]
        operating = p.get("still_operating")
        signals = p.get("closure_signals", [])
        correct = operating is False or "permanently_closed" in signals
        print(f"  still_operating : {operating}  {'✓ CORRECT' if not operating and operating is not None else ('✗ WRONG - should be False' if operating else '? UNKNOWN')}")
        print(f"  closure_signals : {signals}")
        print(f"  reasoning       : {p.get('reasoning')}")
    else:
        print("  [could not parse JSON]")
        print(f"  raw: {r['raw'][:400]}")


from src.shared.observability import ObservabilityLogger
from src.part4_pipeline import stage1_search
import anthropic as _anthropic

_client_top = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_obs_top = ObservabilityLogger()

_coastal_record = {
    "handle": "company/coastal-forest-resources-company",
    "name": COMPANY,
    "city": CITY,
    "state": STATE,
    "website": None,
    "poc_condition": "missing_website",
    "poc_segment": "micro",
}

print(f"Target: {COMPANY}, {CITY}, {STATE}")
print("Ground truth: PERMANENTLY CLOSED (Google Maps)\n")
print("Running stage1_search (pipeline path)...")

_coastal_result = stage1_search(_client_top, _coastal_record, _obs_top)
_coastal_operating = _coastal_result.get("still_operating")
_coastal_signals = _coastal_result.get("closure_signals", [])
_ANY_CLOSURE = {"permanently_closed", "closed_announcement", "acquired", "no_results",
                "domain_expired", "domain_for_sale"}
_coastal_pass = _coastal_operating is False or bool(set(_coastal_signals) & _ANY_CLOSURE)

results = [{
    "model": "stage1_search (Haiku v4 + web_search)",
    "raw": str(_coastal_result),
    "parsed": {
        "still_operating": _coastal_operating,
        "closure_signals": _coastal_signals,
        "reasoning": _coastal_result.get("reasoning"),
    },
}]

for r in results:
    print_result(r)
print(f"\n  {'PASS ✓' if _coastal_pass else 'FAIL ✗'} — expected still_operating=false or closure signal present")


# ── Stage 3c test: Earth Fare Inc. (parametric-path closure verification) ─────

print("\n\n" + "=" * 60)
print("STAGE 3C TEST: Earth Fare Inc., Fletcher NC")
print("Ground truth: PERMANENTLY CLOSED (Google Maps)")
print("Scenario: Stage 1b returned still_operating=null — Stage 3c should resolve it")
print("=" * 60)

from src.shared.observability import ObservabilityLogger
from src.part4_pipeline import stage3c_closure_verify
import anthropic

_earth_fare_record = {
    "handle": "company/earth-fare-inc.",
    "name": "Earth Fare",
    "city": "Fletcher",
    "state": "NC",
    "website": "fortunegiver.com",
    "poc_condition": "industry_only",
    "poc_segment": "mid_market",
}

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_obs = ObservabilityLogger()

print("\nCalling stage3c_closure_verify...")
_result = stage3c_closure_verify(_client, _earth_fare_record, _obs)

print(f"\n  still_operating : {_result.get('still_operating')}")
print(f"  closure_signals : {_result.get('closure_signals', [])}")
print(f"  reasoning       : {_result.get('reasoning')}")
print(f"  _stage          : {_result.get('_stage')}")

_operating = _result.get("still_operating")
_signals = _result.get("closure_signals", [])
_pass = _operating is False or bool(set(_signals) & _ANY_CLOSURE)
print(f"\n  {'PASS ✓' if _pass else 'FAIL ✗'} — expected still_operating=false or any closure signal present")


# ── Stage 1 regression: Progressive Pet Training (directory-CLOSED false positive) ───

print("\n\n" + "=" * 60)
print("STAGE 1 REGRESSION: Progressive Pet Training, Columbia SC")
print("Ground truth: CLOSED (Yelp + directory listings show 'CLOSED' in title/meta)")
print("Scenario: Stage 1 v3 returned still_operating=true (false positive)")
print("Root cause: website found → model ignored directory closure signals")
print("=" * 60)

from src.part4_pipeline import stage1_user_prompt, stage1_search, HAIKU_MODEL

_ppt_record = {
    "handle": "company/progressive-pet-training",
    "name": "Progressive Pet Training",
    "city": "Columbia",
    "state": "South Carolina",
    "website": None,
    "poc_condition": "missing_website",
    "poc_segment": "micro",
}

print("\nCalling stage1_search (same path as pipeline)...")
_ppt_result = stage1_search(_client, _ppt_record, _obs)

_ppt_operating = _ppt_result.get("still_operating")
_ppt_signals = _ppt_result.get("closure_signals", [])
_ppt_pass = _ppt_operating is False or bool(set(_ppt_signals) & _ANY_CLOSURE)
print(f"\n  still_operating : {_ppt_operating}")
print(f"  closure_signals : {_ppt_signals}")
print(f"  reasoning       : {_ppt_result.get('reasoning')}")
print(f"  candidate_website: {_ppt_result.get('candidate_website')}")
print(f"  _stage          : {_ppt_result.get('_stage')}")
print(f"\n  {'PASS ✓' if _ppt_pass else 'FAIL ✗'} — expected still_operating=false or closure signal present")
