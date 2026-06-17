"""
Test whether adding is_single_facility classification to Stage 1 improves size accuracy.

Ground truth cases:
  American Advanced Management, Modesto CA  → multi-site operator  → 5K-10K
  Avera McKennan Hospital, Sioux Falls SD   → single facility      → size from parquet (501-1K area)
"""
import json
import os
from dotenv import load_dotenv

load_dotenv()

SIZE_ENUM = ["1-10", "11-50", "51-200", "201-500", "501-1K", "1K-5K", "5K-10K", "10K+"]
SIZE_BANDS = ", ".join(SIZE_ENUM)

CASES = [
    {
        "company": "American Advanced Management",
        "city": "Modesto",
        "state": "CA",
        "expected_size": "5K-10K",
        "expected_single_facility": False,
        "note": "hospital management company — operates multiple sites",
    },
    {
        "company": "Avera McKennan Hospital",
        "city": "Sioux Falls",
        "state": "SD",
        "expected_size": None,  # just checking is_single_facility classification
        "expected_single_facility": True,
        "note": "single hospital campus (part of Avera Health system)",
    },
]

PROMPT_TEMPLATE = """\
Find accurate information for this company using web search.

Company: {company}
Location: {city}, {state}

Return ONLY this JSON:
{{
  "is_single_facility": true,
  "candidate_size": "51-200",
  "size_confidence": 0.6,
  "reasoning": "one sentence"
}}

Rules:
- is_single_facility: classify based on how this entity employs its workforce, not whether it
  belongs to a larger parent.
  true  → this record IS the operating location (a hospital campus, a store, a factory, a single
           office). It may belong to a larger parent system, but it is itself one site.
  false → this record IS the operator/manager: a management company, franchisor, holding company,
           or multi-site organization that directly employs staff across multiple locations it runs.
  null  → genuinely unclear.
  Key test: does the entity in this record sign the payroll for multiple sites? If yes → false.
- candidate_size: depends on is_single_facility.
  If is_single_facility=true: prefer the headcount for this specific location or facility.
    If only a parent system's total is available, set candidate_size=null and size_confidence=0.30.
  If is_single_facility=false: use the total organizational headcount for this entity across
    all locations it operates or manages.
  Size bands: {size_bands}
  Must be exactly one of: {size_bands}
- size_confidence: 0.0 = no evidence, 1.0 = certain from authoritative source (LinkedIn, SEC, etc).
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


def run_haiku(prompt: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=800,
        system="You are a business data extractor. Always respond with ONLY a valid JSON object. No markdown, no explanation outside the JSON.",
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
        messages=[{"role": "user", "content": prompt}],
    )
    text = ""
    for block in resp.content:
        if hasattr(block, "text"):
            text = block.text
    return {"raw": text, "parsed": parse_json_from_text(text)}


def print_result(case: dict, r: dict) -> None:
    print(f"\n{'='*60}")
    print(f"COMPANY: {case['company']}, {case['city']} {case['state']}")
    print(f"Note:    {case['note']}")
    print(f"{'='*60}")
    if r["parsed"]:
        p = r["parsed"]
        isf = p.get("is_single_facility")
        size = p.get("candidate_size")
        conf = p.get("size_confidence")

        isf_correct = isf == case["expected_single_facility"]
        size_correct = size == case["expected_size"] if case["expected_size"] else None

        print(f"  is_single_facility : {isf}  {'✓' if isf_correct else '✗'} (expected {case['expected_single_facility']})")
        if case["expected_size"]:
            expected = case["expected_size"]
            print(f"  candidate_size     : {size}  {'✓' if size_correct else f'✗ (expected {expected})'}")
        else:
            print(f"  candidate_size     : {size}  (no size ground truth for this case)")
        print(f"  size_confidence    : {conf}")
        print(f"  reasoning          : {p.get('reasoning')}")
    else:
        print("  [could not parse JSON]")
        print(f"  raw: {r['raw'][:400]}")


print("Testing is_single_facility classification + size accuracy\n")

for case in CASES:
    prompt = PROMPT_TEMPLATE.format(
        company=case["company"],
        city=case["city"],
        state=case["state"],
        size_bands=SIZE_BANDS,
    )
    try:
        r = run_haiku(prompt)
        print(f"  {case['company']}: done")
    except Exception as e:
        r = {"raw": str(e), "parsed": None}
        print(f"  {case['company']}: ERROR — {e}")
    print_result(case, r)
