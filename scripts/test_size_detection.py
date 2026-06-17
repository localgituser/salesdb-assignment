"""
Test employee count detection for American Advanced Management, Modesto CA.
Ground truth: 5K-10K (LinkedIn).

Tests two prompt variants with Haiku + web_search (max_uses=2):
  v_current  — current pipeline rule: prefer location-specific headcount
  v_fixed    — revised rule: use org-level headcount for management/holding entities
"""
import json
import os
from dotenv import load_dotenv

load_dotenv()

COMPANY = "American Advanced Management"
CITY = "Modesto"
STATE = "CA"
GROUND_TRUTH = "5K-10K"

SIZE_ENUM = ["1-10", "11-50", "51-200", "201-500", "501-1K", "1K-5K", "5K-10K", "10K+"]

SIZE_BANDS = ", ".join(SIZE_ENUM)

PROMPT_CURRENT = f"""\
Find accurate information for this company using web search.

Company: {COMPANY}
Location: {CITY}, {STATE}

Search for this company and return ONLY this JSON:
{{
  "candidate_size": "51-200",
  "size_confidence": 0.6,
  "reasoning": "one sentence"
}}

Rules:
- candidate_size: prefer location-specific or facility-specific headcount.
  If ONLY corporate-wide or parent org headcount is found, set candidate_size=null and size_confidence=0.30.
  Phrases like "at this location", "this facility employs", "regional office" are preferred.
  Size bands: {SIZE_BANDS}
  Must be exactly one of: {SIZE_BANDS}
- size_confidence: 0.0 = no evidence, 1.0 = certain structured data from authoritative source.
- reasoning: one sentence.
"""

PROMPT_FIXED = f"""\
Find accurate information for this company using web search.

Company: {COMPANY}
Location: {CITY}, {STATE}

Search for this company and return ONLY this JSON:
{{
  "candidate_size": "51-200",
  "size_confidence": 0.6,
  "reasoning": "one sentence"
}}

Rules:
- candidate_size: use the total employee count for this legal entity.
  If the company is a management company, operator, or multi-site organization, use the
  total organizational headcount — NOT a single location's headcount.
  If the company is a single facility that belongs to a larger parent system, prefer the
  facility-specific headcount over the parent system's total.
  If ONLY a parent system headcount is found with no data for this specific entity, set
  candidate_size=null and size_confidence=0.30.
  Size bands: {SIZE_BANDS}
  Must be exactly one of: {SIZE_BANDS}
- size_confidence: 0.0 = no evidence, 1.0 = certain structured data from authoritative source.
- reasoning: one sentence.
"""


def parse_json_from_text(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:]).rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return None


def run_haiku(prompt: str, label: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
        messages=[{"role": "user", "content": prompt}],
    )
    text = ""
    for block in resp.content:
        if hasattr(block, "text"):
            text = block.text
    return {"label": label, "raw": text, "parsed": parse_json_from_text(text)}


def print_result(r: dict) -> None:
    print(f"\n{'='*60}")
    print(f"VARIANT: {r['label']}")
    print(f"{'='*60}")
    if r["parsed"]:
        p = r["parsed"]
        size = p.get("candidate_size")
        conf = p.get("size_confidence")
        correct = size == GROUND_TRUTH
        print(f"  candidate_size   : {size}  {'✓ CORRECT' if correct else f'✗ WRONG (expected {GROUND_TRUTH})'}")
        print(f"  size_confidence  : {conf}")
        print(f"  reasoning        : {p.get('reasoning')}")
    else:
        print("  [could not parse JSON]")
        print(f"  raw: {r['raw'][:400]}")


print(f"Target: {COMPANY}, {CITY}, {STATE}")
print(f"Ground truth: {GROUND_TRUTH} employees (LinkedIn)\n")
print("Running queries...")

results = []
for prompt, label in [
    (PROMPT_CURRENT, "current  — prefer location-specific headcount"),
    (PROMPT_FIXED,   "fixed    — org-level for management entities"),
]:
    try:
        r = run_haiku(prompt, label)
        results.append(r)
        print(f"  {label}: done")
    except Exception as e:
        results.append({"label": label, "raw": "", "parsed": None, "error": str(e)})
        print(f"  {label}: ERROR — {e}")

for r in results:
    print_result(r)
