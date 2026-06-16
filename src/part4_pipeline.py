"""
Part 4 PoC enrichment pipeline (v2).

Cascade:
  Stage 0  — Rules ($0): platform URL detection + name-suffix type inference + TLD signals
  Stage 1  — Haiku + web_search: find website, extract type/size/industry + NAICS code
  Stage 1b — Haiku parametric: classify industry for records that already have a website
  Stage 1.5— Haiku entity gate (conditional): MATCH / SUBSIDIARY / PARENT / NO_MATCH
  Stage 1.6— Haiku + web_search retry with refined query (SUBSIDIARY/PARENT only)
  Stage 2  — Deterministic industry snap ($0): NAICS-filtered cosine-similarity label match
  Stage 3  — Haiku verify: confirm candidate website matches company (low-confidence only)
  Stage 3b — Haiku size search: targeted site:linkedin.com/company query for low-conf size
  Stage 3c — Haiku closure verify: web search for operating status when Stage 1b returns null
  Stage 4  — Sonnet resolution: resolve conflicts/uncertain fields

State machine per record:
  Stage 0 entity_confirmed → skip entity gate, use inferred type/industry directly
  Stage 1 → Stage 1.5 gate (conditional) → SUBSIDIARY/PARENT: retry (Stage 1.6)
  Stage 1.5 NO_MATCH → return NO_CANDIDATE immediately
  Stage 1/1b low-conf website → Stage 3 (verify)
  Stage 1/1b low-conf size → Stage 3b (targeted size search)
  Any field uncertain after Stage 3 → Stage 4 (Sonnet)
  Budget hit → status=budget_exhausted for remaining records
"""

import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

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
PIPELINE_VERSION = "v2"

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

# ── Stage 0 name-suffix and TLD signals ───────────────────────────────────────
# Accuracy figures from empirical validation against 4.16M records (strategy doc).
# HIGH (≥0.85 after LLP/ISD adjustment) → entity_confirmed=True, apply as NULL-FILL only.
_NAME_TYPE_HIGH: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r'\bCity of\b', re.I),                                         'Government Agency', 0.93),
    (re.compile(r'\bSchool District\b', re.I),                                 'Educational',       0.91),
    (re.compile(r'\bCounty of\b', re.I),                                       'Government Agency', 0.88),
    (re.compile(r'\bFoundation\b', re.I),                                      'Nonprofit',         0.92),
    (re.compile(r'\b(?:Church|Ministry|Ministries)\b', re.I),                  'Nonprofit',         0.88),
    (re.compile(r'\b(?:Fire Department|Fire Dept|Police Department)\b', re.I), 'Government Agency', 0.82),
    (re.compile(r'\bLLP\b'),                                                   'Partnership',       0.76),
    (re.compile(r'\b(?:ISD|USD|CUSD)\b'),                                      'Educational',       0.79),
]
# MEDIUM (0.63–0.73) → apply but entity_confirmed=False
_NAME_TYPE_MEDIUM: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r'\bInc\.?\b', re.I),                  'Privately Held',    0.73),
    (re.compile(r'\bCorp\.?\b', re.I),                 'Privately Held',    0.72),
    (re.compile(r'\b(?:University|College)\b', re.I),  'Educational',       0.65),
    (re.compile(r'\bTownship\b', re.I),                'Government Agency', 0.63),
]
# US .gov/.edu/.mil: 0 records in dataset — dead patterns, intentionally omitted.
# .k12.XX.us: 5,129 records, 100% genuine K-12 (n=20 verified).
_K12_TLD_RE = re.compile(r'\.k12\.[a-z]{2}\.us$', re.I)
# Foreign .gov.<cc>: ~290 corruption artifacts — flag website, do NOT infer type.
_FOREIGN_GOV_RE = re.compile(r'\.gov\.[a-z]{2}$', re.I)

# ── NAICS 2-digit → LinkedIn label subsets (for embeddings-based industry snap) ─
NAICS_SECTORS: dict[int, list[str]] = {
    11: ["farming", "farming, ranching, forestry", "ranching", "ranching and fisheries",
         "fisheries", "horticulture", "forestry and logging", "animal feed manufacturing",
         "agricultural chemical manufacturing"],
    21: ["mining", "coal mining", "metal ore mining", "nonmetallic mineral mining",
         "oil and gas", "oil extraction", "natural gas extraction", "oil, gas, and mining",
         "oil and coal product manufacturing"],
    22: ["utilities", "utilities administration", "electric power generation",
         "natural gas distribution", "hydroelectric power generation",
         "nuclear electric power generation", "fossil fuel electric power generation",
         "biomass electric power generation", "geothermal electric power generation",
         "solar electric power generation", "wind electric power generation",
         "water supply and irrigation systems", "steam and air-conditioning supply",
         "water, waste, steam, and air conditioning services",
         "renewable energy power generation", "services for renewable energy"],
    23: ["construction", "building construction", "nonresidential building construction",
         "residential building construction", "highway, street, and bridge construction",
         "utility system construction", "specialty trade contractors",
         "building equipment contractors", "building finishing contractors",
         "building structure and exterior contractors", "civil engineering",
         "subdivision of land", "architecture and planning"],
    31: ["food production", "food and beverage manufacturing", "baked goods manufacturing",
         "dairy product manufacturing", "meat products manufacturing",
         "fruit and vegetable preserves manufacturing", "seafood product manufacturing",
         "sugar and confectionery product manufacturing", "beverage manufacturing",
         "breweries", "wineries", "distilleries", "tobacco manufacturing",
         "textile manufacturing", "apparel manufacturing", "footwear manufacturing",
         "leather product manufacturing", "wood product manufacturing",
         "paper and forest product manufacturing", "printing services",
         "petroleum and coal products manufacturing"],
    32: ["chemical manufacturing", "chemical raw materials manufacturing",
         "pharmaceutical manufacturing", "soap and cleaning product manufacturing",
         "paint, coating, and adhesive manufacturing", "plastics manufacturing",
         "plastics and rubber product manufacturing", "rubber products manufacturing",
         "glass product manufacturing", "glass, ceramics and concrete manufacturing",
         "clay and refractory products manufacturing",
         "lime and gypsum products manufacturing", "abrasives and nonmetallic minerals manufacturing",
         "primary metal manufacturing", "fabricated metal products",
         "cutlery and handtool manufacturing", "architectural and structural metal manufacturing",
         "boilers, tanks, and shipping container manufacturing",
         "metal valve, ball, and roller manufacturing", "spring and wire product manufacturing",
         "turned products and fastener manufacturing", "metalworking machinery manufacturing",
         "construction hardware manufacturing", "metal treatments"],
    33: ["machinery manufacturing", "industrial machinery manufacturing",
         "automation machinery manufacturing", "agriculture, construction, mining machinery manufacturing",
         "commercial and service industry machinery manufacturing",
         "engines and power transmission equipment manufacturing",
         "hvac and refrigeration equipment manufacturing",
         "household appliance manufacturing", "electric lighting equipment manufacturing",
         "electrical equipment manufacturing",
         "appliances, electrical, and electronics manufacturing",
         "communications equipment manufacturing", "computer hardware manufacturing",
         "computer hardware", "semiconductor manufacturing", "semiconductors",
         "electronic and precision equipment maintenance",
         "measuring and control instrument manufacturing",
         "magnetic and optical media manufacturing",
         "motor vehicle manufacturing", "motor vehicle parts manufacturing",
         "aviation and aerospace component manufacturing", "shipbuilding",
         "railroad equipment manufacturing", "transportation equipment manufacturing",
         "furniture and home furnishings manufacturing",
         "household and institutional furniture manufacturing",
         "office furniture and fixtures manufacturing",
         "mattress and blinds manufacturing",
         "defense and space manufacturing", "robot manufacturing", "robotics engineering",
         "nanotechnology research", "smart meter manufacturing",
         "renewable energy equipment manufacturing",
         "renewable energy semiconductor manufacturing", "fuel cell manufacturing",
         "audio and video equipment manufacturing",
         "computers and electronics manufacturing", "consumer electronics",
         "artificial rubber and synthetic fiber manufacturing",
         "packaging and containers manufacturing"],
    42: ["wholesale", "wholesale food and beverage", "wholesale alcoholic beverages",
         "wholesale raw farm products", "wholesale chemical and allied products",
         "wholesale drugs and sundries", "wholesale apparel and sewing supplies",
         "wholesale furniture and home furnishings", "wholesale building materials",
         "wholesale hardware, plumbing, heating equipment", "wholesale machinery",
         "wholesale computer equipment", "wholesale electronics",
         "wholesale appliances, electrical, and electronics",
         "wholesale motor vehicles and parts", "wholesale metals and minerals",
         "wholesale petroleum and petroleum products", "wholesale paper products",
         "wholesale footwear", "wholesale luxury goods and jewelry",
         "wholesale recyclable materials", "wholesale import and export",
         "wholesale photography equipment and supplies"],
    44: ["retail", "food and beverage retail", "retail groceries", "retail pharmacies",
         "retail health and personal care products", "retail gasoline",
         "retail motor vehicles", "retail building materials and garden equipment",
         "retail furniture and home furnishings", "retail appliances, electrical, and electronic equipment",
         "retail apparel and fashion", "retail luxury goods and jewelry",
         "retail books and printed news", "retail office supplies and gifts",
         "retail office equipment", "retail musical instruments", "retail florists",
         "retail art dealers", "retail art supplies",
         "retail recyclable materials & used merchandise",
         "online and mail order retail", "consumer goods"],
    48: ["truck transportation", "maritime transportation", "rail transportation",
         "pipeline transportation", "ground passenger transportation",
         "air, water, and waste program management", "airlines and aviation",
         "freight and package transportation", "sightseeing transportation",
         "interurban and rural bus services", "school and employee bus services",
         "shuttles and special needs transportation services",
         "taxi and limousine services", "urban transit services",
         "postal services", "maritime"],
    49: ["transportation, logistics, supply chain and storage",
         "warehousing and storage", "warehousing",
         "transportation/trucking/railroad", "transportation programs"],
    51: ["software development", "technology, information and internet",
         "technology, information and media", "internet publishing",
         "online media", "internet news", "internet marketplace platforms",
         "social networking platforms", "broadcast media production and distribution",
         "cable and satellite programming", "radio and television broadcasting",
         "online audio and video media", "movies and sound recording",
         "movies, videos, and sound", "sound recording", "music", "musicians",
         "book publishing", "book and periodical publishing", "newspaper publishing",
         "periodical publishing", "sheet music publishing", "blogs",
         "information services", "data infrastructure and analytics",
         "business intelligence platforms", "blockchain services",
         "satellite telecommunications", "telecommunications",
         "telecommunications carriers", "wireless services",
         "media and telecommunications", "media production"],
    52: ["banking", "investment banking", "capital markets", "investment management",
         "investment advice", "financial services", "insurance",
         "insurance carriers", "insurance agencies and brokerages",
         "insurance and employee benefit funds",
         "claims adjusting, actuarial services", "securities and commodity exchanges",
         "funds and trusts", "pension funds", "trusts and estates",
         "savings institutions", "loan brokers", "credit intermediation",
         "venture capital and private equity principals"],
    53: ["real estate", "commercial real estate", "real estate agents and brokers",
         "leasing residential real estate", "leasing non-residential real estate",
         "real estate and equipment rental services",
         "commercial and industrial equipment rental",
         "equipment rental services", "consumer goods rental"],
    54: ["law practice", "legal services", "accounting",
         "architecture and planning", "engineering services",
         "mechanical or industrial engineering", "civil engineering",
         "research", "research services", "biotechnology research",
         "nanotechnology research", "space research and technology",
         "market research", "advertising services", "marketing services",
         "public relations and communications services",
         "design services", "design", "graphic design", "interior design",
         "photography", "translation and localization",
         "veterinary services", "veterinary",
         "professional training and coaching", "professional services",
         "management consulting", "operations consulting",
         "strategic management services", "business consulting and services",
         "executive search services", "think tanks",
         "alternative dispute resolution", "surveying and mapping services",
         "climate data and analytics"],
    55: ["holding companies", "funds and trusts"],
    56: ["staffing and recruiting", "temporary help services",
         "security and investigations", "security guards and patrol services",
         "security systems services", "janitorial services",
         "landscaping services", "facilities services",
         "administrative and support services", "office administration",
         "collection agencies", "travel arrangements",
         "pest control", "telephone call centers"],
    61: ["primary and secondary education", "higher education",
         "education administration programs", "education management",
         "e-learning", "e-learning providers", "technical and vocational training",
         "cosmetology and barber schools", "fine arts schools", "language schools",
         "flight training", "sports and recreation instruction",
         "professional training and coaching", "vocational rehabilitation services",
         "education"],
    62: ["hospitals and health care", "hospitals", "medical practices",
         "mental health care", "outpatient care centers",
         "medical and diagnostic laboratories", "home health care services",
         "nursing homes and residential care facilities",
         "individual and family services", "emergency and relief services",
         "services for the elderly and disabled", "child day care services",
         "family planning centers", "public health",
         "ambulance services", "physicians", "dentists", "chiropractors",
         "optometrists", "physical, occupational and speech therapists",
         "alternative medicine", "medical device", "medical equipment manufacturing",
         "pharmaceutical manufacturing", "biotechnology", "health and human services",
         "health, wellness & fitness", "wellness and fitness services"],
    71: ["performing arts", "performing arts and spectator sports",
         "spectator sports", "sports teams and clubs", "museums",
         "museums, historical sites, and zoos", "historical sites",
         "amusement parks and arcades", "gambling facilities and casinos",
         "golf courses and country clubs", "skiing facilities", "racetracks",
         "zoos and botanical gardens", "recreational facilities",
         "dance companies", "theater companies", "circuses and magic shows",
         "artists and writers", "fine art", "music", "animation",
         "animation and post-production", "entertainment providers",
         "entertainment", "spectator sports", "computer games",
         "mobile gaming apps"],
    72: ["restaurants", "hospitality", "hotels and motels",
         "bars, taverns, and nightclubs", "bed-and-breakfasts, hostels, homestays",
         "food and beverage services", "caterers", "mobile food services",
         "accommodation and food services", "leisure, travel & tourism",
         "food & beverages"],
    81: ["repair and maintenance", "vehicle repair and maintenance",
         "electronic and precision equipment maintenance",
         "footwear and leather goods repair", "reupholstery and furniture repair",
         "commercial and industrial machinery maintenance",
         "religious institutions", "civic and social organizations",
         "professional organizations", "industry associations",
         "political organizations", "philanthropy", "fundraising",
         "philanthropic fundraising services", "non-profit organizations",
         "non-profit organization management", "community services",
         "personal care services", "laundry and drycleaning services",
         "household services", "pet services", "funeral services",
         "sports and recreation instruction", "arts & crafts"],
    92: ["government administration", "executive offices", "legislative offices",
         "courts of law", "law enforcement", "correctional institutions",
         "fire protection", "public safety", "administration of justice",
         "military and international affairs", "armed forces",
         "international affairs", "international trade and development",
         "economic programs", "housing programs",
         "community development and urban planning",
         "environmental quality programs", "air, water, and waste program management",
         "conservation programs", "transportation programs",
         "utilities administration", "housing and community development",
         "public assistance programs", "public policy", "public policy offices",
         "public health", "health and human services",
         "government relations", "government relations services"],
}

# ── Lazy-initialised sentence-transformer (loaded once at first snap_industry call) ─
_ST_MODEL: Any = None
_ST_LABEL_EMBEDDINGS: Any = None

def _get_embeddings():
    """Lazy-initialise the sentence-transformer model and pre-encode all 492 labels."""
    global _ST_MODEL, _ST_LABEL_EMBEDDINGS
    if _ST_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            _ST_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            _ST_LABEL_EMBEDDINGS = _ST_MODEL.encode(INDUSTRY_LABELS, convert_to_numpy=True)
            log.info("sentence-transformers model loaded; %d labels encoded", len(INDUSTRY_LABELS))
        except ImportError:
            log.warning("sentence-transformers not installed — falling back to difflib for industry snap")
            _ST_MODEL = "unavailable"
    return _ST_MODEL, _ST_LABEL_EMBEDDINGS

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


def snap_industry(raw: Optional[str], naics_code: Optional[int] = None) -> Optional[str]:
    """Map a free-text industry description to the closest canonical label.

    Args:
        raw: Free-text industry description from Stage 1 model output.
        naics_code: Optional NAICS 2-digit sector code from Stage 1. When provided,
            the cosine-similarity search is restricted to that sector's label subset,
            eliminating cross-sector sibling-label confusion.
    """
    if not raw or not raw.strip():
        return None
    raw_lower = raw.lower().strip()

    # Exact match
    if raw_lower in INDUSTRY_LABELS:
        return raw_lower

    # Exact prefix containment
    for label in INDUSTRY_LABELS:
        if label.startswith(raw_lower + " ") or label == raw_lower:
            return label

    # Priority keyword lookup (fast, no model needed)
    raw_words = [w for w in re.split(r"[\s,&/\-]+", raw_lower) if w and w not in _STOP_WORDS]
    raw_word_set = set(raw_words)
    if not raw_word_set:
        return None

    for keyword_set, label in _KEYWORD_MAP:
        if keyword_set & raw_word_set:
            return label

    # Embeddings-based cosine similarity (sector-filtered when NAICS code provided)
    model, all_embeddings = _get_embeddings()
    if model and model != "unavailable":
        import numpy as np
        # Determine candidate label set
        if naics_code and naics_code in NAICS_SECTORS:
            candidate_labels = NAICS_SECTORS[naics_code]
            candidate_indices = [INDUSTRY_LABELS.index(l) for l in candidate_labels
                                 if l in INDUSTRY_LABELS]
            candidate_embeddings = all_embeddings[candidate_indices]
        else:
            candidate_labels = INDUSTRY_LABELS
            candidate_indices = list(range(len(INDUSTRY_LABELS)))
            candidate_embeddings = all_embeddings

        query_emb = model.encode([raw_lower], convert_to_numpy=True)
        # Cosine similarity: dot product of L2-normalised vectors
        q_norm = query_emb / (np.linalg.norm(query_emb, axis=1, keepdims=True) + 1e-9)
        c_norms = candidate_embeddings / (np.linalg.norm(candidate_embeddings, axis=1, keepdims=True) + 1e-9)
        sims = (q_norm @ c_norms.T).flatten()
        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])
        if best_score >= 0.40:
            return candidate_labels[best_idx]
        # If sector search found nothing good, widen to full label set
        if naics_code and naics_code in NAICS_SECTORS:
            q_norm_all = q_norm
            c_norms_all = all_embeddings / (np.linalg.norm(all_embeddings, axis=1, keepdims=True) + 1e-9)
            sims_all = (q_norm_all @ c_norms_all.T).flatten()
            best_idx_all = int(np.argmax(sims_all))
            if float(sims_all[best_idx_all]) >= 0.40:
                return INDUSTRY_LABELS[best_idx_all]
        return None

    # Fallback: word-overlap F1 scoring (no model available)
    import difflib as _difflib
    best_score, best_match = 0.0, None
    for label in INDUSTRY_LABELS:
        label_words = set(re.split(r"[\s,&/]+", label)) - _STOP_WORDS
        if not label_words:
            continue
        hits = sum(1 for w in raw_word_set if w in label_words or any(w in lw for lw in label_words))
        precision = hits / len(raw_word_set)
        recall = hits / len(label_words) if label_words else 0.0
        score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        if score > best_score:
            best_score, best_match = score, label
    if best_score >= 0.35:
        return best_match
    matches = _difflib.get_close_matches(raw_lower, INDUSTRY_LABELS, n=1, cutoff=0.45)
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

def stage1_user_prompt(name: str, city: str, state: str, existing_website: Optional[str],
                        refined_exclude: Optional[str] = None) -> str:
    website_line = (
        f"Current website in database (possibly wrong/outdated): {existing_website}"
        if existing_website
        else "No website on record."
    )
    exclude_line = (
        f"\nIMPORTANT: Do NOT return results for '{refined_exclude}' — find the specific entity '{name}' instead."
        if refined_exclude
        else ""
    )
    return f"""\
Find accurate information for this company using web search.

Company: {name}
Location: {city}, {state}
{website_line}{exclude_line}

Search for this company and return ONLY this JSON:
{{
  "extracted_name": "Exact name of the entity found in search results",
  "candidate_website": "domain.com",
  "candidate_type": "Privately Held",
  "is_single_facility": true,
  "candidate_size": "51-200",
  "naics_2digit": 54,
  "industry_raw": "commercial heating and cooling services",
  "website_confidence": 0.85,
  "type_confidence": 0.7,
  "size_confidence": 0.6,
  "industry_confidence": 0.8,
  "still_operating": true,
  "closure_signals": [],
  "reasoning": "one sentence"
}}

Rules:
- extracted_name: the exact legal/official name found in search results (not the query name).
- candidate_website: bare domain only (no https://, no www., no path). null if not found.
- candidate_type must be exactly one of: {", ".join(TYPE_ENUM)}
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
  Size bands: 1-10, 11-50, 51-200, 201-500, 501-1K (501–1000), 1K-5K (1001–5000), 5K-10K (5001–10000), 10K+ (over 10000).
  Must be exactly one of: {", ".join(SIZE_ENUM)}
- naics_2digit: the NAICS 2-digit sector code (integer) that best describes the primary business.
  Common codes: 11=Agriculture, 21=Mining, 22=Utilities, 23=Construction, 31-33=Manufacturing,
  42=Wholesale, 44-45=Retail, 48-49=Transportation, 51=Information/Media, 52=Finance,
  53=Real Estate, 54=Professional Services, 56=Admin/Support, 61=Education, 62=Healthcare,
  71=Arts/Entertainment, 72=Accommodation/Food, 81=Other Services, 92=Government.
- industry_raw: 2-4 words describing the primary business. null if unclear.
- still_operating: true if search results show a current website, recent activity, or active LinkedIn page.
  false if results mention "out of business", "permanently closed", "ceased operations", domain expired/for sale,
  Google Maps shows "Permanently closed", or no substantive business results exist. null if you cannot determine.
- closure_signals: array of zero or more matching signals: "no_results", "domain_expired", "website_404",
  "closed_announcement", "domain_for_sale", "permanently_closed", "acquired".
  Use "permanently_closed" when Google Maps or a directory explicitly labels the location as permanently closed.
  Use "acquired" when the company was bought by another entity — set still_operating=null since the acquiring
  entity may still operate under the same name (requires human review).
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
  "is_single_facility": true,
  "candidate_size": "51-200",
  "naics_2digit": 54,
  "industry_raw": "commercial heating and cooling services",
  "type_confidence": 0.6,
  "size_confidence": 0.5,
  "industry_confidence": 0.75,
  "still_operating": true,
  "closure_signals": [],
  "reasoning": "one sentence"
}}

Rules:
- candidate_type must be exactly one of: {", ".join(TYPE_ENUM)}
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
  Must be exactly one of: {", ".join(SIZE_ENUM)}
- naics_2digit: NAICS 2-digit sector code (integer). null if unclear.
- industry_raw: 2-4 words describing the primary business. null if unclear.
- still_operating: true if the company appears active based on name/location/website signals.
  false if search results or the website indicate closure — including Google Maps "Permanently closed",
  "out of business", "ceased operations", or domain expired/for sale. null if uncertain.
- closure_signals: array of matching signals (may be empty): "no_results", "domain_expired",
  "website_404", "closed_announcement", "domain_for_sale", "permanently_closed", "acquired".
  Use "permanently_closed" when Google Maps or a directory explicitly labels the location as permanently closed.
  Use "acquired" when the company was bought by another entity — set still_operating=null since the acquiring
  entity may still operate under the same name (requires human review).
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
    """Deterministic rules. Expands original v1 (platform URL detection) with:
      - name-suffix type inference (City of, Foundation, LLP, etc.)
      - .k12.XX.us TLD → type=Educational + industry confirmed
      - foreign .gov.<cc> → website_corrupted flag
    Returns entity_confirmed=True when a deterministic signal anchors the entity,
    allowing downstream code to skip the entity verification gate.
    """
    out: dict[str, Any] = {}
    website = record.get("website")
    name = record.get("name") or ""
    out["website_original"] = website
    out["type_original"] = record.get("type")
    out["industry_original"] = record.get("industry")
    out["size_original"] = record.get("size")

    # Platform / institutional URL detection (unchanged from v1)
    if is_platform_url(website):
        out["website_rules_flag"] = True
        out["website_pipeline_stage"] = "rules_flagged"
    else:
        out["website_rules_flag"] = False
        out["website_pipeline_stage"] = "rules_passthrough"

    # Foreign .gov.<cc> corruption artifact — flag, do not infer type from it
    domain = normalize_domain(website) or ""
    if _FOREIGN_GOV_RE.search(domain):
        out["website_corrupted"] = True
        out["website_rules_flag"] = True  # treat as missing for enrichment
    else:
        out["website_corrupted"] = False

    # .k12.XX.us TLD → entity confirmed as K-12 school district
    if _K12_TLD_RE.search(domain):
        out["type_inferred"] = "Educational"
        out["type_inferred_confidence"] = 0.95
        out["industry_inferred"] = "primary and secondary education"
        out["entity_confirmed"] = True
        return out

    # Name-suffix patterns — NULL-FILL ONLY (do not override existing type)
    out["type_inferred"] = None
    out["type_inferred_confidence"] = 0.0
    out["industry_inferred"] = None
    out["entity_confirmed"] = False

    for pattern, type_val, confidence in _NAME_TYPE_HIGH:
        if pattern.search(name):
            out["type_inferred"] = type_val
            out["type_inferred_confidence"] = confidence
            out["entity_confirmed"] = True
            return out

    for pattern, type_val, confidence in _NAME_TYPE_MEDIUM:
        if pattern.search(name):
            out["type_inferred"] = type_val
            out["type_inferred_confidence"] = confidence
            # entity_confirmed stays False for medium-confidence patterns
            return out

    return out


def stage1_search(client: anthropic.Anthropic, record: dict, obs: ObservabilityLogger,
                  refined_exclude: Optional[str] = None) -> dict:
    """Haiku + web_search: find website, extract type/size/industry for missing/platform records.

    Args:
        refined_exclude: When set (SUBSIDIARY/PARENT retry), the entity name to exclude from
            results to force the search to find the specific sub-entity.
    """
    name = record["name"] or ""
    city = record.get("city") or ""
    state = record.get("state") or ""
    existing_website = record.get("website") if record.get("poc_condition") == "platform_url" else None
    stage_label = "1.6" if refined_exclude else "1"
    prompt_ver = "stage1_search_v3_refined" if refined_exclude else "stage1_search_v3"

    messages = [{"role": "user", "content": stage1_user_prompt(
        name, city, state, existing_website, refined_exclude=refined_exclude)}]

    try:
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=600,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
            system=STAGE1_SYSTEM,
            messages=messages,
        )
        usage = response.usage
        cost = compute_cost(usage.input_tokens, usage.output_tokens, HAIKU_MODEL)
        text = get_text(response)
        obs.log_call(
            phase="part_4", model=HAIKU_MODEL,
            tokens=usage.input_tokens + usage.output_tokens, cost=cost,
            prompt_version=prompt_ver, outcome="success",
            metadata={"handle": record["handle"], "stage": stage_label, "raw_response": text},
        )
        result = extract_json(text)
        result["_stage"] = stage_label
        result["_search_used"] = True
        return result
    except Exception as e:
        log.warning("Stage 1 error for %s: %s", record["handle"], e)
        return {"_stage": stage_label, "_search_used": True, "_error": str(e)}


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
        text = get_text(response)
        obs.log_call(
            phase="part_4", model=HAIKU_MODEL,
            tokens=usage.input_tokens + usage.output_tokens, cost=cost,
            prompt_version="stage1b_parametric_v2", outcome="success",
            metadata={"handle": record["handle"], "stage": "1b", "raw_response": text},
        )
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
        text = get_text(response)
        obs.log_call(
            phase="part_4", model=HAIKU_MODEL,
            tokens=usage.input_tokens + usage.output_tokens, cost=cost,
            prompt_version="stage3_verify_v1", outcome="success",
            metadata={"handle": record["handle"], "stage": 3, "raw_response": text},
        )
        result = extract_json(text)
        result["_stage"] = 3
        return result
    except Exception as e:
        log.warning("Stage 3 error for %s: %s", record["handle"], e)
        return {"_stage": 3, "_error": str(e), "website_verified": None, "website_confidence": 0.0}


STAGE15_SYSTEM = """\
You are an entity disambiguation assistant. Determine whether a web search result describes \
the same legal entity as the query. Return ONLY a JSON object."""

def stage1_5_entity_gate(client: anthropic.Anthropic, record: dict, stage1_result: dict,
                          obs: ObservabilityLogger) -> dict:
    """Haiku (no search): verify the entity found in Stage 1 matches the input record.

    Returns {"entity_verdict": "MATCH|SUBSIDIARY|PARENT|NO_MATCH", "gate_reasoning": "..."}
    """
    name = record.get("name") or ""
    state = record.get("state") or ""
    extracted = stage1_result.get("extracted_name") or stage1_result.get("candidate_website") or "unknown"

    prompt = f"""\
You searched for: "{name}", {state}, USA.
The top search result describes: "{extracted}".

Are these the same legal entity (not just the same organisation family)?

Answer with EXACTLY one of:
  MATCH        — same legal entity (e.g. "Portland City Hall" found for "City of Portland")
  SUBSIDIARY   — found entity is a subsidiary/branch of the searched entity
  PARENT       — found entity is the parent/umbrella of the searched entity (e.g. health system vs specific hospital)
  NO_MATCH     — different company entirely

Return ONLY this JSON:
{{
  "entity_verdict": "MATCH",
  "gate_reasoning": "one sentence explaining your decision"
}}"""

    try:
        response = client.messages.create(
            model=HAIKU_MODEL, max_tokens=150, system=STAGE15_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = response.usage
        cost = compute_cost(usage.input_tokens, usage.output_tokens, HAIKU_MODEL)
        text = get_text(response)
        obs.log_call(
            phase="part_4", model=HAIKU_MODEL,
            tokens=usage.input_tokens + usage.output_tokens, cost=cost,
            prompt_version="stage15_entity_gate_v1", outcome="success",
            metadata={"handle": record["handle"], "stage": "1.5",
                      "extracted_name": extracted, "raw_response": text},
        )
        result = extract_json(text)
        result.setdefault("entity_verdict", "MATCH")  # default safe: proceed
        return result
    except Exception as e:
        log.warning("Stage 1.5 error for %s: %s", record["handle"], e)
        return {"entity_verdict": "MATCH", "gate_reasoning": f"gate error: {e}"}


def needs_entity_gate(record: dict, stage0: dict, stage1: dict) -> bool:
    """Return True if Stage 1.5 entity verification should fire."""
    # Nothing useful found — nothing to gate
    if not stage1.get("candidate_website") and not stage1.get("candidate_type"):
        return False
    # Stage 0 already anchored entity via TLD or high-confidence name pattern
    if stage0.get("entity_confirmed"):
        return False
    # Corrupted website — skip gate, website already flagged
    if stage0.get("website_corrupted"):
        return False
    # Large org — parent/subsidiary headcount bleed is common
    if record.get("size") in ("1K-5K", "5K-10K", "10K+"):
        return True
    # Extracted name diverges from input (entity mismatch signal)
    extracted = stage1.get("extracted_name") or ""
    if extracted:
        import difflib as _dl
        ratio = _dl.SequenceMatcher(None,
                                     (record.get("name") or "").lower(),
                                     extracted.lower()).ratio()
        if ratio < 0.70:
            return True
    # Domain concordance — existing valid website matches candidate → entity anchored
    existing = normalize_domain(record.get("website"))
    candidate = normalize_domain(stage1.get("candidate_website"))
    if (existing and candidate and not is_platform_url(record.get("website", ""))
            and existing.split(".")[0] == candidate.split(".")[0]):
        return False
    # Default: run the gate
    return True


STAGE3B_SYSTEM = """\
You are a company size lookup assistant. Use web search to find the employee count \
for the specific company entity provided. Return ONLY a JSON object."""

def stage3b_size_search(client: anthropic.Anthropic, record: dict, obs: ObservabilityLogger) -> dict:
    """Haiku + targeted web_search: find entity-specific employee count.

    Uses site:linkedin.com/company and structured data sources to avoid corporate-wide
    headcount bleed that afflicts general search results.
    """
    name = record.get("name") or ""
    state = record.get("state") or ""

    prompt = f"""\
Find the employee count for this specific company entity (not its parent or subsidiaries).

Company: {name}
State: {state}

Search for "{name}" {state} employees site:linkedin.com/company OR site:craft.co OR site:dnb.com

Return ONLY this JSON:
{{
  "candidate_size": "51-200",
  "size_confidence": 0.75,
  "size_source": "linkedin.com/company/acme-corp",
  "reasoning": "LinkedIn company page shows 150 employees"
}}

Rules:
- candidate_size must be exactly one of: {", ".join(SIZE_ENUM)}
- Prefer location-specific or entity-specific headcount over corporate totals.
- If ONLY a parent org total is found (not this specific entity), set candidate_size=null.
- size_confidence: 0.0 = no evidence, 1.0 = certain structured data from authoritative source."""

    try:
        response = client.messages.create(
            model=HAIKU_MODEL, max_tokens=200,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}],
            system=STAGE3B_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = response.usage
        cost = compute_cost(usage.input_tokens, usage.output_tokens, HAIKU_MODEL)
        text = get_text(response)
        obs.log_call(
            phase="part_4", model=HAIKU_MODEL,
            tokens=usage.input_tokens + usage.output_tokens, cost=cost,
            prompt_version="stage3b_size_search_v1", outcome="success",
            metadata={"handle": record["handle"], "stage": "3b", "raw_response": text},
        )
        result = extract_json(text)
        result["_stage"] = "3b"
        return result
    except Exception as e:
        log.warning("Stage 3b error for %s: %s", record["handle"], e)
        return {"_stage": "3b", "_error": str(e)}


STAGE3C_SYSTEM = """\
You are a business closure verification assistant. Use web search to determine whether \
a company is still operating. Return ONLY a JSON object."""


def stage3c_closure_verify(client: anthropic.Anthropic, record: dict,
                           obs: ObservabilityLogger) -> dict:
    """Haiku + web_search: verify operating status when Stage 1b returned still_operating=null.

    Targeted search for bankruptcy filings, closure announcements, and Google Maps status.
    Only called when parametric classification couldn't determine operating status.
    """
    name = record.get("name") or ""
    city = record.get("city") or ""
    state = record.get("state") or ""

    prompt = f"""\
Search the web to determine if this company is still operating.

Company: {name}
Location: {city}, {state}

Search for: "{name}" "{state}" (closed OR "permanently closed" OR bankruptcy OR \
"ceased operations" OR "out of business")

Return ONLY this JSON:
{{
  "still_operating": true,
  "closure_signals": [],
  "reasoning": "one sentence"
}}

Rules:
- still_operating: true if active. false if results show "permanently closed", \
"out of business", "ceased operations", bankruptcy filing, or domain expired/for sale. \
null if you genuinely cannot determine.
- closure_signals: array of zero or more: "no_results", "domain_expired", "website_404", \
"closed_announcement", "domain_for_sale", "permanently_closed", "acquired".
  Use "permanently_closed" when Google Maps or a directory explicitly labels the location \
as permanently closed.
  Use "acquired" when the company was bought by another entity and set still_operating=null.
- reasoning: one sentence explaining the determination."""

    try:
        response = client.messages.create(
            model=HAIKU_MODEL, max_tokens=256,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
            system=STAGE3C_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = response.usage
        cost = compute_cost(usage.input_tokens, usage.output_tokens, HAIKU_MODEL)
        text = get_text(response)
        obs.log_call(
            phase="part_4", model=HAIKU_MODEL,
            tokens=usage.input_tokens + usage.output_tokens, cost=cost,
            prompt_version="stage3c_closure_verify_v1", outcome="success",
            metadata={"handle": record["handle"], "stage": "3c", "raw_response": text},
        )
        result = extract_json(text)
        result["_stage"] = "3c"
        return result
    except Exception as e:
        log.warning("Stage 3c error for %s: %s", record["handle"], e)
        return {"_stage": "3c", "_error": str(e)}


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
        text = get_text(response)
        obs.log_call(
            phase="part_4", model=SONNET_MODEL,
            tokens=usage.input_tokens + usage.output_tokens, cost=cost,
            prompt_version="stage4_resolve_v1", outcome="success",
            metadata={"handle": record["handle"], "stage": 4,
                      "uncertain_fields": uncertain_fields, "raw_response": text},
        )
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

_DOMAIN_STOPWORDS = {
    "the", "and", "inc", "llc", "ltd", "corp", "co", "company", "group",
    "of", "for", "in", "at", "by", "de", "la", "el",
}


def _domain_matches_name(name: str, website: Optional[str]) -> bool:
    """Return True if any significant name token appears in the website domain.

    Tokens shorter than 4 chars or in the stopword list are skipped so that
    common suffixes like 'inc' or 'co' don't falsely match.
    """
    if not website:
        return True  # no website — not a mismatch, don't force Stage 1
    domain = normalize_domain(website) or ""
    domain_plain = re.sub(r"[^a-z0-9]", "", domain.lower())
    tokens = re.split(r"[\s\-_&,./]+", name.lower())
    significant = [t for t in tokens if len(t) >= 4 and t not in _DOMAIN_STOPWORDS]
    if not significant:
        return True  # can't determine — don't penalise
    return any(tok in domain_plain for tok in significant)


def enrich_record(record: dict, client: anthropic.Anthropic,
                  obs: ObservabilityLogger) -> dict:
    """Run the v2 cascade for a single record. Returns a flat enrichment dict.

    Stage flow:
      0 → (1 or 1b) → [1.5 gate] → [1.6 retry] → 2 → [3] → [3b] → [3c] → [4]
    """
    now = datetime.now(timezone.utc).isoformat()
    poc_condition = record.get("poc_condition", "")

    # ── Stage 0: rules (name-suffix type + TLD signals + platform flag) ───────
    stage0 = stage0_rules(record)

    needs_website_search = poc_condition in ("missing_website", "platform_url")

    # Route to Stage 1 (search) when the existing website domain doesn't match
    # the company name — parametric classification can't verify operating status
    # without search, and a mismatched domain is a strong signal the website is wrong.
    if not needs_website_search and not _domain_matches_name(
        record.get("name", ""), record.get("website")
    ):
        needs_website_search = True
        log.info("Domain mismatch for %s — routing to Stage 1 search", record["handle"])

    stage1_result: dict = {}
    stage3_result: dict = {}
    stage4_result: dict = {}

    # ── Stage 1 / 1b: extract ─────────────────────────────────────────────────
    if needs_website_search:
        stage1_result = stage1_search(client, record, obs)
    else:
        stage1_result = stage1b_parametric(client, record, obs)

    if stage1_result.get("_error"):
        return _build_output(record, stage0, stage1_result, stage3_result, stage4_result,
                             "error", now, max_stage=stage1_result.get("_stage", 1))

    # ── Stage 1.5: entity verification gate (conditional) ─────────────────────
    gate_result: dict = {}
    entity_verdict = "MATCH"
    if needs_website_search and needs_entity_gate(record, stage0, stage1_result):
        gate_result = stage1_5_entity_gate(client, record, stage1_result, obs)
        entity_verdict = gate_result.get("entity_verdict", "MATCH")
        log.info("Entity gate [%s]: %s → %s", record["handle"],
                 stage1_result.get("extracted_name", "?"), entity_verdict)

        if entity_verdict == "NO_MATCH":
            # Discard Stage 1 extraction entirely — entity was wrong
            return _build_output(record, stage0, {}, {}, {}, "completed", now, max_stage=0)

        if entity_verdict in ("SUBSIDIARY", "PARENT"):
            # Stage 1.6: retry with entity-exclusion refinement
            prior_name = stage1_result.get("extracted_name") or stage1_result.get("candidate_website", "")
            retry = stage1_search(client, record, obs, refined_exclude=prior_name)
            if not retry.get("_error"):
                stage1_result = retry

    # ── Stage 2: NAICS-filtered embeddings industry snap ($0) ─────────────────
    industry_raw = stage1_result.get("industry_raw") or ""
    naics_code = stage1_result.get("naics_2digit")
    if isinstance(naics_code, float):
        naics_code = int(naics_code) if not (naics_code != naics_code) else None

    # Honour Stage 0 industry signal (e.g. .k12 TLD → "primary and secondary education")
    if stage0.get("industry_inferred") and stage0["entity_confirmed"]:
        stage1_result["industry_snapped"] = stage0["industry_inferred"]
        stage1_result["industry_snap_method"] = "stage0_tld"
    else:
        snapped = snap_industry(industry_raw, naics_code=naics_code)
        if snapped:
            stage1_result["industry_snapped"] = snapped
            stage1_result["industry_snap_method"] = "embeddings" if naics_code else "keyword"
        elif record.get("industry") and not _is_nan(record.get("industry")):
            stage1_result["industry_snapped"] = record["industry"]
            stage1_result["industry_snap_method"] = "passthrough"
        else:
            stage1_result["industry_snapped"] = None
            stage1_result["industry_snap_method"] = "none"

    # Use Stage 0 type inference as NULL-FILL (never override an existing enriched type)
    if stage0.get("type_inferred") and _is_nan(stage1_result.get("candidate_type")):
        stage1_result["candidate_type"] = stage0["type_inferred"]
        stage1_result["type_confidence"] = stage0["type_inferred_confidence"]

    # ── Stage 2 (cont.): deterministic B2B/B2C from NAICS ($0) ─────────────────
    _NAICS_B2B_B2C: dict[int, str] = {
        # B2C
        44: "B2C", 45: "B2C",          # Retail Trade
        71: "B2C",                      # Arts, Entertainment & Recreation
        72: "B2C",                      # Accommodation & Food Services
        61: "B2C",                      # Educational Services
        # B2B
        11: "B2B", 21: "B2B", 22: "B2B",   # Agriculture, Mining, Utilities
        23: "B2B",                           # Construction
        31: "B2B", 32: "B2B", 33: "B2B",   # Manufacturing
        42: "B2B",                           # Wholesale Trade
        48: "B2B", 49: "B2B",               # Transportation & Warehousing
        51: "B2B",                           # Information / Media
        52: "B2B",                           # Finance & Insurance
        53: "B2B",                           # Real Estate
        54: "B2B",                           # Professional, Scientific & Technical
        55: "B2B",                           # Management of Companies
        56: "B2B",                           # Administrative & Support Services
        92: "B2B",                           # Public Administration / Government
        # Mixed
        62: "Both",                          # Health Care & Social Assistance
        81: "Both",                          # Other Services
    }
    b2b_vs_b2c: Optional[str] = _NAICS_B2B_B2C.get(naics_code) if naics_code else None
    stage1_result["b2b_vs_b2c"] = b2b_vs_b2c

    # ── Stage 3: website verification (low-confidence records only) ───────────
    candidate_website = normalize_domain(stage1_result.get("candidate_website"))
    w_conf = float(stage1_result.get("website_confidence", 0.0))

    if candidate_website and needs_website_search and w_conf < CONFIDENCE_VERIFY_THRESHOLD:
        stage3_result = stage3_verify(client, record, candidate_website, obs)
        if stage3_result.get("website_verified") is True:
            verified_conf = float(stage3_result.get("website_confidence", w_conf))
            stage1_result["website_confidence"] = max(w_conf, verified_conf)
        elif stage3_result.get("website_verified") is False:
            stage1_result["website_confidence"] = min(w_conf, 0.45)

    # ── Stage 3b: targeted size search (missing or low-confidence size) ────────
    s_conf_after_gate = float(stage1_result.get("size_confidence", 0.0))
    size_after_gate = stage1_result.get("candidate_size")
    if entity_verdict in ("MATCH", "MATCH") or stage0.get("entity_confirmed"):
        if _is_nan(size_after_gate) or s_conf_after_gate < 0.55:
            size_result = stage3b_size_search(client, record, obs)
            if not size_result.get("_error"):
                new_s_conf = float(size_result.get("size_confidence", 0.0))
                if new_s_conf > s_conf_after_gate and size_result.get("candidate_size"):
                    stage1_result["candidate_size"] = size_result["candidate_size"]
                    stage1_result["size_confidence"] = new_s_conf
                    log.info("Stage 3b size upgrade [%s]: %s → %s (%.2f)",
                             record["handle"], size_after_gate,
                             size_result["candidate_size"], new_s_conf)

    # ── Stage 3c: closure verification (still_operating=null after Stage 1b) ───
    # Only runs on the parametric path — Stage 1 (search) already had web access.
    if stage1_result.get("still_operating") is None and stage1_result.get("_stage") == "1b":
        phase_cost = obs.get_phase_cost("part_4")
        if phase_cost < PART4_BUDGET:
            closure_result = stage3c_closure_verify(client, record, obs)
            if not closure_result.get("_error") and closure_result.get("still_operating") is not None:
                stage1_result["still_operating"] = closure_result["still_operating"]
                stage1_result["closure_signals"] = closure_result.get("closure_signals") or []
                stage1_result["_closure_verified_stage"] = "3c"
                log.info("Stage 3c closure [%s]: still_operating=%s signals=%s",
                         record["handle"], closure_result["still_operating"],
                         closure_result.get("closure_signals", []))
        else:
            log.warning("Stage 3c skipped for %s — Part 4 budget exhausted", record["handle"])

    # ── Determine uncertain fields for Stage 4 escalation ────────────────────
    uncertain_fields: list[str] = []
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
    if gate_result:
        max_stage = max(max_stage, 2)  # 1.5 gate fired
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
        _w_conf = float(stage1.get("website_confidence", 0.0))
        website_original_correct = (website_enriched == website_original_domain) if _w_conf >= 0.70 else None
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

    # Final values: prefer high-confidence enriched value; fall back to original when confidence is low
    type_orig = record.get("type") if not _is_nan(record.get("type")) else None
    size_orig = record.get("size") if not _is_nan(record.get("size")) else None
    industry_orig = record.get("industry") if not _is_nan(record.get("industry")) else None
    type_final = type_enriched if (type_enriched and t_conf >= 0.65) else (type_orig or type_enriched)
    size_final = size_enriched if (size_enriched and s_conf >= 0.55) else (size_orig or size_enriched)
    industry_final = industry_enriched if (industry_enriched and i_conf >= 0.65) else (industry_orig or industry_enriched)
    website_final = (
        website_enriched if (website_enriched and w_conf >= 0.70)
        else (website_original_domain if (website_original_domain and not stage0.get("website_rules_flag")) else website_enriched)
    )

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
            else (type_enriched == record.get("type")) if (type_enriched and t_conf >= 0.65) else None
        ),
        "industry_original_correct": (
            None if _is_nan(record.get("industry"))
            else (industry_enriched == record.get("industry")) if (industry_enriched and i_conf >= 0.65) else None
        ),
        "size_original_correct": (
            None if _is_nan(record.get("size"))
            else (size_enriched == record.get("size")) if (size_enriched and s_conf >= 0.55) else None
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
        "operating_status_review_flag": stage1.get("still_operating") is None or bool(stage1.get("closure_signals")),
        # Record-level
        "enrichment_status": enrichment_status,
        "stage_resolved": max_stage,
        "status": status,
        # Business intelligence signals
        "still_operating": stage1.get("still_operating"),
        "closure_signals": stage1.get("closure_signals") or [],
        "is_single_facility": stage1.get("is_single_facility"),
        "b2b_vs_b2c": stage1.get("b2b_vs_b2c"),
        # Pass-through fields for eval join
        "poc_segment": record.get("poc_segment"),
        "poc_condition": record.get("poc_condition"),
        "name": record.get("name"),
        "city": record.get("city"),
        "state": record.get("state"),
    }


# ── Run report & review queue ──────────────────────────────────────────────────

_SEGMENT_PRIORITY = {"enterprise": 1, "mid_market": 2, "smb": 3, "micro": 4}
_FIELDS = ["website", "type", "industry", "size"]
_REVIEW_FLAG_COLS = [f"{f}_review_flag" for f in _FIELDS] + ["operating_status_review_flag"]


def generate_run_report(df: "pd.DataFrame", total_spent: float) -> None:
    """Write docs/part4-run-report.md and data/enriched/part4_review_queue.csv."""
    import pandas as pd

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    n = len(df)
    lines: list[str] = []

    def h(title: str) -> None:
        lines.append(f"\n## {title}\n")

    # ── Header ─────────────────────────────────────────────────────────────────
    lines.append(f"# Part 4 Enrichment Run Report\n")
    lines.append(f"_Generated: {ts}_  ")
    lines.append(f"_Pipeline version: {PIPELINE_VERSION}_  ")
    lines.append(f"_Records: {n}_  ")
    lines.append(f"_Budget spent: ${total_spent:.4f} / ${PART4_BUDGET:.2f} "
                 f"(${PART4_BUDGET - total_spent:.4f} remaining)_\n")

    # ── Enrichment outcome ──────────────────────────────────────────────────────
    h("Enrichment Outcome Distribution")
    if "enrichment_status" in df.columns:
        status_counts = df["enrichment_status"].value_counts(dropna=False)
        lines.append("| Status | Count | % |")
        lines.append("|--------|------:|--:|")
        for status, cnt in status_counts.items():
            lines.append(f"| {status} | {cnt} | {cnt/n:.0%} |")

    # ── Stage distribution ──────────────────────────────────────────────────────
    h("Stage Distribution")
    if "stage_resolved" in df.columns:
        stage_counts = df["stage_resolved"].value_counts(dropna=False).sort_index()
        lines.append("| Highest stage reached | Count | % |")
        lines.append("|----------------------|------:|--:|")
        stage_labels = {0: "Stage 0 only (budget/skip)", 1: "Stage 1/1b (Haiku search)",
                        3: "Stage 3 (Haiku verify)", 4: "Stage 4 (Sonnet)"}
        for stage, cnt in stage_counts.items():
            label = stage_labels.get(stage, f"Stage {stage}")
            lines.append(f"| {label} | {cnt} | {cnt/n:.0%} |")

    # ── Fill rates ──────────────────────────────────────────────────────────────
    h("Fill Rate by Field")
    lines.append("| Field | Originally null | Now filled | Fill rate |")
    lines.append("|-------|---------------:|----------:|----------:|")
    for field in _FIELDS:
        orig_col = f"{field}_original"
        final_col = f"{field}_final"
        if orig_col not in df.columns or final_col not in df.columns:
            continue
        orig_null = df[orig_col].isna() | (df[orig_col] == "")
        final_filled = df[final_col].notna() & (df[final_col] != "")
        newly_filled = (orig_null & final_filled).sum()
        null_count = orig_null.sum()
        rate = f"{newly_filled/null_count:.0%}" if null_count > 0 else "N/A"
        lines.append(f"| {field} | {null_count} | {newly_filled} | {rate} |")

    # ── Source data reliability ─────────────────────────────────────────────────
    h("Source Data Reliability (`original_correct` by field × segment)")
    lines.append("_Rows where `original_correct=True` — pipeline confirmed the source value was right. "
                 "`False` — pipeline found a different (likely correct) value. "
                 "`unknown` — field was originally null (no signal)._\n")

    segs = ["enterprise", "mid_market", "smb", "micro"]
    header_segs = " | ".join(segs)
    lines.append(f"| Field | Metric | {header_segs} |")
    lines.append("|-------|--------|" + "|".join(["-------"] * len(segs)) + "|")

    for field in _FIELDS:
        col = f"{field}_original_correct"
        if col not in df.columns:
            continue
        correct_row, incorrect_row, rate_row = [], [], []
        for seg in segs:
            sub = df[df["poc_segment"] == seg][col] if "poc_segment" in df.columns else df[col]
            correct = (sub == True).sum()  # noqa: E712
            incorrect = (sub == False).sum()  # noqa: E712
            total = correct + incorrect
            correct_row.append(str(correct))
            incorrect_row.append(str(incorrect))
            rate_row.append(f"{correct/total:.0%}" if total > 0 else "—")
        lines.append(f"| **{field}** | correct | {' | '.join(correct_row)} |")
        lines.append(f"| | incorrect | {' | '.join(incorrect_row)} |")
        lines.append(f"| | reliability | {' | '.join(rate_row)} |")

    h("Source Data Reliability by Field × Size Band")
    size_bands = ["1-10", "11-50", "51-200", "201-500", "501-1K", "1K-5K", "5K-10K", "10K+"]
    present_bands = [b for b in size_bands
                     if "size_original" in df.columns and (df["size_original"] == b).any()]
    if present_bands:
        hdr = " | ".join(present_bands)
        lines.append(f"| Field | Metric | {hdr} |")
        lines.append("|-------|--------|" + "|".join(["-------"] * len(present_bands)) + "|")
        for field in _FIELDS:
            col = f"{field}_original_correct"
            if col not in df.columns:
                continue
            correct_row, rate_row = [], []
            for band in present_bands:
                sub = df[df["size_original"] == band][col]
                correct = (sub == True).sum()  # noqa: E712
                incorrect = (sub == False).sum()  # noqa: E712
                total = correct + incorrect
                correct_row.append(f"{correct}/{total}" if total > 0 else "—")
                rate_row.append(f"{correct/total:.0%}" if total > 0 else "—")
            lines.append(f"| **{field}** | correct/total | {' | '.join(correct_row)} |")
            lines.append(f"| | reliability | {' | '.join(rate_row)} |")

    # ── Business operating status ───────────────────────────────────────────────
    h("Business Operating Status")
    if "still_operating" in df.columns:
        active = (df["still_operating"] == True).sum()   # noqa: E712
        defunct = (df["still_operating"] == False).sum()  # noqa: E712
        unknown = df["still_operating"].isna().sum()
        lines.append("| Status | Count | % of batch |")
        lines.append("|--------|------:|-----------:|")
        lines.append(f"| Active | {active} | {active/n:.0%} |")
        lines.append(f"| Defunct | {defunct} | {defunct/n:.0%} |")
        lines.append(f"| Unknown | {unknown} | {unknown/n:.0%} |")
        if defunct > 0 and "closure_signals" in df.columns:
            from collections import Counter
            all_signals: list[str] = []
            for signals in df["closure_signals"].dropna():
                if isinstance(signals, list):
                    all_signals.extend(signals)
            if all_signals:
                signal_counts = Counter(all_signals)
                lines.append("\n_Closure signals observed:_\n")
                for sig, cnt in signal_counts.most_common():
                    lines.append(f"- `{sig}`: {cnt}")

    # ── B2B vs B2C breakdown ────────────────────────────────────────────────────
    h("B2B vs B2C by Segment")
    if "b2b_vs_b2c" in df.columns and "poc_segment" in df.columns:
        lines.append("| Segment | B2B | B2C | Both | Unknown |")
        lines.append("|---------|----:|----:|-----:|--------:|")
        for seg in segs:
            sub = df[df["poc_segment"] == seg]["b2b_vs_b2c"] if "poc_segment" in df.columns else df["b2b_vs_b2c"]
            b2b = (sub == "B2B").sum()
            b2c = (sub == "B2C").sum()
            both = (sub == "Both").sum()
            unk = sub.isna().sum()
            lines.append(f"| {seg} | {b2b} | {b2c} | {both} | {unk} |")
        # overall row
        b2b = (df["b2b_vs_b2c"] == "B2B").sum()
        b2c = (df["b2b_vs_b2c"] == "B2C").sum()
        both = (df["b2b_vs_b2c"] == "Both").sum()
        unk = df["b2b_vs_b2c"].isna().sum()
        lines.append(f"| **total** | **{b2b}** | **{b2c}** | **{both}** | **{unk}** |")

    # ── Review queue summary ────────────────────────────────────────────────────
    h("Review Queue Summary")
    flag_cols_present = [c for c in _REVIEW_FLAG_COLS if c in df.columns]
    if flag_cols_present:
        any_flag = df[flag_cols_present].any(axis=1)
        flagged_count = any_flag.sum()
        lines.append(f"**{flagged_count} records** flagged for manual review "
                     f"({flagged_count/n:.0%} of batch).\n")
        lines.append("| Field | Flagged records |")
        lines.append("|-------|---------------:|")
        for col in flag_cols_present:
            field = col.replace("_review_flag", "")
            cnt = df[col].sum() if df[col].dtype == bool else (df[col] == True).sum()  # noqa: E712
            lines.append(f"| {field} | {cnt} |")
        if "poc_segment" in df.columns:
            lines.append("\n| Segment | Flagged | Total |")
            lines.append("|---------|--------:|------:|")
            for seg in segs:
                seg_mask = df["poc_segment"] == seg
                seg_flagged = (any_flag & seg_mask).sum()
                seg_total = seg_mask.sum()
                lines.append(f"| {seg} | {seg_flagged} | {seg_total} |")
        lines.append(f"\nReview queue written to: `data/enriched/part4_review_queue.csv`")
    else:
        lines.append("No review flag columns found in output.")

    # Write report
    report_path = ROOT / "docs/part4-run-report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Run report written to %s", report_path)

    # ── Review queue CSV ────────────────────────────────────────────────────────
    if not flag_cols_present:
        return

    any_flag = df[[c for c in _REVIEW_FLAG_COLS if c in df.columns]].any(axis=1)
    review_df = df[any_flag].copy()

    review_df["priority"] = review_df["poc_segment"].map(_SEGMENT_PRIORITY).fillna(9).astype(int)
    review_df["fields_to_review"] = review_df.apply(
        lambda row: ", ".join(
            f for f in _FIELDS
            if row.get(f"{f}_review_flag", False)
        ),
        axis=1,
    )

    # Blank out field columns for rows where that field is NOT flagged
    field_cols_ordered = []
    for field in _FIELDS:
        for suffix in ("_original", "_enriched", "_confidence", "_pipeline_stage"):
            col = f"{field}{suffix}"
            if col in review_df.columns:
                field_cols_ordered.append(col)
                flag_col = f"{field}_review_flag"
                if flag_col in review_df.columns:
                    not_flagged = ~review_df[flag_col].fillna(False).astype(bool)
                    review_df.loc[not_flagged, col] = None

    id_cols = ["priority", "handle", "name", "city", "state", "poc_segment", "fields_to_review"]
    id_cols = [c for c in id_cols if c in review_df.columns]

    out_cols = id_cols + field_cols_ordered
    review_df = review_df[out_cols].sort_values(
        ["priority", "website_confidence"] if "website_confidence" in review_df.columns else ["priority"]
    )

    csv_path = ROOT / "data/enriched/part4_review_queue.csv"
    review_df.to_csv(csv_path, index=False)
    log.info("Review queue (%d records) written to %s", len(review_df), csv_path)


# ── Main ───────────────────────────────────────────────────────────────────────

def run_part4(limit: Optional[int] = None,
              handles: Optional[List[str]] = None) -> None:
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
    if handles is not None:
        handle_set = set(handles)
        records = [r for r in records if r.get("handle") in handle_set]
        log.info("HANDLE MODE: running %d specific records", len(records))
    elif limit is not None:
        records = records[:limit]
        log.info("TEST MODE: limiting to %d records", limit)
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

    # Write output parquet via DuckDB — merge with existing when running specific handles
    import pandas as pd
    new_df = pd.DataFrame(results)

    if handles is not None and Path(ENRICHED_PATH).exists():
        existing_df = duckdb.connect().execute(
            f"SELECT * FROM parquet_scan('{ENRICHED_PATH}')"
        ).df()
        # Drop any existing rows for handles being re-run, then append
        existing_df = existing_df[~existing_df["handle"].isin(set(handles))]
        out_df = pd.concat([existing_df, new_df], ignore_index=True)
        log.info("Merged %d existing + %d new records", len(existing_df), len(new_df))
    else:
        out_df = new_df

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

    # Run report + review queue
    generate_run_report(out_df, total_spent)

    # Cascade health gates
    print("\n=== Cascade health gates ===")
    try:
        enforce(check_cascade_health(ENRICHED_PATH), "cascade_health")
    except GateFailure as e:
        log.error("Cascade health: %s", e)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Part 4 enrichment pipeline")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N records (for test runs)")
    parser.add_argument("--handles", type=str, default=None,
                        help="Comma-separated list of handles to run (merges into existing enriched output)")
    args = parser.parse_args()
    handle_list = [h.strip() for h in args.handles.split(",")] if args.handles else None
    run_part4(limit=args.limit, handles=handle_list)
