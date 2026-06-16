"""
Test closure detection across two scenarios:

1. Stage 1 search path — Coastal Forest Resources Company, Havana FL
   (original test: web_search tool available, Google Maps says permanently closed)

2. Stage 3c closure verification — Earth Fare Inc., Fletcher NC
   (new test: simulates parametric path returning still_operating=null, then calls
   stage3c_closure_verify to resolve via targeted web search)
"""
import json
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

PROMPT = f"""\
Search the web for current information about this company and return ONLY a JSON object.

Company: {COMPANY}
Location: {CITY}, {STATE}

Return ONLY this JSON:
{{
  "still_operating": true,
  "closure_signals": [],
  "reasoning": "one sentence"
}}

Rules:
- still_operating: true if active. false if results mention "out of business", "permanently closed",
  "ceased operations", Google Maps shows "Permanently closed", or domain expired/for sale. null if unknown.
- closure_signals: array of zero or more: "no_results", "domain_expired", "website_404",
  "closed_announcement", "domain_for_sale", "permanently_closed".
  Use "permanently_closed" when Google Maps or a directory explicitly labels the location as permanently closed.
- reasoning: one sentence explaining the determination.
"""


def parse_json_from_text(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]).rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON block within the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return None


def run_claude(model_id: str, label: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=model_id,
        max_tokens=512,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
        messages=[{"role": "user", "content": PROMPT}],
    )
    # Extract final text block (after tool use)
    text = ""
    for block in resp.content:
        if hasattr(block, "text"):
            text = block.text
    return {"model": label, "raw": text, "parsed": parse_json_from_text(text)}


def run_gemini() -> dict:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=PROMPT,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    text = resp.text or ""
    return {"model": "gemini-2.5-flash (grounding)", "raw": text, "parsed": parse_json_from_text(text)}


def run_perplexity() -> dict:
    import requests
    headers = {
        "Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "sonar",
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 512,
    }
    resp = requests.post("https://api.perplexity.ai/chat/completions", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()
    return {"model": "perplexity-sonar", "raw": text, "parsed": parse_json_from_text(text)}


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


runners = [
    ("claude", "claude-haiku-4-5", "claude-haiku-4-5 + web_search (max_uses=2)"),
    # ("claude", "claude-sonnet-4-5", "claude-sonnet-4-5 + web_search"),
    # ("gemini", None, None),
    # Perplexity skipped — account has no credits (quota exhausted)
    # ("perplexity", None, None),
]

results = []
print(f"Target: {COMPANY}, {CITY}, {STATE}")
print("Ground truth: PERMANENTLY CLOSED (Google Maps)\n")
print("Running queries...")

for runner_type, model_id, label in runners:
    try:
        if runner_type == "claude":
            r = run_claude(model_id, label)
        elif runner_type == "gemini":
            r = run_gemini()
        else:
            r = run_perplexity()
        results.append(r)
        print(f"  {r['model']}: done")
    except Exception as e:
        name = label or ("gemini-2.0-flash" if runner_type == "gemini" else "perplexity-sonar")
        results.append({"model": name, "raw": "", "parsed": None, "error": str(e)})
        print(f"  {name}: ERROR — {e}")

for r in results:
    print_result(r)


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
_pass = _operating is False or "permanently_closed" in _signals
print(f"\n  {'PASS ✓' if _pass else 'FAIL ✗'} — expected still_operating=false or permanently_closed in signals")
