"""
Phase 1.5 — Deterministic cleanup gate.

Reads:  data/processed/us_companies.parquet  (never modified)
Writes: data/processed/us_companies_clean.parquet

Rules applied (in order, first match wins per field):
  state:   trim → already-valid → case-fix → abbreviation-expand →
           redundant-prefix-strip → typo-correct → city-in-state-recover → NULL
  website: platform-blocklist → institutional-TLD → placeholder → keep
  founded: pre-1800 → NULL

Each record gets a `rules_flags` column listing which rules fired (empty = no change).
Recovery stats are logged at the end.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent

from src.shared.config import CONFIG

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

INPUT = ROOT / CONFIG.market.dataset.parquet
OUTPUT = ROOT / "data/processed/us_companies_clean.parquet"

# ── Valid state universe ───────────────────────────────────────────────────────

VALID_STATES = frozenset([
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming", "District of Columbia",
    "Puerto Rico", "Guam", "U.S. Virgin Islands", "American Samoa",
    "Northern Mariana Islands",
])

# ── State normalisation maps ───────────────────────────────────────────────────

# Standard USPS codes + documented dotted variants (§1b: 47 distinct abbrev values)
_ABBREV_MAP: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
    "PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands",
    "AS": "American Samoa", "MP": "Northern Mariana Islands",
}

# Build dotted variants automatically (AL → A.L., etc.)
_DOTTED: dict[str, str] = {}
for _code, _name in _ABBREV_MAP.items():
    if len(_code) == 2:
        dotted = f"{_code[0]}.{_code[1]}."
        _DOTTED[dotted] = _name
        _DOTTED[f"{_code[0]}.{_code[1]}"] = _name  # without trailing dot

ABBREV_MAP: dict[str, str] = {**_ABBREV_MAP, **_DOTTED}

# Documented typos (§1b: 6 distinct typos, 511 records)
TYPO_MAP: dict[str, str] = {
    "Flrida": "Florida",
    "Flordia": "Florida",
    "Californie": "California",
    "Califrnia": "California",
    "Calfornia": "California",
    "Califonia": "California",
    "Georgea": "Georgia",
    "Tennesse": "Tennessee",
    "Tennesse": "Tennessee",
    "Pennsylvnia": "Pennsylvania",
    "Pennsylvannia": "Pennsylvania",
    "Washignton": "Washington",
    "Massacusetts": "Massachusetts",
    "Massachsetts": "Massachusetts",
    "Massachusets": "Massachusetts",
    "Connecticutt": "Connecticut",
    "Louisianna": "Louisiana",
    "Missisipi": "Mississippi",
    "Missisippi": "Mississippi",
    "Minnessota": "Minnesota",
}

# City-in-state recovery: state field holds a suffix word from a two-word state name.
# Key: leaked state value. Value: (expected city prefix, recovered state).
# Only unambiguous splits included (§1b: ~17,903 records across 41 distinct values).
CITY_IN_STATE: dict[str, tuple[str, str]] = {
    "York": ("New", "New York"),
    "Hampshire": ("New", "New Hampshire"),
    "Jersey": ("New", "New Jersey"),
    "Mexico": ("New", "New Mexico"),
    # Directional splits — only when city prefix is unambiguous
    "Orleans": ("New", "Louisiana"),       # New Orleans → Louisiana
    "Angeles": ("Los", "California"),
    "Francisco": ("San", "California"),    # San Francisco
    "Diego": ("San", "California"),
    "Antonio": ("San", "Texas"),
    "Jose": ("San", "California"),
    "Vegas": ("Las", "Nevada"),
    "Paso": ("El", "Texas"),
}

# ── Website cleaning ───────────────────────────────────────────────────────────

PLACEHOLDER_URLS: frozenset[str] = frozenset({
    "www", "http", "https", "http://", "https://", "www.",
    "http://www", "https://www", "http://www.", "https://www.",
    "com", ".com", "n/a", "none", "null", "na", "n.a.", "-",
    "example.com", "test.com", "website.com",
})

INSTITUTIONAL_TLDS: tuple[str, ...] = (".edu", ".mil", ".gov")

# Platform blocklist from config — no hardcoding here
_PLATFORM_BLOCKLIST: frozenset[str] = CONFIG.enrichment_rules.platform_blocklist_set

# ── Name cleaning ──────────────────────────────────────────────────────────────

NAME_SENTINEL: frozenset[str] = frozenset({
    "closed", "none", "n/a", "na", "null", "unknown", "retired",
    "test", "deleted", "delete", "removed", ".", "-", "...", "x", "a",
})

# ── City cleaning ──────────────────────────────────────────────────────────────

# State abbreviations and junk values that appear in the city field (§6b §11.4)
JUNK_CITY_VALUES: frozenset[str] = frozenset({
    "ny", "fl", "dc", "la", "sf", "mc", "n/a", "na", "none", "null", "unknown",
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa",
    "wv", "wi", "wy",
})

# When state_city_recover fires, prefix+suffix = the real city name.
# Only entries where the combination is a known US city (not a state name like "New Hampshire").
CITY_CORRECT: dict[str, str] = {
    "York": "New York",
    "Orleans": "New Orleans",
    "Angeles": "Los Angeles",
    "Francisco": "San Francisco",
    "Diego": "San Diego",
    "Antonio": "San Antonio",
    "Jose": "San Jose",
    "Vegas": "Las Vegas",
    "Paso": "El Paso",
}


def _has_non_latin(name: str) -> bool:
    """Return True if name contains CJK (U+4E00–U+9FFF) or Arabic (U+0600–U+06FF) characters."""
    for ch in name:
        cp = ord(ch)
        if 0x4E00 <= cp <= 0x9FFF or 0x0600 <= cp <= 0x06FF:
            return True
    return False


def clean_name(name_val: Optional[str]) -> tuple[Optional[str], str]:
    """Null out short/garbage/sentinel names. Returns (cleaned_or_None, flag)."""
    if not isinstance(name_val, str):
        return name_val, ""
    stripped = name_val.strip()
    if not stripped or len(stripped) < 2 or stripped.lower() in NAME_SENTINEL:
        return None, "name_garbage"
    return name_val, ""


def clean_city(city_val: Optional[str], orig_state_val: Optional[str], state_flag: str) -> tuple[Optional[str], str]:
    """
    Fix city field in two cases:
    1. state_city_recover fired — recombine prefix+suffix into the real city name where known.
    2. Junk state-abbreviation or short garbage value in city field → NULL.
    """
    if not isinstance(city_val, str):
        return city_val, ""
    stripped = city_val.strip()
    if not stripped:
        return None, ""

    if state_flag == "state_city_recover" and isinstance(orig_state_val, str):
        suffix = orig_state_val.strip()
        corrected = CITY_CORRECT.get(suffix) or CITY_CORRECT.get(suffix.title())
        if corrected:
            return corrected, "city_state_recombine"

    if stripped.lower() in JUNK_CITY_VALUES or (len(stripped) <= 2 and stripped.isalpha()):
        return None, "city_junk"

    if len(stripped) <= 3 and stripped.endswith("-"):
        return None, "city_junk"

    return city_val, ""


def _extract_domain(url: str) -> str:
    """Return the netloc/domain from a URL string, lowercased."""
    url = url.strip().lower()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        return urlparse(url).netloc.lstrip("www.")
    except Exception:
        return url


def clean_website(url: Optional[str]) -> tuple[Optional[str], str]:
    """Return (cleaned_url_or_None, flag_name_or_empty)."""
    if not url or (isinstance(url, float)):
        return None, ""

    raw = url.strip()
    if not raw:
        return None, ""

    lowered = raw.lower()

    if lowered in PLACEHOLDER_URLS:
        return None, "website_placeholder"

    domain = _extract_domain(raw)

    if any(domain.endswith(tld) for tld in INSTITUTIONAL_TLDS):
        return None, "website_institutional_tld"

    for blocked in _PLATFORM_BLOCKLIST:
        if domain == blocked or domain.endswith("." + blocked):
            return None, "website_platform_blocklist"

    return raw, ""


# ── Founded cleaning ───────────────────────────────────────────────────────────

def clean_founded(val) -> tuple[Optional[int], str]:
    """Null out pre-1800 values (confirmed junk, §6b: 1,357 records)."""
    if val is None:
        return None, ""
    if isinstance(val, float):
        if pd.isna(val):
            return None, ""
        val = int(val)
    if isinstance(val, str):
        stripped = val.strip().lower()
        if not stripped or stripped in ("nan", "none", "null", "n/a", "na"):
            return None, ""
        try:
            val = int(float(stripped))
        except (ValueError, TypeError):
            return None, ""
    try:
        year = int(val)
    except (ValueError, TypeError):
        return None, ""
    if year < 1800:
        return None, "founded_pre1800"
    return year, ""


# ── State cleaning ─────────────────────────────────────────────────────────────

def _strip_redundant_prefix(val: str) -> Optional[str]:
    """
    'Tx Texas' → 'Texas', 'Fl Florida' → 'Florida'.
    Tries all suffixes from shortest to longest; returns first that is a valid state.
    Covers §1b's 143 distinct redundant-prefix values without hardcoding each one.
    """
    words = val.split()
    if len(words) < 2:
        return None
    for start in range(1, len(words)):
        candidate = " ".join(words[start:])
        if candidate in VALID_STATES:
            return candidate
    return None


def clean_state(state_val: Optional[str], city_val: Optional[str]) -> tuple[Optional[str], str]:
    """
    Apply state normalisation pipeline.  Returns (cleaned_state_or_None, flag).
    """
    if not state_val or (isinstance(state_val, float) and pd.isna(state_val)):
        return None, ""

    val = state_val.strip()
    if not val:
        return None, ""

    # 1. Already valid
    if val in VALID_STATES:
        return val, ""

    # 2. Case mismatch — title-case and re-check (handles "District Of Columbia")
    title = val.title()
    if title in VALID_STATES:
        return title, "state_case_fix"

    # 3. Abbreviation expansion (upper-case lookup for standard codes; as-is for dotted)
    upper = val.upper().strip(".")
    candidate = ABBREV_MAP.get(val) or ABBREV_MAP.get(upper) or ABBREV_MAP.get(val.upper())
    if candidate:
        return candidate, "state_abbrev_expand"

    # 4. Redundant prefix strip ("Tx Texas" → "Texas")
    stripped = _strip_redundant_prefix(val)
    if stripped:
        return stripped, "state_redundant_prefix"

    # Also try title-cased strip
    stripped = _strip_redundant_prefix(title)
    if stripped:
        return stripped, "state_redundant_prefix"

    # 5. Typo correction
    typo_fix = TYPO_MAP.get(val) or TYPO_MAP.get(title)
    if typo_fix:
        return typo_fix, "state_typo_fix"

    # 6. City-in-state recovery — use city field to disambiguate
    entry = CITY_IN_STATE.get(val) or CITY_IN_STATE.get(title)
    if entry:
        expected_prefix, recovered_state = entry
        city_str = city_val if isinstance(city_val, str) else ""
        city_clean = city_str.strip()
        if city_clean.lower() == expected_prefix.lower() or city_clean == "":
            return recovered_state, "state_city_recover"

    return None, "state_unresolvable"


# ── Vectorised application ─────────────────────────────────────────────────────

def _compute_shared_domain_flag(df: pd.DataFrame, website_series: pd.Series) -> pd.Series:
    """Flag records whose domain appears on ≥50 distinct handle values (franchise/chain shared domain)."""
    domains = website_series.apply(lambda u: _extract_domain(u) if isinstance(u, str) else None)
    handles = df["handle"] if "handle" in df.columns else pd.Series([""] * len(df), index=df.index)
    temp = pd.DataFrame({"domain": domains, "handle": handles})
    temp = temp[temp["domain"].notna() & (temp["domain"] != "")]
    counts = temp.groupby("domain")["handle"].nunique()
    shared: frozenset[str] = frozenset(counts[counts >= 50].index)
    return domains.apply(lambda d: d in shared if d else False)


def apply_rules(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all rules to a copy of df. Adds `rules_flags` column and boolean flag columns."""
    out = df.copy()
    flags: list[list[str]] = [[] for _ in range(len(df))]

    # ── name ───────────────────────────────────────────────────────────────────
    log.info("Applying name cleaning rules...")
    name_results = [clean_name(n) for n in df["name"]]
    name_vals, name_flags = zip(*name_results)
    out["name"] = list(name_vals)
    for i, flag in enumerate(name_flags):
        if flag:
            flags[i].append(flag)

    # ── state ──────────────────────────────────────────────────────────────────
    log.info("Applying state normalisation rules...")
    city_col = df["city"] if "city" in df.columns else [None] * len(df)
    state_results = [clean_state(s, c) for s, c in zip(df["state"], city_col)]
    state_vals, state_flags = zip(*state_results)
    out["state"] = list(state_vals)
    for i, flag in enumerate(state_flags):
        if flag:
            flags[i].append(flag)

    # ── city ───────────────────────────────────────────────────────────────────
    log.info("Applying city cleaning rules...")
    city_results = [
        clean_city(c, s_orig, s_flag)
        for c, s_orig, s_flag in zip(city_col, df["state"], state_flags)
    ]
    city_vals, city_flags = zip(*city_results)
    out["city"] = list(city_vals)
    for i, flag in enumerate(city_flags):
        if flag:
            flags[i].append(flag)

    # ── website ────────────────────────────────────────────────────────────────
    log.info("Applying website cleaning rules...")
    website_results = [clean_website(w) for w in df["website"]]
    web_vals, web_flags = zip(*website_results)
    out["website"] = list(web_vals)
    for i, flag in enumerate(web_flags):
        if flag:
            flags[i].append(flag)

    # ── founded ────────────────────────────────────────────────────────────────
    log.info("Applying founded cleaning rules...")
    founded_results = [clean_founded(f) for f in df["founded"]]
    out["founded"] = [v for v, _ in founded_results]
    for i, (_, flag) in enumerate(founded_results):
        if flag:
            flags[i].append(flag)

    out["rules_flags"] = [",".join(f) for f in flags]

    # ── boolean flag columns (dataset-level; no value changes) ─────────────────
    log.info("Computing boolean flag columns...")
    out["has_non_latin_name"] = out["name"].apply(
        lambda n: _has_non_latin(n) if isinstance(n, str) else False
    )
    founded_num = pd.to_numeric(out["founded"], errors="coerce")
    out["implausible_size_founded"] = (df["size"] == "10K+") & (founded_num >= 2021)
    out["has_shared_domain"] = _compute_shared_domain_flag(df, out["website"])

    return out


def log_recovery_stats(original: pd.DataFrame, cleaned: pd.DataFrame) -> None:
    """Log how many records each rule recovered / changed."""
    flag_series = cleaned["rules_flags"]
    all_flags = flag_series[flag_series != ""].str.split(",").explode()
    counts = all_flags.value_counts()

    log.info("=" * 60)
    log.info("  RULES RECOVERY SUMMARY")
    log.info("=" * 60)
    for flag, count in counts.items():
        log.info(f"  {flag:<35} {count:>8,} records")

    total_changed = (flag_series != "").sum()
    log.info(f"\n  Total records modified: {total_changed:,} of {len(cleaned):,}")

    # State recovery
    orig_invalid = (~original["state"].isin(VALID_STATES) & original["state"].notna()).sum()
    still_null = cleaned["state"].isna().sum()
    orig_null = original["state"].isna().sum()
    recovered = orig_invalid - (still_null - orig_null)
    log.info(f"\n  State: {orig_invalid:,} invalid → {recovered:,} recovered, "
             f"{still_null - orig_null:,} net new NULLs (unresolvable)")

    # Name garbage
    orig_null_name = original["name"].isna().sum()
    new_null_name = cleaned["name"].isna().sum()
    log.info(f"  Name: {new_null_name - orig_null_name:,} garbage/sentinel names → NULL")

    # City cleanup
    city_recombined = flag_series.str.contains("city_state_recombine").sum()
    city_junked = flag_series.str.contains("city_junk").sum()
    log.info(f"  City: {city_recombined:,} corrected via state recombine, {city_junked:,} junk → NULL")

    # Website reclassification
    orig_null_web = original["website"].isna().sum()
    new_null_web = cleaned["website"].isna().sum()
    reclassified = new_null_web - orig_null_web
    log.info(f"  Website: {reclassified:,} URLs reclassified as NULL")

    # Founded null-out
    orig_null_f = original["founded"].isna().sum()
    new_null_f = cleaned["founded"].isna().sum()
    log.info(f"  Founded: {new_null_f - orig_null_f:,} pre-1800 values → NULL")

    # Boolean flag columns
    log.info(f"  has_non_latin_name flagged: {cleaned['has_non_latin_name'].sum():,} records")
    log.info(f"  implausible_size_founded flagged: {cleaned['implausible_size_founded'].sum():,} records")
    log.info(f"  has_shared_domain flagged: {cleaned['has_shared_domain'].sum():,} records")
    log.info("=" * 60)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    if not INPUT.exists():
        log.error(f"Input not found: {INPUT}")
        sys.exit(1)

    log.info(f"Reading {INPUT} ...")
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_parquet('{INPUT}')").df()
    log.info(f"Loaded {len(df):,} records, columns: {list(df.columns)}")

    cleaned = apply_rules(df)

    log_recovery_stats(df, cleaned)

    log.info(f"Writing {OUTPUT} ...")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # Register DataFrame with DuckDB and write Parquet natively (no pyarrow dep)
    con.register("cleaned", cleaned)
    con.execute(f"COPY cleaned TO '{OUTPUT}' (FORMAT PARQUET)")
    log.info("Done.")


if __name__ == "__main__":
    main()
