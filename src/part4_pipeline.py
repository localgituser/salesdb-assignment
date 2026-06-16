"""
Part 4 PoC enrichment pipeline.

Cascade:
  Stage 0 — Rules ($0): detect platform/institutional URLs, pass-through clean values
  Stage 1 — Haiku + web_search: find website, extract type/size/industry_raw
  Stage 1b — Haiku parametric: classify industry for records that already have a website
  Stage 2 — Deterministic industry snap ($0): fuzzy match industry_raw → canonical label
  Stage 3 — Haiku verify: confirm candidate website matches company (low-confidence records only)
  Stage 4 — Sonnet resolution: resolve conflicts/uncertain fields (~18% of records)

State machine per record:
  Stage 1/1b uncertain → escalate to Stage 3 (verify)
  Stage 3 uncertain → escalate to Stage 4 (Sonnet)
  Stage 4 uncertain → status=unresolved, move on
  Budget hit → status=budget_exhausted for remaining records
"""

import difflib
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import duckdb
import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.shared.config import CONFIG
from src.shared.observability import ObservabilityLogger
from src.part4_gate import (
    GateFailure,
    check_batch_quality,
    check_cascade_health,
    check_part4_entry,
    enforce,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(message)s")

# ── Paths & constants ──────────────────────────────────────────────────────────

BATCH_PATH = str(ROOT / "data/processed/part1_sample_audit.parquet")
ENRICHED_PATH = str(ROOT / "data/enriched/part4_enriched_sample.parquet")
PIPELINE_VERSION = "v1"

HAIKU_MODEL = CONFIG.models.classification   # claude-haiku-4-5-20251001
SONNET_MODEL = CONFIG.models.judgment        # claude-sonnet-4-6

HAIKU_USD_PER_M = {"input": 0.80, "output": 4.00}
SONNET_USD_PER_M = {"input": 3.00, "output": 15.00}

PART4_BUDGET = CONFIG.budget.per_part_usd.get("part_4", 5.0)

TYPE_ENUM = [
    "Privately Held", "Self-Owned", "Nonprofit", "Partnership",
    "Public Company", "Self-Employed", "Educational", "Government Agency",
]
SIZE_ENUM = ["1-10", "11-50", "51-200", "201-500", "501-1K", "1K-5K", "5K-10K", "10K+"]

# All 492 canonical industry labels from the dataset
INDUSTRY_LABELS = [
    "abrasives and nonmetallic minerals manufacturing", "accessible architecture and design",
    "accessible hardware manufacturing", "accommodation and food services", "accounting",
    "administration of justice", "administrative and support services", "advertising services",
    "agricultural chemical manufacturing",
    "agriculture, construction, mining machinery manufacturing",
    "air, water, and waste program management", "airlines and aviation",
    "alternative dispute resolution", "alternative fuel vehicle manufacturing",
    "alternative medicine", "ambulance services", "amusement parks and arcades",
    "animal feed manufacturing", "animation", "animation and post-production",
    "apparel & fashion", "apparel manufacturing",
    "appliances, electrical, and electronics manufacturing",
    "architectural and structural metal manufacturing", "architecture and planning",
    "armed forces", "artificial rubber and synthetic fiber manufacturing",
    "artists and writers", "arts & crafts", "audio and video equipment manufacturing",
    "automation machinery manufacturing", "automotive", "aviation & aerospace",
    "aviation and aerospace component manufacturing", "baked goods manufacturing", "banking",
    "bars, taverns, and nightclubs", "bed-and-breakfasts, hostels, homestays",
    "beverage manufacturing", "biomass electric power generation", "biotechnology",
    "biotechnology research", "blockchain services", "blogs",
    "boilers, tanks, and shipping container manufacturing", "book and periodical publishing",
    "book publishing", "breweries", "broadcast media production and distribution",
    "building construction", "building equipment contractors", "building finishing contractors",
    "building materials", "building structure and exterior contractors",
    "business consulting and services", "business content", "business intelligence platforms",
    "business supplies & equipment", "cable and satellite programming", "capital markets",
    "caterers", "chemical manufacturing", "chemical raw materials manufacturing",
    "child day care services", "chiropractors", "circuses and magic shows",
    "civic and social organizations", "civil engineering",
    "claims adjusting, actuarial services", "clay and refractory products manufacturing",
    "climate data and analytics", "climate technology product manufacturing", "coal mining",
    "collection agencies", "commercial and industrial equipment rental",
    "commercial and industrial machinery maintenance",
    "commercial and service industry machinery manufacturing", "commercial real estate",
    "communications equipment manufacturing",
    "community development and urban planning", "community services",
    "computer and network security", "computer games", "computer hardware",
    "computer hardware manufacturing", "computer networking", "computer networking products",
    "computers and electronics manufacturing", "conservation programs", "construction",
    "construction hardware manufacturing", "consumer electronics", "consumer goods",
    "consumer goods rental", "consumer services", "correctional institutions", "cosmetics",
    "cosmetology and barber schools", "courts of law", "credit intermediation",
    "cutlery and handtool manufacturing", "dairy", "dairy product manufacturing",
    "dance companies", "data infrastructure and analytics", "data security software products",
    "defense & space", "defense and space manufacturing", "dentists", "design",
    "design services", "desktop computing software products", "digital accessibility services",
    "distilleries", "e-learning", "e-learning providers", "economic programs", "education",
    "education administration programs", "education management",
    "electric lighting equipment manufacturing", "electric power generation",
    "electric power transmission, control, and distribution", "electrical equipment manufacturing",
    "electronic and precision equipment maintenance", "embedded software products",
    "emergency and relief services", "engineering services",
    "engines and power transmission equipment manufacturing", "entertainment",
    "entertainment providers", "environmental quality programs", "environmental services",
    "equipment rental services", "events services", "executive offices",
    "executive search services", "fabricated metal products", "facilities services",
    "family planning centers", "farming", "farming, ranching, forestry",
    "fashion accessories manufacturing", "financial services", "fine art", "fine arts schools",
    "fire protection", "fisheries", "flight training", "food & beverages",
    "food and beverage manufacturing", "food and beverage retail", "food and beverage services",
    "food production", "footwear and leather goods repair", "footwear manufacturing",
    "forestry and logging", "fossil fuel electric power generation",
    "freight and package transportation", "fruit and vegetable preserves manufacturing",
    "fuel cell manufacturing", "fundraising", "funds and trusts", "furniture",
    "furniture and home furnishings manufacturing", "gambling facilities and casinos",
    "geothermal electric power generation", "glass product manufacturing",
    "glass, ceramics and concrete manufacturing", "golf courses and country clubs",
    "government administration", "government relations", "government relations services",
    "graphic design", "ground passenger transportation", "health and human services",
    "health, wellness & fitness", "higher education",
    "highway, street, and bridge construction", "historical sites", "holding companies",
    "home health care services", "horticulture", "hospitality", "hospitals",
    "hospitals and health care", "hotels and motels",
    "household and institutional furniture manufacturing", "household appliance manufacturing",
    "household services", "housing and community development", "housing programs",
    "human resources", "human resources services",
    "hvac and refrigeration equipment manufacturing", "hydroelectric power generation",
    "import & export", "individual and family services", "industrial automation",
    "industrial machinery manufacturing", "industry associations", "information services",
    "information technology & services", "insurance", "insurance agencies and brokerages",
    "insurance and employee benefit funds", "insurance carriers", "interior design",
    "international affairs", "international trade and development",
    "internet marketplace platforms", "internet news", "internet publishing",
    "interurban and rural bus services", "investment advice", "investment banking",
    "investment management", "it services and it consulting",
    "it system custom software development", "it system data services",
    "it system design services", "it system installation and disposal",
    "it system operations and maintenance", "it system testing and evaluation",
    "it system training and support", "janitorial services", "landscaping services",
    "language schools", "laundry and drycleaning services", "law enforcement", "law practice",
    "leasing non-residential real estate", "leasing residential real estate",
    "leather product manufacturing", "legal services", "legislative offices",
    "leisure, travel & tourism", "libraries", "lime and gypsum products manufacturing",
    "loan brokers", "luxury goods & jewelry", "machinery manufacturing",
    "magnetic and optical media manufacturing", "manufacturing", "maritime",
    "maritime transportation", "market research", "marketing services",
    "mattress and blinds manufacturing", "measuring and control instrument manufacturing",
    "meat products manufacturing", "mechanical or industrial engineering",
    "media and telecommunications", "media production", "medical and diagnostic laboratories",
    "medical device", "medical equipment manufacturing", "medical practices",
    "mental health care", "metal ore mining", "metal treatments",
    "metal valve, ball, and roller manufacturing", "metalworking machinery manufacturing",
    "military and international affairs", "mining", "mobile computing software products",
    "mobile food services", "mobile gaming apps", "motor vehicle manufacturing",
    "motor vehicle parts manufacturing", "movies and sound recording",
    "movies, videos, and sound", "museums", "museums, historical sites, and zoos", "music",
    "musicians", "nanotechnology research", "natural gas distribution", "natural gas extraction",
    "newspaper publishing", "non-profit organization management", "non-profit organizations",
    "nonmetallic mineral mining", "nonresidential building construction",
    "nuclear electric power generation", "nursing homes and residential care facilities",
    "office administration", "office furniture and fixtures manufacturing",
    "oil and coal product manufacturing", "oil and gas", "oil extraction",
    "oil, gas, and mining", "online and mail order retail", "online audio and video media",
    "online media", "operations consulting", "optometrists", "outpatient care centers",
    "outsourcing and offshoring consulting", "outsourcing/offshoring",
    "packaging & containers", "packaging and containers manufacturing",
    "paint, coating, and adhesive manufacturing", "paper & forest products",
    "paper and forest product manufacturing", "pension funds", "performing arts",
    "performing arts and spectator sports", "periodical publishing",
    "personal and laundry services", "personal care product manufacturing",
    "personal care services", "pet services", "pharmaceutical manufacturing",
    "philanthropic fundraising services", "philanthropy", "photography",
    "physical, occupational and speech therapists", "physicians", "pipeline transportation",
    "plastics and rubber product manufacturing", "plastics manufacturing",
    "political organizations", "postal services", "primary and secondary education",
    "primary metal manufacturing", "printing services", "professional organizations",
    "professional services", "professional training and coaching", "program development",
    "public assistance programs", "public health", "public policy", "public policy offices",
    "public relations and communications services", "public safety", "racetracks",
    "radio and television broadcasting", "rail transportation",
    "railroad equipment manufacturing", "ranching", "ranching and fisheries", "real estate",
    "real estate agents and brokers", "real estate and equipment rental services",
    "recreational facilities", "regenerative design", "religious institutions",
    "renewable energy equipment manufacturing", "renewable energy power generation",
    "renewable energy semiconductor manufacturing", "renewables & environment",
    "repair and maintenance", "research", "research services",
    "residential building construction", "restaurants", "retail",
    "retail apparel and fashion", "retail appliances, electrical, and electronic equipment",
    "retail art dealers", "retail art supplies", "retail books and printed news",
    "retail building materials and garden equipment", "retail florists",
    "retail furniture and home furnishings", "retail gasoline", "retail groceries",
    "retail health and personal care products", "retail luxury goods and jewelry",
    "retail motor vehicles", "retail musical instruments", "retail office equipment",
    "retail office supplies and gifts", "retail pharmacies",
    "retail recyclable materials & used merchandise", "reupholstery and furniture repair",
    "robot manufacturing", "robotics engineering", "rubber products manufacturing",
    "satellite telecommunications", "savings institutions", "school and employee bus services",
    "seafood product manufacturing", "securities and commodity exchanges",
    "security and investigations", "security guards and patrol services",
    "security systems services", "semiconductor manufacturing", "semiconductors",
    "services for renewable energy", "services for the elderly and disabled",
    "sheet music publishing", "shipbuilding",
    "shuttles and special needs transportation services", "sightseeing transportation",
    "skiing facilities", "smart meter manufacturing", "soap and cleaning product manufacturing",
    "social networking platforms", "software development", "solar electric power generation",
    "sound recording", "space research and technology", "specialty trade contractors",
    "spectator sports", "sporting goods", "sporting goods manufacturing",
    "sports and recreation instruction", "sports teams and clubs",
    "spring and wire product manufacturing", "staffing and recruiting",
    "steam and air-conditioning supply", "strategic management services", "subdivision of land",
    "sugar and confectionery product manufacturing", "surveying and mapping services",
    "taxi and limousine services", "technical and vocational training",
    "technology, information and internet", "technology, information and media",
    "telecommunications", "telecommunications carriers", "telephone call centers",
    "temporary help services", "textile manufacturing", "theater companies", "think tanks",
    "tobacco", "tobacco manufacturing", "translation and localization",
    "transportation equipment manufacturing", "transportation programs",
    "transportation, logistics, supply chain and storage",
    "transportation/trucking/railroad", "travel arrangements", "truck transportation",
    "trusts and estates", "turned products and fastener manufacturing",
    "urban transit services", "utilities", "utilities administration",
    "utility system construction", "vehicle repair and maintenance",
    "venture capital and private equity principals", "veterinary", "veterinary services",
    "vocational rehabilitation services", "warehousing", "warehousing and storage",
    "waste collection", "waste treatment and disposal", "water supply and irrigation systems",
    "water, waste, steam, and air conditioning services", "wellness and fitness services",
    "wholesale", "wholesale alcoholic beverages", "wholesale apparel and sewing supplies",
    "wholesale appliances, electrical, and electronics", "wholesale building materials",
    "wholesale chemical and allied products", "wholesale computer equipment",
    "wholesale drugs and sundries", "wholesale food and beverage", "wholesale footwear",
    "wholesale furniture and home furnishings",
    "wholesale hardware, plumbing, heating equipment", "wholesale import and export",
    "wholesale luxury goods and jewelry", "wholesale machinery",
    "wholesale metals and minerals", "wholesale motor vehicles and parts",
    "wholesale paper products", "wholesale petroleum and petroleum products",
    "wholesale photography equipment and supplies", "wholesale raw farm products",
    "wholesale recyclable materials", "wind electric power generation", "wine & spirits",
    "wineries", "wireless services", "wood product manufacturing", "writing and editing",
    "zoos and botanical gardens",
]

PLATFORM_BLOCKLIST = CONFIG.enrichment_rules.platform_blocklist_set
INSTITUTIONAL_TLDS = frozenset([".edu", ".gov", ".mil"])

# ── Helpers ────────────────────────────────────────────────────────────────────

def compute_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    p = HAIKU_USD_PER_M if "haiku" in model else SONNET_USD_PER_M
    return (input_tokens / 1_000_000 * p["input"]) + (output_tokens / 1_000_000 * p["output"])


def is_platform_url(url: Any) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    stripped = url.lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
    for blocked in PLATFORM_BLOCKLIST:
        if stripped.startswith(blocked):
            return True
    for tld in INSTITUTIONAL_TLDS:
        if tld in stripped.split("/")[0]:
            return True
    return False


def normalize_domain(url: Any) -> Optional[str]:
    """Strip protocol and www, return bare domain or None."""
    if not isinstance(url, str) or not url.strip():
        return None
    d = url.lower().strip().removeprefix("https://").removeprefix("http://").removeprefix("www.")
    d = d.split("/")[0].split("?")[0].rstrip(".")
    return d if d else None


_STOP_WORDS = frozenset(["and", "or", "of", "the", "a", "an", "in", "for", "to", "with",
                          "by", "at", "on", "its", "as", "from", "&"])

# Priority keyword → canonical label (first match wins; ordered by specificity)
_KEYWORD_MAP: list[tuple[frozenset, str]] = [
    (frozenset(["hospital", "hospitals"]), "hospitals and health care"),
    (frozenset(["restaurant", "restaurants", "dining", "eatery"]), "restaurants"),
    (frozenset(["maritime", "shipping", "tanker", "bulk", "liquid"]), "maritime transportation"),
    (frozenset(["law", "attorney", "attorneys", "lawyers", "litigation", "llp", "p.a."]), "law practice"),
    (frozenset(["legal"]), "legal services"),
    # "district" + any school keyword → K-12, not higher education
    (frozenset(["district", "isd", "k-12", "k12", "elementary", "secondary"]), "primary and secondary education"),
    (frozenset(["school"]), "primary and secondary education"),
    (frozenset(["vehicle", "auto", "automobile", "body", "repair"]), "vehicle repair and maintenance"),
    (frozenset(["defense", "missile", "munitions"]), "defense and space manufacturing"),
    (frozenset(["aerospace", "space", "satellite", "rocket", "launch"]), "aviation and aerospace component manufacturing"),
    (frozenset(["skincare", "beauty", "cosmetics", "personal", "care"]), "personal care product manufacturing"),
    (frozenset(["staffing", "recruiting", "temp", "placement"]), "staffing and recruiting"),
    (frozenset(["trucking", "truck", "freight", "hauling"]), "truck transportation"),
    (frozenset(["it", "software", "saas", "app", "platform", "cloud", "tech"]), "it services and it consulting"),
    (frozenset(["consulting", "advisory", "management", "strategy"]), "business consulting and services"),
    (frozenset(["real", "estate", "realty", "property", "brokerage"]), "real estate"),
    (frozenset(["warehouse", "warehousing", "storage", "fulfillment"]), "warehousing and storage"),
    (frozenset(["construction", "contractor", "building"]), "construction"),
    (frozenset(["healthcare", "health", "medical", "clinical"]), "hospitals and health care"),
    (frozenset(["education", "university", "college", "higher"]), "higher education"),
    (frozenset(["nonprofit", "non-profit", "charity", "foundation"]), "philanthropic fundraising services"),
    (frozenset(["government", "agency", "federal", "municipal"]), "government administration"),
    (frozenset(["public", "safety", "corrections", "prison"]), "public safety"),
    (frozenset(["outsourcing", "bpo", "offshoring"]), "outsourcing and offshoring consulting"),
    (frozenset(["insurance"]), "insurance"),
    (frozenset(["banking", "bank", "financial"]), "banking"),
    (frozenset(["retail"]), "retail"),
    (frozenset(["hospitality", "hotel", "lodging"]), "hospitality"),
    (frozenset(["manufacturing"]), "manufacturing"),
    (frozenset(["logistics", "supply", "chain", "distribution"]), "transportation, logistics, supply chain and storage"),
    (frozenset(["telecom", "telecommunications", "wireless"]), "telecommunications"),
    (frozenset(["defense", "military"]), "defense and space manufacturing"),
]


def snap_industry(raw: Optional[str]) -> Optional[str]:
    """Map a free-text industry description to the closest canonical label."""
    if not raw or not raw.strip():
        return None
    raw_lower = raw.lower().strip()

    # Exact match
    if raw_lower in INDUSTRY_LABELS:
        return raw_lower

    # Exact prefix containment (whole-word only: avoid "maritime" matching "maritime transportation")
    for label in INDUSTRY_LABELS:
        if raw_lower == label:
            return label
        # raw fully contained in label as a prefix (e.g. raw="hospital" → label="hospitals and health care")
        if (label.startswith(raw_lower + " ") or label == raw_lower):
            return label

    # Priority keyword lookup
    raw_words = [w for w in re.split(r"[\s,&/\-]+", raw_lower) if w and w not in _STOP_WORDS]
    raw_word_set = set(raw_words)

    if not raw_word_set:
        return None

    # Priority keyword table
    for keyword_set, label in _KEYWORD_MAP:
        if keyword_set & raw_word_set:
            return label

    best_score, best_match = 0.0, None
    for label in INDUSTRY_LABELS:
        label_words = set(re.split(r"[\s,&/]+", label)) - _STOP_WORDS
        if not label_words:
            continue
        # Precision: fraction of raw words found in label
        hits = sum(1 for w in raw_word_set if w in label_words or any(w in lw for lw in label_words))
        precision = hits / len(raw_word_set)
        # Recall: fraction of raw words found in label (prefer labels that cover most raw words)
        recall = hits / len(label_words) if label_words else 0.0
        # F1-like score
        score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        if score > best_score:
            best_score, best_match = score, label

    if best_score >= 0.35:
        return best_match

    # Last resort: difflib character-level similarity
    matches = difflib.get_close_matches(raw_lower, INDUSTRY_LABELS, n=1, cutoff=0.45)
    return matches[0] if matches else None


def extract_json(text: str) -> dict:
    """Parse JSON from model text — tries code block then bare JSON."""
    # Code block
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Bare JSON object
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def get_text(response: anthropic.types.Message) -> str:
    """Extract the last text block from an Anthropic message."""
    text_blocks = [b for b in response.content if getattr(b, "type", None) == "text"]
    return text_blocks[-1].text if text_blocks else ""

# ── Prompts ────────────────────────────────────────────────────────────────────

STAGE1_SYSTEM = """\
You are a business data enrichment assistant. Use web search to find accurate firmographic \
data for the company provided. Return ONLY a JSON object, no prose."""

def stage1_user_prompt(name: str, city: str, state: str, existing_website: Optional[str]) -> str:
    website_line = (
        f"Current website in database (possibly wrong/outdated): {existing_website}"
        if existing_website
        else "No website on record."
    )
    return f"""\
Find accurate information for this company using web search.

Company: {name}
Location: {city}, {state}
{website_line}

Search for this company and return ONLY this JSON:
{{
  "candidate_website": "domain.com",
  "candidate_type": "Privately Held",
  "candidate_size": "51-200",
  "industry_raw": "commercial heating and cooling services",
  "website_confidence": 0.85,
  "type_confidence": 0.7,
  "size_confidence": 0.6,
  "industry_confidence": 0.8,
  "reasoning": "one sentence"
}}

Rules:
- candidate_website: bare domain only (no https://, no www., no path). null if not found.
- candidate_type must be exactly one of: {", ".join(TYPE_ENUM)}
- candidate_size must be exactly one of: {", ".join(SIZE_ENUM)}
  Size band employee ranges: 1-10, 11-50, 51-200, 201-500, 501-1K (501–1000), 1K-5K (1001–5000), 5K-10K (5001–10000), 10K+ (over 10000).
  Use the company's own website headcount or recent news — do not guess from name alone.
- industry_raw: 2-4 words describing the primary business. null if unclear.
- Use null for any field you cannot determine confidently.
- Confidence: 0.0 = no evidence, 1.0 = certain."""


STAGE1B_SYSTEM = """\
You are a business classifier. Based on company name and location, infer firmographic fields. \
Return ONLY a JSON object."""

def stage1b_user_prompt(name: str, city: str, state: str, existing_website: Optional[str],
                         existing_type: Optional[str], existing_size: Optional[str]) -> str:
    return f"""\
Classify this company using name and location (no web search).

Company: {name}
Location: {city}, {state}
Website: {existing_website or "unknown"}
Stored type: {existing_type or "unknown"}
Stored size: {existing_size or "unknown"}

Return ONLY this JSON:
{{
  "candidate_type": "Privately Held",
  "candidate_size": "51-200",
  "industry_raw": "commercial heating and cooling services",
  "type_confidence": 0.6,
  "size_confidence": 0.5,
  "industry_confidence": 0.75,
  "reasoning": "one sentence"
}}

Rules:
- candidate_type must be exactly one of: {", ".join(TYPE_ENUM)}
- candidate_size must be exactly one of: {", ".join(SIZE_ENUM)}
- industry_raw: 2-4 words describing the primary business. null if unclear.
- Use null for fields you cannot determine with confidence > 0.5."""


STAGE3_SYSTEM = """\
You are a website verification assistant. Determine whether a candidate website domain \
belongs to the specified company. Return ONLY a JSON object."""

def stage3_user_prompt(name: str, city: str, state: str, candidate_website: str) -> str:
    return f"""\
Does this website belong to this company?

Company: {name}
Location: {city}, {state}
Candidate website: {candidate_website}

Consider:
1. Does the domain relate to the company name?
2. Is it a direct company site (not a job board, social media, or directory)?
3. Could this be a different company with a similar name in a different location?
4. Is this a parent organization or umbrella brand rather than the specific company's own site?
   (e.g. a hospital system's root domain instead of the specific hospital's subdomain/page)

Return ONLY this JSON:
{{
  "website_verified": true,
  "website_confidence": 0.9,
  "reasoning": "domain matches company name and is a direct company site"
}}"""


STAGE4_SYSTEM = """\
You are a senior data quality analyst. Resolve uncertain or conflicting enrichment fields \
for the company record below. Return ONLY a JSON object with final values."""

def stage4_user_prompt(record: dict, stage1_result: dict, stage3_result: dict,
                        uncertain_fields: list) -> str:
    return f"""\
Resolve uncertain enrichment for this company.

Original record:
  Handle: {record['handle']}
  Name:   {record['name']}
  City:   {record['city']}, {record['state']}
  Stored website:  {record.get('website') or 'null'}
  Stored type:     {record.get('type') or 'null'}
  Stored size:     {record.get('size') or 'null'}
  Stored industry: {record.get('industry') or 'null'}

Stage 1 found:
  Website:    {stage1_result.get('candidate_website') or 'null'} (confidence {stage1_result.get('website_confidence', 0):.2f})
  Type:       {stage1_result.get('candidate_type') or 'null'} (confidence {stage1_result.get('type_confidence', 0):.2f})
  Size:       {stage1_result.get('candidate_size') or 'null'} (confidence {stage1_result.get('size_confidence', 0):.2f})
  Industry:   {stage1_result.get('industry_raw') or 'null'} (confidence {stage1_result.get('industry_confidence', 0):.2f})

Stage 3 website verification:
  Verified: {stage3_result.get('website_verified')}
  Reasoning: {stage3_result.get('reasoning') or 'none'}

Uncertain fields that need resolution: {", ".join(uncertain_fields)}

Return ONLY this JSON with final resolved values:
{{
  "website_final": "domain.com",
  "type_final": "Privately Held",
  "size_final": "51-200",
  "industry_final": "commercial heating and cooling services",
  "website_confidence": 0.85,
  "type_confidence": 0.7,
  "size_confidence": 0.6,
  "industry_confidence": 0.75,
  "resolution_notes": "one sentence"
}}

Rules:
- Use null for fields that cannot be resolved.
- candidate_type must be exactly one of: {", ".join(TYPE_ENUM)}
- candidate_size must be exactly one of: {", ".join(SIZE_ENUM)}
- industry_final should be the canonical industry label (2-5 words from the dataset taxonomy)"""


# ── Pipeline stages ────────────────────────────────────────────────────────────

def stage0_rules(record: dict) -> dict:
    """
    Deterministic cleanup. Returns enrichment columns for Stage 0 decisions.
    Sets website_pipeline_stage=rules for records where rules resolve the website.
    """
    out: dict[str, Any] = {}
    website = record.get("website")
    out["website_original"] = website
    out["type_original"] = record.get("type")
    out["industry_original"] = record.get("industry")
    out["size_original"] = record.get("size")

    if is_platform_url(website):
        out["website_rules_flag"] = True
        out["website_pipeline_stage"] = "rules_flagged"
    else:
        out["website_rules_flag"] = False
        out["website_pipeline_stage"] = "rules_passthrough"

    return out


def stage1_search(client: anthropic.Anthropic, record: dict, obs: ObservabilityLogger) -> dict:
    """Haiku + web_search: find website, extract type/size/industry for missing/platform records."""
    name = record["name"] or ""
    city = record.get("city") or ""
    state = record.get("state") or ""
    existing_website = record.get("website") if record.get("poc_condition") == "platform_url" else None

    messages = [{"role": "user", "content": stage1_user_prompt(name, city, state, existing_website)}]

    try:
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=512,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}],
            system=STAGE1_SYSTEM,
            messages=messages,
        )
        usage = response.usage
        cost = compute_cost(usage.input_tokens, usage.output_tokens, HAIKU_MODEL)
        obs.log_call(
            phase="part_4", model=HAIKU_MODEL,
            tokens=usage.input_tokens + usage.output_tokens, cost=cost,
            prompt_version="stage1_search_v1", outcome="success",
            metadata={"handle": record["handle"], "stage": 1},
        )
        text = get_text(response)
        result = extract_json(text)
        result["_stage"] = 1
        result["_search_used"] = True
        return result
    except Exception as e:
        log.warning("Stage 1 error for %s: %s", record["handle"], e)
        return {"_stage": 1, "_search_used": True, "_error": str(e)}


def stage1b_parametric(client: anthropic.Anthropic, record: dict, obs: ObservabilityLogger) -> dict:
    """Haiku without search: classify industry/type/size from company name+location alone."""
    name = record["name"] or ""
    city = record.get("city") or ""
    state = record.get("state") or ""
    existing_website = normalize_domain(record.get("website"))
    existing_type = record.get("type") if not _is_nan(record.get("type")) else None
    existing_size = record.get("size") if not _is_nan(record.get("size")) else None

    messages = [{"role": "user", "content": stage1b_user_prompt(
        name, city, state, existing_website, existing_type, existing_size)}]

    try:
        response = client.messages.create(
            model=HAIKU_MODEL, max_tokens=300, system=STAGE1B_SYSTEM, messages=messages,
        )
        usage = response.usage
        cost = compute_cost(usage.input_tokens, usage.output_tokens, HAIKU_MODEL)
        obs.log_call(
            phase="part_4", model=HAIKU_MODEL,
            tokens=usage.input_tokens + usage.output_tokens, cost=cost,
            prompt_version="stage1b_parametric_v1", outcome="success",
            metadata={"handle": record["handle"], "stage": "1b"},
        )
        text = get_text(response)
        result = extract_json(text)
        result["_stage"] = "1b"
        result["_search_used"] = False
        return result
    except Exception as e:
        log.warning("Stage 1b error for %s: %s", record["handle"], e)
        return {"_stage": "1b", "_search_used": False, "_error": str(e)}


def stage3_verify(client: anthropic.Anthropic, record: dict, candidate_website: str,
                  obs: ObservabilityLogger) -> dict:
    """Haiku: verify candidate website matches the company (no search)."""
    name = record["name"] or ""
    city = record.get("city") or ""
    state = record.get("state") or ""

    messages = [{"role": "user", "content": stage3_user_prompt(name, city, state, candidate_website)}]

    try:
        response = client.messages.create(
            model=HAIKU_MODEL, max_tokens=200, system=STAGE3_SYSTEM, messages=messages,
        )
        usage = response.usage
        cost = compute_cost(usage.input_tokens, usage.output_tokens, HAIKU_MODEL)
        obs.log_call(
            phase="part_4", model=HAIKU_MODEL,
            tokens=usage.input_tokens + usage.output_tokens, cost=cost,
            prompt_version="stage3_verify_v1", outcome="success",
            metadata={"handle": record["handle"], "stage": 3},
        )
        text = get_text(response)
        result = extract_json(text)
        result["_stage"] = 3
        return result
    except Exception as e:
        log.warning("Stage 3 error for %s: %s", record["handle"], e)
        return {"_stage": 3, "_error": str(e), "website_verified": None, "website_confidence": 0.0}


def stage4_resolve(client: anthropic.Anthropic, record: dict, stage1_result: dict,
                   stage3_result: dict, uncertain_fields: list, obs: ObservabilityLogger) -> dict:
    """Sonnet: full-context resolution for uncertain/conflicting fields."""
    messages = [{"role": "user", "content": stage4_user_prompt(
        record, stage1_result, stage3_result, uncertain_fields)}]

    try:
        response = client.messages.create(
            model=SONNET_MODEL, max_tokens=400, system=STAGE4_SYSTEM, messages=messages,
        )
        usage = response.usage
        cost = compute_cost(usage.input_tokens, usage.output_tokens, SONNET_MODEL)
        obs.log_call(
            phase="part_4", model=SONNET_MODEL,
            tokens=usage.input_tokens + usage.output_tokens, cost=cost,
            prompt_version="stage4_resolve_v1", outcome="success",
            metadata={"handle": record["handle"], "stage": 4,
                      "uncertain_fields": uncertain_fields},
        )
        text = get_text(response)
        result = extract_json(text)
        result["_stage"] = 4
        return result
    except Exception as e:
        log.warning("Stage 4 error for %s: %s", record["handle"], e)
        return {"_stage": 4, "_error": str(e)}


# ── Per-record orchestration ───────────────────────────────────────────────────

def _is_nan(v: Any) -> bool:
    """True if value is None, NaN, or empty string."""
    if v is None:
        return True
    if isinstance(v, float) and v != v:
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


CONFIDENCE_VERIFY_THRESHOLD = 0.72
CONFIDENCE_ESCALATE_THRESHOLD = 0.60


def enrich_record(record: dict, client: anthropic.Anthropic,
                  obs: ObservabilityLogger) -> dict:
    """Run the cascade for a single record. Returns a flat enrichment dict."""
    now = datetime.now(timezone.utc).isoformat()
    handle = record["handle"]
    poc_condition = record.get("poc_condition", "")

    # ── Stage 0: rules ────────────────────────────────────────────────────────
    stage0 = stage0_rules(record)

    needs_website_search = poc_condition in ("missing_website", "platform_url")
    needs_industry_only = poc_condition == "missing_industry"

    stage1_result: dict = {}
    stage3_result: dict = {}
    stage4_result: dict = {}

    # ── Stage 1 / 1b: extract ─────────────────────────────────────────────────
    if needs_website_search:
        stage1_result = stage1_search(client, record, obs)
    else:
        stage1_result = stage1b_parametric(client, record, obs)

    if stage1_result.get("_error"):
        # Propagate error cleanly
        return _build_output(record, stage0, stage1_result, stage3_result, stage4_result,
                             "error", now, max_stage=stage1_result.get("_stage", 1))

    # ── Stage 2: deterministic industry snap ($0) ─────────────────────────────
    industry_raw = stage1_result.get("industry_raw") or ""
    snapped_industry = snap_industry(industry_raw)
    if snapped_industry:
        stage1_result["industry_snapped"] = snapped_industry
        stage1_result["industry_snap_method"] = "fuzzy"
    elif record.get("industry") and not _is_nan(record.get("industry")):
        stage1_result["industry_snapped"] = record["industry"]
        stage1_result["industry_snap_method"] = "passthrough"
    else:
        stage1_result["industry_snapped"] = None
        stage1_result["industry_snap_method"] = "none"

    # ── Stage 3: website verification (low-confidence records only) ───────────
    candidate_website = normalize_domain(stage1_result.get("candidate_website"))
    w_conf = float(stage1_result.get("website_confidence", 0.0))

    if candidate_website and needs_website_search and w_conf < CONFIDENCE_VERIFY_THRESHOLD:
        stage3_result = stage3_verify(client, record, candidate_website, obs)
        # Upgrade confidence if verification passes
        if stage3_result.get("website_verified") is True:
            verified_conf = float(stage3_result.get("website_confidence", w_conf))
            stage1_result["website_confidence"] = max(w_conf, verified_conf)
        elif stage3_result.get("website_verified") is False:
            stage1_result["website_confidence"] = min(w_conf, 0.45)

    # ── Determine uncertain fields for Stage 4 escalation ────────────────────
    uncertain_fields = []
    final_w_conf = float(stage1_result.get("website_confidence", 0.0))
    final_t_conf = float(stage1_result.get("type_confidence", 0.0))
    final_s_conf = float(stage1_result.get("size_confidence", 0.0))
    final_i_conf = float(stage1_result.get("industry_confidence", 0.0))

    if needs_website_search and candidate_website and final_w_conf < CONFIDENCE_ESCALATE_THRESHOLD:
        uncertain_fields.append("website")
    if candidate_website and stage3_result.get("website_verified") is False:
        if "website" not in uncertain_fields:
            uncertain_fields.append("website")
    if stage1_result.get("candidate_type") and final_t_conf < CONFIDENCE_ESCALATE_THRESHOLD:
        uncertain_fields.append("type")
    # Only escalate size to Sonnet when we have a found website to reason against;
    # without web evidence Sonnet can't do better than Haiku's parametric guess.
    if stage1_result.get("candidate_size") and final_s_conf < CONFIDENCE_ESCALATE_THRESHOLD:
        if candidate_website:
            uncertain_fields.append("size")
    if stage1_result.get("industry_snapped") and final_i_conf < CONFIDENCE_ESCALATE_THRESHOLD:
        uncertain_fields.append("industry")

    # ── Stage 4: Sonnet resolution ────────────────────────────────────────────
    if uncertain_fields:
        stage4_result = stage4_resolve(client, record, stage1_result, stage3_result,
                                       uncertain_fields, obs)

    max_stage = 1
    if stage3_result:
        max_stage = 3
    if stage4_result:
        max_stage = 4

    return _build_output(record, stage0, stage1_result, stage3_result, stage4_result,
                         "completed", now, max_stage)


def _build_output(record: dict, stage0: dict, stage1: dict, stage3: dict, stage4: dict,
                  status: str, enriched_at: str, max_stage: int) -> dict:
    """Assemble the final per-record enrichment dict."""
    handle = record["handle"]

    # Resolve per-field final values (Stage 4 overrides Stage 1)
    def final_val(field_key: str, stage4_key: str) -> Optional[str]:
        if stage4 and stage4.get(stage4_key) and not stage4.get("_error"):
            return stage4[stage4_key]
        return stage1.get(field_key)

    def final_conf(conf_key: str) -> float:
        if stage4 and stage4.get(conf_key) and not stage4.get("_error"):
            return float(stage4[conf_key])
        return float(stage1.get(conf_key, 0.0))

    website_original = stage0.get("website_original")
    website_enriched = normalize_domain(final_val("candidate_website", "website_final"))
    type_enriched = final_val("candidate_type", "type_final")
    size_enriched = final_val("candidate_size", "size_final")
    industry_enriched = stage1.get("industry_snapped")
    if stage4 and stage4.get("industry_final") and not stage4.get("_error"):
        industry_enriched = stage4["industry_final"]

    # Validate enums
    if type_enriched and type_enriched not in TYPE_ENUM:
        type_enriched = None
    if size_enriched and size_enriched not in SIZE_ENUM:
        size_enriched = None

    # website_original_correct: did the pipeline agree with the stored value?
    website_original_domain = normalize_domain(website_original)
    if _is_nan(website_original):
        website_original_correct = None      # was null — no correctness signal
    elif website_enriched and website_original_domain:
        website_original_correct = (website_enriched == website_original_domain)
    else:
        website_original_correct = None

    # Determine pipeline stage for each field
    def field_stage(field: str, enriched_val: Any) -> str:
        if _is_nan(enriched_val):
            return "NO_CANDIDATE"
        if stage4 and not stage4.get("_error") and stage4.get(f"{field}_final"):
            return "sonnet"
        if stage3 and field == "website":
            return "haiku"
        return "haiku" if stage1.get("_search_used") else "haiku_parametric"

    w_conf = final_conf("website_confidence")
    t_conf = final_conf("type_confidence")
    s_conf = final_conf("size_confidence")
    i_conf = final_conf("industry_confidence")

    # Final values: prefer enriched, fall back to original if enriched is null
    type_final = type_enriched or (record.get("type") if not _is_nan(record.get("type")) else None)
    size_final = size_enriched or (record.get("size") if not _is_nan(record.get("size")) else None)
    industry_final = industry_enriched or (record.get("industry") if not _is_nan(record.get("industry")) else None)
    website_final = website_enriched or (website_original_domain if not stage0.get("website_rules_flag") else None)

    # Determine enrichment_status — only count fields that were actually missing and got filled.
    filled = sum([
        website_final is not None and _is_nan(website_original),
        type_final is not None and _is_nan(stage0.get("type_original")),
        size_final is not None and _is_nan(stage0.get("size_original")),
        industry_final is not None and _is_nan(record.get("industry")),
    ])
    if status == "error":
        enrichment_status = "ERROR"
    elif website_enriched and stage3.get("website_verified") is False and not stage4:
        enrichment_status = "CONFLICT"
    elif filled == 0:
        enrichment_status = "NO_CANDIDATE"
    elif filled >= 2:
        enrichment_status = "FULLY_ENRICHED"
    else:
        enrichment_status = "PARTIALLY_ENRICHED"

    return {
        "handle": handle,
        "enriched_at": enriched_at,
        "pipeline_version": PIPELINE_VERSION,
        # Original values
        "website_original": website_original,
        "type_original": stage0.get("type_original"),
        "industry_original": stage0.get("industry_original"),
        "size_original": stage0.get("size_original"),
        # Enriched (candidate) values
        "website_enriched": website_enriched,
        "type_enriched": type_enriched,
        "industry_enriched": industry_enriched,
        "size_enriched": size_enriched,
        # Final write-back values
        "website_final": website_final,
        "type_final": type_final,
        "industry_final": industry_final,
        "size_final": size_final,
        # Data validity audit trail
        "website_original_correct": website_original_correct,
        "type_original_correct": (
            None if _is_nan(record.get("type"))
            else (type_enriched == record.get("type")) if type_enriched else None
        ),
        "industry_original_correct": (
            None if _is_nan(record.get("industry"))
            else (industry_enriched == record.get("industry")) if industry_enriched else None
        ),
        "size_original_correct": (
            None if _is_nan(record.get("size"))
            else (size_enriched == record.get("size")) if size_enriched else None
        ),
        # Confidence scores
        "website_confidence": w_conf,
        "type_confidence": t_conf,
        "industry_confidence": i_conf,
        "size_confidence": s_conf,
        # Pipeline provenance
        "website_pipeline_stage": field_stage("website", website_final),
        "type_pipeline_stage": field_stage("type", type_final),
        "industry_pipeline_stage": field_stage("industry", industry_final),
        "size_pipeline_stage": field_stage("size", size_final),
        # Review flags (medium confidence or conflict)
        "website_review_flag": w_conf < 0.70 and website_enriched is not None,
        "type_review_flag": t_conf < 0.65 and type_enriched is not None,
        "industry_review_flag": i_conf < 0.65 and industry_enriched is not None,
        "size_review_flag": s_conf < 0.55 and size_enriched is not None,
        # Record-level
        "enrichment_status": enrichment_status,
        "stage_resolved": max_stage,
        "status": status,
        # Pass-through fields for eval join
        "poc_segment": record.get("poc_segment"),
        "poc_condition": record.get("poc_condition"),
        "name": record.get("name"),
        "city": record.get("city"),
        "state": record.get("state"),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def run_part4() -> None:
    obs = ObservabilityLogger()

    # Entry gates
    print("=== Part 4 entry gates ===")
    try:
        enforce(check_part4_entry(), "part4_entry")
    except GateFailure as e:
        log.error(str(e))
        sys.exit(1)

    # Load batch
    con = duckdb.connect()
    rows = con.execute(f"SELECT * FROM parquet_scan('{BATCH_PATH}')").df()
    records = rows.to_dict("records")
    log.info("Loaded %d records from %s", len(records), BATCH_PATH)

    # Batch quality gate
    print("\n=== Batch quality gates ===")
    try:
        enforce(check_batch_quality(BATCH_PATH), "batch_quality")
    except GateFailure as e:
        log.error(str(e))
        sys.exit(1)

    client = anthropic.Anthropic()
    results = []
    budget_exhausted_at: Optional[int] = None

    for i, record in enumerate(records):
        # Budget check before every LLM call
        spent = obs.get_phase_cost("part_4")
        if spent >= PART4_BUDGET:
            log.warning("Part 4 budget exhausted at record %d/%d ($%.4f)", i, len(records), spent)
            budget_exhausted_at = i
            # Mark remaining records
            for rem in records[i:]:
                results.append({
                    "handle": rem["handle"],
                    "enriched_at": datetime.now(timezone.utc).isoformat(),
                    "pipeline_version": PIPELINE_VERSION,
                    "status": "budget_exhausted",
                    "enrichment_status": "NO_CANDIDATE",
                    "stage_resolved": 0,
                    "poc_segment": rem.get("poc_segment"),
                    "poc_condition": rem.get("poc_condition"),
                    "name": rem.get("name"),
                    "city": rem.get("city"),
                    "state": rem.get("state"),
                })
            break

        log.info("[%d/%d] %s — %s", i + 1, len(records), record.get("handle", "?"),
                 record.get("poc_condition", "?"))

        enriched = enrich_record(record, client, obs)
        results.append(enriched)

        # Micro-delay to avoid rate limits
        time.sleep(0.10)

    # Write output parquet via DuckDB
    import pandas as pd
    out_df = pd.DataFrame(results)

    Path(ENRICHED_PATH).parent.mkdir(parents=True, exist_ok=True)
    out_con = duckdb.connect()
    out_con.register("enriched_df", out_df)
    out_con.execute(f"COPY enriched_df TO '{ENRICHED_PATH}' (FORMAT PARQUET)")

    total_spent = obs.get_phase_cost("part_4")
    log.info("Part 4 complete. %d records written. Cost: $%.4f / $%.2f budget.",
             len(results), total_spent, PART4_BUDGET)

    if budget_exhausted_at is not None:
        log.warning("Budget exhausted at record %d. %d records marked budget_exhausted.",
                    budget_exhausted_at, len(records) - budget_exhausted_at)

    # Cascade health gates
    print("\n=== Cascade health gates ===")
    try:
        enforce(check_cascade_health(ENRICHED_PATH), "cascade_health")
    except GateFailure as e:
        log.error("Cascade health: %s", e)


if __name__ == "__main__":
    run_part4()
