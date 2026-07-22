"""DealScope — Streamlit app.

Pipeline (composition-order contract from scoring.py / valuation.py):
load_companies() -> score_companies() + valuation_range() on the FULL
universe -> filter_companies() last, purely for display.

UI: the "DealScope - Final Design" direction — a dark, teal-accented,
five-view flow: landing/search -> results (score-ring table) -> tear sheet,
with an advanced-filters slide-over reachable from a top-bar button. The
data/logic layer under src/ is unchanged; this file is presentation only.
"""

import fcntl
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.data.loaders import load_companies, load_deals, get_data_as_of
from src.data.filings import fetch_all_nse_filings, fetch_bse_notices, match_filings_to_company, parse_pub_date, NSE_FEEDS
from src.data.news import fetch_company_news
from src.data.sector_taxonomy_v2 import SECTOR_V2_BUCKETS, TAXONOMY_VERSION
from src.logic.filtering import filter_companies
from src.logic.scoring import score_companies, METRICS
from src.logic.valuation import valuation_range
from src.logic.piotroski import compute_piotroski
from src.logic.zscore import compute_zscore
from src.config import get_gemini_api_key, get_groq_api_key, get_cerebras_api_key

# ----------------------------------------------------------------------------
# Palette — DealScope design-system tokens (near-black / mint-accent system,
# spec'd in the technical design doc: bg/panel/panelAlt/text/muted/dim/accent/
# accentDim/accentText/warn). Variable NAMES kept from the prior teal system
# so every call site below is unchanged; only the underlying hex/rgba values
# moved to match the spec exactly.
# ----------------------------------------------------------------------------

C_BG = "#07080a"          # bg — page background
C_CARD = "#0d0f0d"        # panel — card/table/row/modal background
C_CARD2 = "#111411"       # panelAlt — header row, row-hover, empty-ring, dashed-box bg
C_PANEL = "#111411"       # panelAlt (dashed "insufficient data" cards)
C_ROW_ALT = "#111411"     # panelAlt, used solid for zebra striping (spec: "row-hover background")
C_TEAL = "#2ee88a"        # accent (mint) — the system's sole accent color
C_TEAL_LT = "#2ee88a"     # accent — spec has one accent tone, not a lighter variant
C_TEAL_DK = "rgba(46,232,138,.16)"   # accentDim — active-chip / valuation-gradient start
C_TEAL_DK2 = "rgba(46,232,138,.05)"  # accentDim, fainter — valuation-gradient end
C_INK = "#07080a"         # accentText — text on a solid accent fill
C_T1 = "#dfe3e0"          # text — primary
C_T2 = "#b7bcb8"          # text/muted blend — secondary (spec defines no distinct tier; interpolated)
C_T3 = "#6f756f"          # muted — secondary/meta text (spec exact)
C_T4 = "#6f756f"          # muted — spec's 3-tier system collapses dim-label tiers into muted
C_T5 = "#6f756f"          # muted (labels, ranks)
C_T6 = "#454944"          # dim — tertiary/disabled (spec exact; footer, N/A, pending values)
C_BORDER = "rgba(255,255,255,.10)"   # border
C_BORDER2 = "rgba(255,255,255,.18)"  # borderStrong
C_TRACK = "rgba(255,255,255,.1)"
C_WARN = "#e0b23e"        # warn (amber) — sole alert color (Grey-zone Z-score, filing tags)
C_DANGER = "#e0625a"      # not in the spec's token list; added only for the Distress Z-score
                           # zone, which needs a 3rd, distinct semantic color from warn/accent.

FACTOR_LABELS = {
    "revenue_growth_pct": "Revenue Growth",
    "ebitda_margin_pct": "EBITDA Margin",
    "return_on_capital_employed_pct": "ROCE",
    "total_debt": "Debt Level",
}

# Filters are preset BUCKETS chosen from dropdowns, not free-drag range
# sliders. Dragging a two-handle slider to a precise value is fiddly and was
# the single biggest usability complaint; a labelled dropdown ("Mid ·
# ₹2,000–20,000 Cr") is instant and unambiguous. Each bucket carries the raw
# (lo, hi) bounds filter_companies() expects; None = open-ended on that side.
_CR = 1e7  # one crore, in raw rupees (yfinance reports in rupees)

# {field: (human label, [(option label, (raw_lo, raw_hi) | None), ...])}
# Option index 0 is always "Any" (no filter). Ordered high→low so the most
# selective/interesting buckets sit near the top of the dropdown.
FILTER_PRESETS = {
    "market_cap": ("Market cap", [
        ("Any", None),
        ("Mega · over ₹1,00,000 Cr", (100000 * _CR, None)),
        ("Large · ₹20,000–1,00,000 Cr", (20000 * _CR, 100000 * _CR)),
        ("Mid · ₹2,000–20,000 Cr", (2000 * _CR, 20000 * _CR)),
        ("Small · ₹500–2,000 Cr", (500 * _CR, 2000 * _CR)),
        ("Micro · under ₹500 Cr", (None, 500 * _CR)),
    ]),
    "revenue": ("Revenue", [
        ("Any", None),
        ("Over ₹10,000 Cr", (10000 * _CR, None)),
        ("₹2,000–10,000 Cr", (2000 * _CR, 10000 * _CR)),
        ("₹500–2,000 Cr", (500 * _CR, 2000 * _CR)),
        ("₹100–500 Cr", (100 * _CR, 500 * _CR)),
        ("Under ₹100 Cr", (None, 100 * _CR)),
    ]),
    "ebitda_margin_pct": ("EBITDA margin", [
        ("Any", None),
        ("Over 30%", (30, None)),
        ("20–30%", (20, 30)),
        ("10–20%", (10, 20)),
        ("0–10%", (0, 10)),
        ("Loss-making (< 0%)", (None, 0)),
    ]),
    "return_on_capital_employed_pct": ("ROCE", [
        ("Any", None),
        ("Over 25%", (25, None)),
        ("15–25%", (15, 25)),
        ("5–15%", (5, 15)),
        ("0–5%", (0, 5)),
        ("Negative (< 0%)", (None, 0)),
    ]),
    "total_debt": ("Total debt", [
        ("Any", None),
        ("Debt-free / minimal", (None, 1 * _CR)),
        ("Under ₹500 Cr", (None, 500 * _CR)),
        ("₹500–5,000 Cr", (500 * _CR, 5000 * _CR)),
        ("Over ₹5,000 Cr", (5000 * _CR, None)),
    ]),
}
FILTER_PRESET_FIELDS = list(FILTER_PRESETS.keys())

# Promoter-pledge is a ceiling, not a range: each option is a max acceptable %.
PLEDGE_PRESETS = ("Max promoter pledge", [
    ("Any", None),
    ("No pledge (0%)", 0.0),
    ("Under 10%", 10.0),
    ("Under 25%", 25.0),
    ("Under 50%", 50.0),
])

# Financial-health is one dropdown that sets the internal fh flags below.
FIN_HEALTH_PRESETS = ("Financial health", [
    ("Any", {}),
    ("Altman Z'': Safe zone", {"safe_only": True}),
    ("Exclude Distress zone", {"exclude_distress": True}),
    ("Piotroski F-Score ≥ 7 (strong)", {"min_fscore": 7}),
    ("Piotroski F-Score ≥ 5", {"min_fscore": 5}),
])

# Query-param keys the Reset button clears (dropdown indices + weights + sectors).
FILTER_QP_KEYS = ["sectors"] + [f"f_{fld}" for fld in FILTER_PRESET_FIELDS] + ["f_pledge", "f_health"]
FILTER_WIDGET_KEYS = [f"sb_{fld}" for fld in FILTER_PRESET_FIELDS] + ["sb_pledge", "sb_health"]

# How many company rows the custom-HTML results table renders at once. The
# full filtered set always drives the "N matched" count and the CSV export;
# rendering every one of up to 2,046 conic-gradient score rings as live DOM
# would lag, so the ranked table shows the top slice and a "show more" step
# extends it. Nothing is hidden from filtering or export — only from the
# initial paint.
ROWS_PER_PAGE = 60

st.set_page_config(
    page_title="DealScope", layout="wide", initial_sidebar_state="collapsed"
)


# ----------------------------------------------------------------------------
# Formatting helpers
# ----------------------------------------------------------------------------

def indian_number(n):
    """Format a number with Indian digit grouping, e.g. 1057219 -> '10,57,219'."""
    n = int(round(n))
    negative = n < 0
    n = abs(n)
    s = str(n)
    if len(s) <= 3:
        result = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        result = ",".join(parts) + "," + last3
    return ("-" if negative else "") + result


def format_cr(raw_value):
    """Format a raw-rupee value as a full '₹X,XX,XXX Cr' string, or 'N/A'."""
    if pd.isna(raw_value):
        return "N/A"
    return f"₹{indian_number(raw_value / 1e7)} Cr"


def format_cr_plain(raw_value):
    """Format a raw-rupee value as a bare Indian-grouped crore number (for table cells)."""
    if pd.isna(raw_value):
        return "N/A"
    return indian_number(raw_value / 1e7)


def format_pct(value, decimals=1):
    if pd.isna(value):
        return "N/A"
    return f"{value:.{decimals}f}%"


def sector_display_name(bucket):
    """Short labels for the 13-sector v2 taxonomy (chips, table cells, cards)."""
    return {
        "Financial Services": "Financials",
        "Technology & IT Services": "Technology",
        "Healthcare & Lifesciences": "Healthcare",
        "Consumer Discretionary & Retail": "Consumer Disc.",
        "Consumer Staples & Agri": "Staples & Agri",
        "Automotive & Mobility": "Auto & Mobility",
        "Industrials & Capital Goods": "Industrials",
        "Metals, Mining & Materials": "Metals & Mining",
        "Energy & Utilities": "Energy & Utilities",
        "Infrastructure & Construction": "Infrastructure",
        "Real Estate": "Real Estate",
        "Telecom, Media & Entertainment": "Telecom & Media",
    }.get(bucket, bucket)


def esc(value):
    """HTML-escape any value that reaches an unsafe_allow_html block."""
    return html.escape(str(value))


# ----------------------------------------------------------------------------
# AI rationale — tries Gemini, then Groq, then Cerebras (in that order), cached
# by (symbol, as_of_date) on disk so repeat clicks and app restarts (free-tier
# sleep/wake) don't re-burn API quota on any provider. Any provider's failure
# (or empty response) falls through to the next; if all three fail, returns
# None so the PRD fallback text renders instead of crashing the tear sheet.
# ----------------------------------------------------------------------------

RATIONALE_CACHE_PATH = Path(__file__).resolve().parent / ".rationale_cache.json"
RATIONALE_CACHE_LOCK_PATH = Path(__file__).resolve().parent / ".rationale_cache.json.lock"
GEMINI_MODEL = "gemini-flash-latest"
GROQ_MODEL = "llama-3.3-70b-versatile"
CEREBRAS_MODEL = "gpt-oss-120b"


def _load_rationale_cache():
    if not RATIONALE_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(RATIONALE_CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_rationale_cache(updates):
    """Persists `updates` (only the key(s) this call just generated) into the
    on-disk cache -- never the full in-memory snapshot a caller loaded at the
    start of its own turn. Confirmed root cause of ~94 companies (SIEMENS,
    SBILIFE, SWIGGY, MUTHOOTFIN, ...) silently losing an already-successful
    generation during the unattended overnight run: this used to
    `write_text(json.dumps(cache))` with whatever full dict the caller had
    loaded minutes earlier, so if a second process had written a new entry
    in the meantime, this call's save clobbered it -- no exception, no log,
    just a lost update. Now it re-reads the file fresh and merges `updates`
    on top under an flock, so two processes racing on different companies
    both survive: the last writer merges instead of overwriting.
    """
    try:
        with open(RATIONALE_CACHE_LOCK_PATH, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                on_disk = _load_rationale_cache()
                on_disk.update(updates)
                RATIONALE_CACHE_PATH.write_text(json.dumps(on_disk))
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
    except OSError:
        pass


def _build_rationale_prompt(company_row):
    def val(field, formatter):
        v = company_row.get(field)
        return formatter(v) if pd.notna(v) else "N/A"

    factor_lines = "\n".join(
        f"- {FACTOR_LABELS[m]}: "
        + (f"{company_row[f'pctl_{m}']:.0f}th percentile" if pd.notna(company_row.get(f"pctl_{m}")) else "N/A (excluded from score, reweighted)")
        for m in METRICS
    )

    return f'''You are drafting a factual, mechanical deal-screening note for a corporate development analyst. Write exactly one paragraph (3-5 sentences). Tone: neutral, analytical, factual -- not marketing copy, not speculation. Only reference figures explicitly given below. If a figure says N/A, do not guess, estimate, or invent a value for it -- either omit it or explicitly note it is undisclosed.

Company: {company_row['name']} ({company_row['symbol']})
Sector (peer group for all percentiles below): {sector_display_name(company_row['sector_v2'])}
Composite score: {f"{company_row['score']:.0f}/100 (out of 100, sector-relative)" if pd.notna(company_row['score']) else "N/A (fewer than 2 of the 4 scoring metrics are available for this company)"}

Factor percentiles vs. sector peers:
{factor_lines}

Key financials:
- Revenue: {val('revenue', format_cr)}
- EBITDA: {val('ebitda', format_cr)}
- EBITDA Margin: {val('ebitda_margin_pct', format_pct)}
- ROCE: {val('return_on_capital_employed_pct', format_pct)}
- Total Debt: {val('total_debt', format_cr)}
- Market Cap: {val('market_cap', format_cr)}
- Promoter Pledge: {val('promoter_pledge_pct', format_pct)}

Indicative valuation range:
- EV/EBITDA implied: {val('ev_ebitda_low', format_cr)} - {val('ev_ebitda_high', format_cr)}
- P/E implied: {val('pe_implied_low', format_cr)} - {val('pe_implied_high', format_cr)}'''


# Every provider call gets an explicit, bounded timeout (no external HTTP call
# left to whatever a given SDK defaults to). A slow/unresponsive provider
# should fail fast into the next one in RATIONALE_PROVIDERS, not tie up the
# request.
AI_CALL_TIMEOUT_SECONDS = 30


def _call_gemini(api_key, prompt):
    # Imported here, not at module load, so a cold start only pays the
    # memory/import cost of whichever SDK is actually used.
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=AI_CALL_TIMEOUT_SECONDS * 1000),
    )
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return (response.text or "").strip()


def _call_groq(api_key, prompt):
    from groq import Groq

    client = Groq(api_key=api_key, timeout=AI_CALL_TIMEOUT_SECONDS)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return (response.choices[0].message.content or "").strip()


def _call_cerebras(api_key, prompt):
    from cerebras.cloud.sdk import Cerebras

    client = Cerebras(api_key=api_key, timeout=AI_CALL_TIMEOUT_SECONDS)
    response = client.chat.completions.create(
        model=CEREBRAS_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return (response.choices[0].message.content or "").strip()


RATIONALE_PROVIDERS = [
    ("Gemini", get_gemini_api_key, _call_gemini),
    ("Groq", get_groq_api_key, _call_groq),
    ("Cerebras", get_cerebras_api_key, _call_cerebras),
]


def get_ai_rationale(company_row):
    # TAXONOMY_VERSION in the key invalidates rationales generated under an
    # older sector taxonomy -- cached texts bake in the old peer-group names
    # and percentiles, which changed for ~39% of companies in v2.
    cache_key = f"{company_row['symbol']}|{company_row['as_of_date']}|{TAXONOMY_VERSION}"
    cache = _load_rationale_cache()
    if cache_key in cache:
        cached = cache[cache_key]
        # get_ai_analysis() (below) stores a {about, why_this_score, ...} dict
        # under the same cache_key/file. A plain string is still the only
        # shape this function ever wrote itself; a dict means some other
        # process already re-generated this company under the new schema, so
        # prefer its why_this_score (the genuine rewrite) over a stale
        # `rationale` string.
        if isinstance(cached, dict):
            return cached.get("why_this_score") or cached.get("rationale")
        return cached

    prompt = _build_rationale_prompt(company_row)
    for _name, key_getter, call_fn in RATIONALE_PROVIDERS:
        api_key = key_getter()
        if not api_key:
            continue
        try:
            text = call_fn(api_key, prompt)
            if not text:
                continue
        except Exception:
            continue

        cache[cache_key] = text
        _save_rationale_cache({cache_key: text})
        return text

    return None


def _build_analysis_prompt(company_row):
    """Like _build_rationale_prompt(), but asks for two fields in one call:
    a plain factual "about" description and a "why_this_score" explanation
    that has to actually use the factor percentiles below rather than
    restating them. Same inputs, same N/A discipline -- only the instructions
    and the requested output shape differ.
    """
    def val(field, formatter):
        v = company_row.get(field)
        return formatter(v) if pd.notna(v) else "N/A"

    factor_lines = "\n".join(
        f"- {FACTOR_LABELS[m]}: "
        + (f"{company_row[f'pctl_{m}']:.0f}th percentile" if pd.notna(company_row.get(f"pctl_{m}")) else "N/A (excluded from score, reweighted)")
        for m in METRICS
    )

    return f'''You are drafting two short, factual notes for a corporate development analyst screening acquisition targets. Respond with ONLY a valid JSON object -- no markdown code fences, no commentary before or after it -- in exactly this shape:
{{"about": "...", "why_this_score": "..."}}

"about": 2-4 sentences, plain and factual. What the company actually does -- sector, product or service, who it sells to. Not scored, not evaluative, no opinion on quality or prospects.

"why_this_score": 3-5 sentences that actually explain the composite score using the real factor percentiles below. Name the 2-3 factors driving it up or down and say what that means in plain terms for the business -- do not just restate the percentile numbers back. Tone for both fields: neutral, analytical, factual -- not marketing copy, not speculation. Only reference figures explicitly given below; if a figure says N/A, do not guess, estimate, or invent a value for it -- either omit it or explicitly note it is undisclosed.

Company: {company_row['name']} ({company_row['symbol']})
Sector (peer group for all percentiles below): {sector_display_name(company_row['sector_v2'])}
Composite score: {f"{company_row['score']:.0f}/100 (out of 100, sector-relative)" if pd.notna(company_row['score']) else "N/A (fewer than 2 of the 4 scoring metrics are available for this company)"}

Factor percentiles vs. sector peers:
{factor_lines}

Key financials:
- Revenue: {val('revenue', format_cr)}
- EBITDA: {val('ebitda', format_cr)}
- EBITDA Margin: {val('ebitda_margin_pct', format_pct)}
- ROCE: {val('return_on_capital_employed_pct', format_pct)}
- Total Debt: {val('total_debt', format_cr)}
- Market Cap: {val('market_cap', format_cr)}
- Promoter Pledge: {val('promoter_pledge_pct', format_pct)}

Indicative valuation range:
- EV/EBITDA implied: {val('ev_ebitda_low', format_cr)} - {val('ev_ebitda_high', format_cr)}
- P/E implied: {val('pe_implied_low', format_cr)} - {val('pe_implied_high', format_cr)}'''


def _parse_analysis_response(text):
    """Best-effort parse of a provider's response into {about, why_this_score}.
    Strips a markdown code fence if a model adds one despite being told not
    to. Returns None (never a partial dict) if parsing fails or either field
    is missing/empty, so a malformed response is treated as this provider
    failing -- same as get_ai_rationale() treating empty text as failure --
    and the caller falls through to the next provider in RATIONALE_PROVIDERS.
    """
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    about = str(data.get("about") or "").strip()
    why = str(data.get("why_this_score") or "").strip()
    if not about or not why:
        return None
    return {"about": about, "why_this_score": why}


def get_ai_analysis(company_row):
    """Two-field version of get_ai_rationale(): "about" (factual company
    description) + "why_this_score" (factor-based score explanation) from a
    single call per provider, using the exact same RATIONALE_PROVIDERS
    fallback chain, per-provider try/except-and-continue behavior, and cache
    file -- only the prompt and the parsed response shape are new.

    Returns the cached/generated {about, why_this_score} dict, or None if
    every provider failed or returned something unparseable.
    """
    cache_key = f"{company_row['symbol']}|{company_row['as_of_date']}|{TAXONOMY_VERSION}"
    cache = _load_rationale_cache()
    existing = cache.get(cache_key)
    if isinstance(existing, dict) and existing.get("about") and existing.get("why_this_score"):
        return existing

    # Pre-taxonomy-v2 entries were cached under the un-versioned "symbol|date"
    # key (no TAXONOMY_VERSION segment) by the original get_ai_rationale(),
    # before that key format existed. That old rationale is still worth
    # keeping as a fallback/reference even though its peer-group percentiles
    # may now be stale -- carried into the new entry below, never copied into
    # why_this_score, which is always a fresh generation.
    legacy_key = f"{company_row['symbol']}|{company_row['as_of_date']}"
    legacy_rationale = cache.get(legacy_key) if isinstance(cache.get(legacy_key), str) else None

    prompt = _build_analysis_prompt(company_row)
    for _name, key_getter, call_fn in RATIONALE_PROVIDERS:
        api_key = key_getter()
        if not api_key:
            continue
        try:
            text = call_fn(api_key, prompt)
        except Exception:
            continue
        result = _parse_analysis_response(text)
        if result is None:
            continue

        # Extend the existing entry rather than clobber it -- a legacy
        # string-only rationale (pre-dating this change) is kept under
        # "rationale" as a fallback/reference, not overwritten; why_this_score
        # is always the fresh generation from this call, never copied from it.
        if isinstance(existing, dict):
            entry = dict(existing)
        elif isinstance(existing, str):
            entry = {"rationale": existing}
        elif legacy_rationale:
            entry = {"rationale": legacy_rationale}
        else:
            entry = {}
        entry["about"] = result["about"]
        entry["why_this_score"] = result["why_this_score"]
        cache[cache_key] = entry
        _save_rationale_cache({cache_key: entry})
        return entry

    return None


# ----------------------------------------------------------------------------
# Cached data pipeline
# ----------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_universe():
    """load_companies() + valuation_range() on the full universe. Weight-independent.

    Peer groups use the 13-sector v2 taxonomy (sector_v2 column).
    """
    df = load_companies()
    df = compute_zscore(df)
    df = compute_piotroski(df)
    df = valuation_range(df, bucket_col="sector_v2")
    return df


@st.cache_data(show_spinner=False)
def score_universe(df, weights_tuple):
    weights = dict(weights_tuple)
    return score_companies(df, weights, bucket_col="sector_v2")


@st.cache_data(show_spinner=False)
def load_all_deals(taxonomy_version=TAXONOMY_VERSION):
    # taxonomy_version is part of the cache key: load_deals() derives
    # sector_v2, and st.cache_data only watches THIS function's body/args --
    # without the explicit key a taxonomy change would serve stale deals.
    return load_deals()


@st.cache_data(show_spinner=False)
def sector_avg_scores(scored):
    """Mean composite score within each v2 sector, for the ring's sector tick."""
    return scored.groupby("sector_v2")["score"].mean().to_dict()


# ----------------------------------------------------------------------------
# CSS
# ----------------------------------------------------------------------------

def inject_css():
    panel_open = st.query_params.get("panel") == "1"
    modal_display = "flex" if panel_open else "none"
    css = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {{ --r-card: 10px; --r-ctrl: 8px; }}
/* Type system: Inter carries all UI text (labels, prose, buttons, headings);
   IBM Plex Mono is reserved for NUMERIC DATA only — figures, scores, tickers,
   percentages. Data cells opt into mono via an inline 'IBM Plex Mono' family,
   which the higher-specificity rule below re-asserts over the Inter blanket.
   This mono-for-numbers / sans-for-everything split is what reads as a real
   product rather than a terminal dump. */
html, body, [class*="css"], .stApp, .stApp * {{
    font-family: 'Inter', -apple-system, system-ui, sans-serif !important;
    color: {C_T1};
    -webkit-font-smoothing: antialiased;
}}
.stApp [style*="Plex Mono"], .stApp [style*="Plex Mono"] * {{
    font-family: 'IBM Plex Mono', ui-monospace, 'SF Mono', monospace !important;
    font-feature-settings: 'tnum' 1;
}}
/* Streamlit's native chrome (expander chevron, etc.) renders via Material
   Symbols ligature text (e.g. "keyboard_arrow_right") -- keep its icon font. */
[data-testid="stIconMaterial"] {{ font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important; }}
.stApp {{ background: {C_BG}; }}
#MainMenu, header[data-testid="stHeader"], footer, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display: none !important; }}
[data-testid="collapsedControl"] {{ display: none !important; }}
section[data-testid="stSidebar"] {{ display: none !important; }}
/* Narrower centered column with real side gutters — content no longer fills
   the whole laptop width edge-to-edge, which is what made it feel "zoomed in". */
.block-container {{ padding: 0 28px 4rem; max-width: 1200px; }}
a {{ color: {C_TEAL} !important; text-decoration: none !important; }}
hr {{ border-color: {C_BORDER}; }}

/* Soft, approachable rounding on interactive controls. */
div.stButton > button, div.stFormSubmitButton > button, div.stDownloadButton > button,
div[data-testid="stLinkButton"] > a, div[data-testid="stTextInput"] input,
div[data-baseweb="select"] > div, .sd-search-row {{ border-radius: var(--r-ctrl) !important; }}

/* Generic buttons */
div.stButton > button, div.stFormSubmitButton > button {{
    background: transparent; color: {C_T3}; border: 1px solid {C_BORDER};
    font-weight: 600; font-size: 11.5px; padding: 10px 14px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
div.stButton > button:hover, div.stFormSubmitButton > button:hover {{
    border-color: {C_BORDER2}; color: {C_T1};
}}
/* Selected sector chip = primary button */
div.stButton > button[kind="primary"], div.stButton > button[data-testid="baseButton-primary"] {{
    background: {C_TEAL_DK}; color: {C_TEAL}; border: 1px solid {C_TEAL}; font-weight: 700;
}}
div.stButton > button[kind="primary"]:hover {{ background: {C_TEAL_DK}; color: {C_TEAL}; }}

div.stDownloadButton > button {{
    background: transparent; color: {C_T3}; border: 1px solid {C_BORDER};
    font-weight: 400; font-size: 11.5px; padding: 10px 14px; white-space: nowrap;
}}
div.stDownloadButton > button:hover {{ color: {C_T1}; border-color: {C_BORDER2}; }}
div.stFormSubmitButton > button {{
    background: {C_TEAL} !important; color: {C_INK} !important; border: none !important;
    font-weight: 700; font-size: 12.5px; letter-spacing: .06em; padding: 12px 22px;
}}
div.stFormSubmitButton > button:hover {{ opacity: .85; }}

/* Link button (Share) */
div[data-testid="stLinkButton"] > a {{
    background: transparent; color: {C_T3}; border: 1px solid {C_BORDER};
    font-weight: 400; font-size: 11.5px; padding: 10px 14px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-height: 0;
}}
div[data-testid="stLinkButton"] > a:hover {{ color: {C_T1}; border-color: {C_BORDER2}; }}

/* "FILTERS" trigger button: outlined in accent, distinct from the neutral
   secondary buttons above. */
[class*="st-key-open_adv"] button, [class*="st-key-land_adv"] button {{
    background: transparent !important; color: {C_TEAL} !important;
    border: 1px solid {C_TEAL} !important; font-weight: 700 !important;
    font-size: 11.5px !important; letter-spacing: .06em; padding: 10px 18px !important;
}}
[class*="st-key-open_adv"] button:hover, [class*="st-key-land_adv"] button:hover {{ background: {C_TEAL_DK} !important; }}

/* Sector chips: 999px pill (the design system's one explicit chip exception
   to the zero-radius rule). Wrap the label to a second line instead of
   hard-clipping mid-word. !important + inner-element targeting is needed to
   beat the higher-specificity generic-button rule and Streamlit's own
   nowrap on the label div. Equal-height keeps the chip row aligned when one
   label wraps. */
[class*="st-key-chip_"] button, [class*="st-key-chip_"] button * {{
    white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
    word-break: break-word !important; hyphens: auto !important;
}}
[class*="st-key-chip_"] button, [class*="st-key-chip_"] button[kind] {{
    line-height: 1.2; height: 100%; min-height: 34px; padding: 5px 14px !important;
    font-size: 12.5px; font-weight: 500; letter-spacing: normal; display: flex; align-items: center;
    justify-content: center; text-align: center; border-radius: 999px !important;
    background: transparent; color: {C_T2}; border: 1px solid {C_BORDER};
}}
[class*="st-key-chip_"] button:hover {{ border-color: {C_BORDER2}; }}
div.stButton > button[kind="primary"][class], [class*="st-key-chip_"] button[kind="primary"] {{
    background: {C_TEAL_DK} !important; color: {C_TEAL} !important; border: 1px solid {C_TEAL} !important;
}}

/* Text input */
div[data-testid="stTextInput"] input {{
    background: transparent; border: none; color: {C_T1}; font-size: 13px; padding: 14px 4px;
}}
div[data-testid="stTextInput"] input::placeholder {{ color: {C_T3}; }}
div[data-testid="stTextInput"] input:focus {{ box-shadow: none; }}
/* Results-toolbar search gets its own bordered shell (landing's is .sd-search-row) */
[class*="st-key-results_search"] {{ border: 1px solid {C_BORDER}; background: {C_CARD}; }}
[class*="st-key-results_search"]:focus-within {{ border-color: {C_BORDER2}; }}

/* Sliders -> mint accent (kept only for the 4 factor-weight controls) */
div[data-testid="stSlider"] [data-baseweb="slider"] > div > div {{ background: {C_TEAL} !important; }}
div[data-testid="stSlider"] [role="slider"] {{ background: {C_TEAL} !important; border-color: {C_TEAL} !important; }}
div[data-testid="stSlider"] [data-testid="stTickBarMin"],
div[data-testid="stSlider"] [data-testid="stTickBarMax"] {{ color: {C_T3}; }}

/* Select dropdowns — the new, easier filter control (replaced range sliders) */
div[data-baseweb="select"] > div {{
    background: {C_CARD2} !important; border: 1px solid {C_BORDER} !important;
    font-size: 13px !important; min-height: 40px;
}}
div[data-baseweb="select"] > div:hover {{ border-color: {C_BORDER2} !important; }}
div[data-baseweb="select"] div {{ color: {C_T1} !important; }}
div[data-baseweb="popover"] li {{ font-size: 13px !important; }}
div[data-baseweb="popover"] [aria-selected="true"] {{ background: {C_TEAL_DK} !important; color: {C_TEAL} !important; }}

/* Multiselect (sectors, when used) */
div[data-testid="stMultiSelect"] [data-baseweb="tag"] {{ background: {C_TEAL_DK}; border-radius: 999px; }}

/* Toggle switch (Financial Health filter section) — one of the three
   explicit radius exceptions in the design system. */
div[data-testid="stCheckbox"] label div[data-testid="stMarkdownContainer"] {{ font-size: 12.5px; }}
div[data-testid="stCheckbox"] span[data-baseweb="checkbox"] > div {{
    border-radius: 999px !important; background: {C_CARD2} !important; border-color: {C_BORDER2} !important;
}}
div[data-testid="stCheckbox"] input:checked ~ span[data-baseweb="checkbox"] > div {{
    background: {C_TEAL} !important; border-color: {C_TEAL} !important;
}}

/* ---- Advanced Filters: centered modal (spec: instant appear/disappear,
   no slide transition, backdrop click / × / Escape all dismiss) ---- */
#dwr-scrim {{
    position: fixed; inset: 0; background: rgba(0,0,0,.65); z-index: 998;
    display: {modal_display}; align-items: center; justify-content: center;
}}
.st-key-filterdrawer {{
    position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: 640px; max-width: 90vw; max-height: 85vh; z-index: 999;
    background: {C_CARD}; border: 1px solid {C_BORDER2};
    box-shadow: 0 24px 64px rgba(0,0,0,.5);
    padding: 22px 26px; overflow-y: auto;
    display: {modal_display}; flex-direction: column;
}}
.st-key-filterdrawer .stSlider {{ margin-bottom: -6px; }}

.dwr-title {{ font-size: 13px; font-weight: 700; letter-spacing: .06em; color: {C_T1}; }}
.dwr-grouplabel {{ font-size: 11.5px; letter-spacing: .05em; color: {C_T1}; font-weight: 700;
    margin: 18px 0 6px; padding-top: 12px; border-top: 1px solid {C_BORDER}; }}
.dwr-grouplabel:first-of-type {{ border-top: none; padding-top: 0; }}
.dwr-fieldlabel {{ display: flex; justify-content: space-between; align-items: center;
    font-size: 10.5px; letter-spacing: .05em; color: {C_T3}; font-weight: 600; margin-bottom: -6px; }}
.dwr-fieldval {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: {C_TEAL}; font-weight: 500; }}

/* Filters trigger badge — the second explicit radius exception. */
.sd-filter-badge {{ display: inline-block; background: {C_TEAL}; color: {C_INK};
    border-radius: 999px; padding: 1px 6px; font: 700 10px 'IBM Plex Mono', monospace; margin-left: 6px; }}

/* Wordmark */
.brand {{ display: flex; align-items: center; gap: 8px; }}
.brand-dot {{ width: 8px; height: 8px; background: {C_TEAL}; }}
.brand-name {{ font-weight: 700; font-size: 14px; letter-spacing: .16em; color: {C_T1}; }}

.sd-masthead {{ display: flex; justify-content: space-between; align-items: center; gap: 16px;
    height: 56px; margin: 0 -32px 24px; padding: 0 32px; border-bottom: 1px solid {C_BORDER};
    position: sticky; top: 0; z-index: 50; background: {C_BG}; }}
.sd-mast-left {{ display: flex; align-items: center; gap: 28px; min-width: 0; }}
.sd-wordmark {{ font-size: 14px; font-weight: 700; letter-spacing: .16em; color: {C_T1} !important; text-decoration: none !important; }}
.sd-nav-divider {{ width: 1px; height: 14px; background: {C_BORDER}; }}
.sd-nav-link {{ font-size: 12.5px; color: {C_T3} !important; text-decoration: none !important; }}
.sd-nav-link.active {{ color: {C_T1} !important; }}
.sd-mast-right {{ display: flex; align-items: center; gap: 12px; }}
.sd-snapshot-tag {{ font-size: 10.5px; letter-spacing: .06em; color: {C_T1}; border: 1px solid {C_BORDER}; padding: 4px 8px; }}

.sd-hero {{ display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 54px 40px 40px; }}
.sd-hero-kicker {{ font-size: 11px; color: {C_TEAL}; letter-spacing: .14em; margin-bottom: 18px; text-align: center; text-transform: uppercase; }}
.sd-hero-title {{ font-size: 38px; font-weight: 800; line-height: 1.12; text-align: center;
    max-width: 620px; margin: 0 0 16px; letter-spacing: -.02em; }}
.sd-hero-sub {{ font-size: 15px; color: {C_T3}; line-height: 1.65; text-align: center; max-width: 520px; margin: 0 auto 30px; }}
.sd-search-shell {{ width: min(720px, 100%); margin: 0 auto; }}
.sd-search-row {{ display: flex; align-items: center; gap: 10px; border: 1px solid {C_BORDER2}; background: {C_CARD}; padding: 0 6px 0 18px; }}
.sd-search-prompt {{ color: {C_T3}; font-size: 16px; white-space: nowrap; }}
.sd-search-input input {{ padding: 15px 4px !important; font-size: 14px !important; }}
.sd-search-submit button {{ background: {C_TEAL} !important; color: {C_INK} !important; border: none !important;
    padding: 12px 22px !important; font-weight: 700 !important; font-size: 12.5px !important; letter-spacing: .06em; }}
.sd-search-submit button:hover {{ opacity: .85; }}
.sd-hero-actions {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 20px; }}
.sd-hero-stats {{ display: flex; justify-content: center; align-items: center; gap: 16px; margin-top: 30px; flex-wrap: wrap; }}
.sd-hero-stat {{ font-size: 11px; color: {C_T3}; }}
.sd-hero-stat strong {{ color: {C_T1}; }}

/* Stat-card grids: class-based so a media query can reflow them (inline grid
   styles can't be overridden by @media — they win on specificity). Hairline
   grid via 1px gap over a border-colored background; rounded outer corners. */
.sd-grid4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; background: {C_BORDER};
    border: 1px solid {C_BORDER}; border-radius: var(--r-card); overflow: hidden; }}
.sd-grid3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: {C_BORDER};
    border: 1px solid {C_BORDER}; border-radius: var(--r-card); overflow: hidden; }}

/* Results table can't crush its fixed-width numeric columns; on narrow screens
   it scrolls horizontally inside its own card instead of breaking page layout. */
.sd-table-scroll {{ overflow-x: auto; }}
.sd-table-inner {{ min-width: 680px; }}

/* Tear-sheet two-column body */
.sd-tearbody {{ display: grid; grid-template-columns: 1fr 1fr; gap: 32px; align-items: start; }}
.sd-section-title {{ font-size: 12px; font-weight: 700; letter-spacing: .08em; color: {C_T3};
    text-transform: uppercase; padding-top: 8px; margin: 0 0 12px; }}

/* Clickable feed rows (regulatory filings, BSE notices, news) — each row is
   an <a> to the official source, opening in a new tab. Title turns mint on
   hover to signal it's a real link. */
.sd-feed .sd-feed-row {{ display: block; padding: 11px 16px; border-bottom: 1px solid {C_BORDER}; }}
.sd-feed .sd-feed-row:last-child {{ border-bottom: none; }}
.sd-feed .sd-feed-row:hover {{ background: {C_CARD2}; }}
.sd-feed .sd-feed-title {{ font-size: 13px; font-weight: 600; color: {C_T1} !important;
    margin-bottom: 3px; line-height: 1.45; }}
.sd-feed .sd-feed-row:hover .sd-feed-title {{ color: {C_TEAL} !important; }}
.sd-feed .sd-feed-meta {{ font-size: 11px; color: {C_T4} !important; }}
.sd-feed .sd-feed-ext {{ color: {C_T5} !important; font-weight: 400; }}

/* ---- Responsive (Streamlit's own column stacking below ~640px still
   applies regardless; these rules just prevent the fixed-width layout from
   causing horizontal page scroll on a narrower viewport) ---- */
@media (max-width: 1024px) {{
    .block-container {{ padding: 0 20px 3rem; }}
    .sd-masthead {{ margin: 0 -20px 24px; padding: 0 20px; }}
}}
@media (max-width: 640px) {{
    .sd-grid4 {{ grid-template-columns: repeat(2, 1fr); }}
    .sd-tearbody {{ grid-template-columns: 1fr; }}
    .sd-tearhead {{ flex-direction: column; align-items: flex-start !important; gap: 18px; }}
    .sd-masthead {{ flex-direction: column; height: auto; align-items: flex-start; padding: 12px 20px; }}
    .sd-hero-title {{ font-size: 32px; }}
    .sd-search-row {{ flex-wrap: wrap; }}
    .sd-search-submit {{ width: 100%; }}
}}
</style>
"""
    css = "\n".join(line for line in css.splitlines() if line.strip())
    st.markdown(css, unsafe_allow_html=True)
    st.markdown('<div id="dwr-scrim"></div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# HTML component renderers
# ----------------------------------------------------------------------------

def ring_html(score, sector_avg, size=34, inner_bg=C_CARD, font_size=10.5,
              show_label=False, glow=False):
    """Score ring: teal arc = score, white tick = sector-average score."""
    thickness = max(3, round(size * 0.09))
    if pd.isna(score):
        # Unscored: flat faint ring, em-dash.
        num = "–"
        arc = f"background:rgba(255,255,255,.06)"
        tick = ""
        num_color = C_T6
    else:
        deg = max(0, min(360, score / 100 * 360))
        arc = f"background:conic-gradient({C_TEAL} 0deg {deg}deg,rgba(255,255,255,.1) {deg}deg 360deg)"
        num = f"{score:.0f}"
        num_color = C_T1
        tick = ""
        if pd.notna(sector_avg):
            tick_deg = max(0, min(360, sector_avg / 100 * 360))
            tick = (f'<div style="position:absolute;inset:0;transform:rotate({tick_deg:.1f}deg)">'
                    f'<div style="position:absolute;top:0;left:50%;width:2px;height:{max(5, round(size*0.18))}px;'
                    f'background:{C_T1};border-radius:0;transform:translateX(-50%)"></div></div>')
    glow_css = f"box-shadow:0 0 40px -8px rgba(31,184,163,.5);" if glow and pd.notna(score) else ""
    label = (f'<div style="font:700 8px Inter,sans-serif;letter-spacing:.1em;color:{C_T5}">SCORE</div>'
             if show_label else "")
    return (f'<div style="position:relative;width:{size}px;height:{size}px;border-radius:50%;{glow_css}">'
            f'<div style="position:absolute;inset:0;border-radius:50%;{arc}"></div>'
            f'{tick}'
            f'<div style="position:absolute;inset:{thickness}px;border-radius:50%;background:{inner_bg};'
            f'display:flex;flex-direction:column;align-items:center;justify-content:center">'
            f'<div style="font:700 {font_size}px \'IBM Plex Mono\',monospace;color:{num_color};line-height:1">{num}</div>'
            f'{label}</div></div>')


def stat_card(label, value, value_color=C_T1, small=False):
    pad = "14px 16px" if small else "18px 20px"
    lbl_size = "9.5px" if small else "10px"
    val_size = "14px" if small else "18px"
    return (f'<div style="padding:{pad};background:{C_CARD2};'
            f'border:1px solid {C_BORDER}">'
            f'<div style="font:700 {lbl_size} Inter,sans-serif;letter-spacing:.05em;color:{C_T5};margin-bottom:{"5px" if small else "7px"}">{esc(label)}</div>'
            f'<div style="font:700 {val_size} \'IBM Plex Mono\',monospace;color:{value_color}">{esc(value)}</div></div>')


def key_financial_row(label, value):
    """One label/value row for the tear sheet's plain-list Key Financials
    block (as opposed to stat_card()'s boxed-card treatment)."""
    color = C_T1 if value != "N/A" else C_T5
    return (f'<div style="display:flex;justify-content:space-between;padding:11px 16px;'
            f'border-bottom:1px solid {C_BORDER};font-size:12.5px">'
            f'<span style="color:{C_T3}">{esc(label)}</span>'
            f'<span style="font-weight:600;color:{color}">{esc(value)}</span></div>')


def breakdown_bar_html(label, weight, percentile):
    wt = f'<span style="color:{C_T5};font-weight:400">wt {weight}</span>'
    if pd.isna(percentile):
        return (f'<div><div style="display:flex;justify-content:space-between;margin-bottom:6px">'
                f'<span style="font:600 12.5px Inter,sans-serif;color:{C_T5}">{label} {wt}</span>'
                f'<span style="font:600 11.5px Inter,sans-serif;color:{C_T5}">reweighted — no data</span></div>'
                f'<div style="height:7px;border-radius:0;background:rgba(255,255,255,.04)"></div></div>')
    pct = max(0, min(100, percentile))
    return (f'<div><div style="display:flex;justify-content:space-between;margin-bottom:6px">'
            f'<span style="font:600 12.5px Inter,sans-serif;color:{C_T2}">{label} {wt}</span>'
            f'<span style="font:700 12.5px \'IBM Plex Mono\',monospace;color:{C_TEAL_LT}">{pct:.0f}</span></div>'
            f'<div style="height:7px;border-radius:0;background:rgba(255,255,255,.08)">'
            f'<div style="width:{pct}%;height:100%;border-radius:0;background:{C_TEAL}"></div></div></div>')


def extract_note_segment(full_note, prefix):
    """Pull just this method's reason out of valuation_range()'s combined valuation_note."""
    if not full_note or prefix not in full_note:
        return "Insufficient sector peer data to compute this range."
    rest = full_note[full_note.index(prefix) + len(prefix):].strip()
    for other_prefix in ("EV/EBITDA:", "P/E:"):
        if other_prefix != prefix and other_prefix in rest:
            rest = rest.split(other_prefix)[0].strip()
    return rest if rest.endswith(".") else rest + "."


# ----------------------------------------------------------------------------
# Query params <-> filter/weight state
# ----------------------------------------------------------------------------

def qp_float_pair(key, default):
    raw = st.query_params.get(key)
    if not raw:
        return default
    try:
        lo, hi = raw.split(",")
        return (float(lo), float(hi))
    except (ValueError, AttributeError):
        return default


def qp_float(key, default):
    raw = st.query_params.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def qp_int(key, default):
    raw = st.query_params.get(key)
    if raw is None:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


# Multi-value query params join on "|", not ",": two v2 bucket names contain
# literal commas ("Telecom, Media & Entertainment", "Metals, Mining &
# Materials"), so a comma separator would split the names themselves.
QP_LIST_SEP = "|"


def qp_list(key, default):
    raw = st.query_params.get(key)
    if raw is None:
        return default
    return [s for s in raw.split(QP_LIST_SEP) if s]


def current_sectors():
    """Selected sectors from the URL; empty list means 'all sectors'."""
    sel = [s for s in qp_list("sectors", []) if s in SECTOR_V2_BUCKETS]
    return sel


def current_weights():
    return {m: qp_int(f"w_{m}", 5) for m in METRICS}


def preserved_href(**overrides):
    """Build an href that keeps the current filter/weight/search state.

    The results table's row links and the "how scoring works" link are plain
    <a> tags (hard navigation), so unlike go() they don't automatically carry
    the existing query string. Without this, clicking into a tear sheet dropped
    every active filter, sector, weight, and search term from the URL — and the
    tear sheet's own score then silently fell back to default weights. We start
    from the live params, drop the routing-only keys, apply the overrides, and
    URL-encode everything (so a value containing '&', spaces, etc. can't corrupt
    the link).
    """
    params = {k: v for k, v in st.query_params.to_dict().items()
              if k not in ("view", "symbol", "panel")}
    for k, v in overrides.items():
        if v is None:
            params.pop(k, None)
        else:
            params[k] = v
    return "?" + urlencode(params)


# ----------------------------------------------------------------------------
# Shared UI pieces
# ----------------------------------------------------------------------------

def brand_markup():
    return (f'<div class="brand"><div class="brand-dot"></div>'
            f'<div class="brand-name">DEALSCOPE</div></div>')


def render_masthead(universe, active_view="landing"):
    as_of = get_data_as_of(universe)
    landing_href = preserved_href(view="landing", q=None, page=None, symbol=None, panel=None)
    results_href = preserved_href(view="results", symbol=None, panel=None)
    scoring_href = preserved_href(view="scoring", symbol=None, panel=None)
    st.markdown(f'''
<div class="sd-masthead">
    <div class="sd-mast-left">
        <a class="sd-wordmark" href="{landing_href}" target="_self">DEALSCOPE</a>
        <div class="sd-nav-divider"></div>
        <a class="sd-nav-link{' active' if active_view == 'results' else ''}" href="{results_href}" target="_self">Screener</a>
        <a class="sd-nav-link{' active' if active_view == 'scoring' else ''}" href="{scoring_href}" target="_self">Methodology</a>
    </div>
    <div class="sd-mast-right">
        <div class="sd-snapshot-tag">DATA SNAPSHOT · {esc(as_of)}</div>
    </div>
</div>''', unsafe_allow_html=True)


def go(view=None, **params):
    """Mutate query params then rerun (used by buttons)."""
    if view is not None:
        st.query_params["view"] = view
    for k, v in params.items():
        if v is None:
            st.query_params.pop(k, None)
        else:
            st.query_params[k] = v
    st.rerun()


def render_sector_chips(target_view, universe=None):
    """Sector chips as toggle buttons with counts."""
    selected = set(current_sectors())
    if universe is not None and "sector_v2" in universe.columns:
        sector_counts = universe["sector_v2"].value_counts(dropna=False).to_dict()
    else:
        sector_counts = {}
    labels = []
    for bucket in SECTOR_V2_BUCKETS:
        label = sector_display_name(bucket)
        count = int(sector_counts.get(bucket, 0))
        labels.append((bucket, f"{label} ({count})" if count else label))
    split = (len(labels) + 1) // 2
    for row_labels in (labels[:split], labels[split:]):
        cols = st.columns(len(row_labels))
        for (bucket, label), col in zip(row_labels, cols):
            is_on = bucket in selected
            if col.button(label, key=f"chip_{bucket}",
                          type="primary" if is_on else "secondary",
                          use_container_width=True):
                if is_on:
                    selected.discard(bucket)
                else:
                    selected.add(bucket)
                new = QP_LIST_SEP.join(b for b in SECTOR_V2_BUCKETS if b in selected)
                go(target_view, sectors=new or None, page=None)


def _preset_index(param_key, n_options):
    """Saved dropdown index from the URL (default 0 = 'Any'), clamped valid."""
    idx = qp_int(param_key, 0)
    return idx if 0 <= idx < n_options else 0


def _bounds_to_filter(bounds):
    """Turn a preset's (raw_lo|None, raw_hi|None) into a concrete (lo, hi)
    pair Series.between() can use — None becomes an open ±inf edge."""
    lo, hi = bounds
    return (lo if lo is not None else float("-inf"),
            hi if hi is not None else float("inf"))


def render_filter_drawer(universe):
    """Centered filter modal built from easy preset-bucket DROPDOWNS (no
    fiddly range sliders) plus the 4 factor-weight sliders. Always rendered on
    the results view so its state is readable every run; CSS hides it
    (display:none) unless ?panel=1."""
    picks = {}  # widget key -> chosen option index

    def dropdown(container, key, label, options):
        opt_labels = [o[0] for o in options]
        default_idx = _preset_index(f"f_{key}", len(options))
        with container:
            chosen = st.selectbox(label, opt_labels, index=default_idx, key=f"sb_{key}")
        picks[key] = opt_labels.index(chosen)

    with st.container(key="filterdrawer"):
        hc1, hc2 = st.columns([6, 1])
        with hc1:
            st.markdown('<span class="dwr-title">FILTERS</span>', unsafe_allow_html=True)
        with hc2:
            if st.button("×", key="dwr_close", use_container_width=True):
                go("results", panel=None)

        st.markdown('<div class="dwr-grouplabel" style="border-top:none;padding-top:0">SIZE</div>', unsafe_allow_html=True)
        row = st.columns(2)
        dropdown(row[0], "market_cap", *FILTER_PRESETS["market_cap"])
        dropdown(row[1], "revenue", *FILTER_PRESETS["revenue"])

        st.markdown('<div class="dwr-grouplabel">PROFITABILITY &amp; LEVERAGE</div>', unsafe_allow_html=True)
        row = st.columns(2)
        dropdown(row[0], "ebitda_margin_pct", *FILTER_PRESETS["ebitda_margin_pct"])
        dropdown(row[1], "return_on_capital_employed_pct", *FILTER_PRESETS["return_on_capital_employed_pct"])
        row = st.columns(2)
        dropdown(row[0], "total_debt", *FILTER_PRESETS["total_debt"])
        dropdown(row[1], "pledge", *PLEDGE_PRESETS)

        st.markdown('<div class="dwr-grouplabel">FINANCIAL HEALTH</div>', unsafe_allow_html=True)
        dropdown(st.container(), "health", *FIN_HEALTH_PRESETS)

        st.markdown('<div class="dwr-grouplabel">FACTOR WEIGHTS</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:11px;color:{C_T3};margin:-4px 0 8px;line-height:1.5">'
                    f'How much each factor counts toward the 0–100 score. '
                    f'<a href="{esc(preserved_href(view="scoring"))}" target="_self">How scoring works</a></div>',
                    unsafe_allow_html=True)
        weights = {}
        wr = st.columns(2)
        for i, metric in enumerate(METRICS):
            with wr[i % 2]:
                weights[metric] = st.slider(
                    FACTOR_LABELS[metric], min_value=0, max_value=10,
                    value=qp_int(f"w_{metric}", 5), step=1, key=f"w_{metric}",
                )

        c1, c2 = st.columns(2)
        if c1.button("Reset all", key="dwr_reset", use_container_width=True):
            for k in FILTER_QP_KEYS + [f"w_{m}" for m in METRICS]:
                st.query_params.pop(k, None)
            for k in FILTER_WIDGET_KEYS + [f"w_{m}" for m in METRICS]:
                st.session_state.pop(k, None)
            st.query_params.pop("panel", None)
            st.rerun()
        if c2.button("Apply", key="dwr_apply", type="primary", use_container_width=True):
            st.query_params.pop("panel", None)
            st.rerun()

    # ---- persist picks to the URL every run (shareable + survives reload) ----
    for key, idx in picks.items():
        st.query_params[f"f_{key}"] = str(idx)
    for metric in METRICS:
        st.query_params[f"w_{metric}"] = str(weights[metric])

    # ---- translate picks into the dicts the pipeline consumes ----
    # bucket_filters (mcap/revenue/margin/roce/debt) are applied by
    # apply_bucket_filters() which EXCLUDES rows with no value on the filtered
    # field: when a user explicitly asks for "Mega caps", a company whose
    # market cap is unknown can't honestly be claimed to be one. (Promoter
    # pledge is the deliberate exception — missing pledge ≈ unpledged, so it
    # keeps filter_companies()'s NaN-passes ceiling semantics.)
    bucket_filters = {}
    active_count = 0
    for field in FILTER_PRESET_FIELDS:
        bounds = FILTER_PRESETS[field][1][picks[field]][1]
        if bounds is not None:
            bucket_filters[field] = _bounds_to_filter(bounds)
            active_count += 1

    pledge_ceiling = PLEDGE_PRESETS[1][picks["pledge"]][1]
    if pledge_ceiling is not None:
        active_count += 1

    fh_choice = FIN_HEALTH_PRESETS[1][picks["health"]][1]
    if fh_choice:
        active_count += 1
    fh_filters = {
        "min_fscore": fh_choice.get("min_fscore", 0),
        "safe_only": fh_choice.get("safe_only", False),
        "exclude_distress": fh_choice.get("exclude_distress", False),
    }

    filters = {"sectors": current_sectors(), "sector_col": "sector_v2"}
    if pledge_ceiling is not None:
        filters["promoter_pledge_pct_max"] = pledge_ceiling
    if current_sectors():
        active_count += 1

    return filters, bucket_filters, weights, fh_filters, active_count


# ----------------------------------------------------------------------------
# 1 · Landing / search
# ----------------------------------------------------------------------------

def render_landing(universe):
    as_of = get_data_as_of(universe)
    n = len(universe)

    render_masthead(universe, active_view="landing")

    st.markdown(f'''
<div class="sd-hero">
  <div class="sd-hero-kicker">INSTITUTIONAL-GRADE SCREENING · {n:,} NSE-LISTED COMPANIES</div>
  <div class="sd-hero-title">Indicative M&amp;A valuation, weighted your way.</div>
  <div class="sd-hero-sub">Filter, weight-score, and value any NSE-listed company against a factor-weighted engine. Search by name, ticker, or a plain-language query.</div>
</div>''', unsafe_allow_html=True)

    with st.form("landing_search_form", clear_on_submit=False):
        search_cols = st.columns([0.15, 5.4, 0.95])
        with search_cols[0]:
            st.markdown('<div class="sd-search-prompt">&gt;</div>', unsafe_allow_html=True)
        with search_cols[1]:
            # NL-style placeholder per design spec; the search itself is still a
            # literal name/ticker substring match (see render_results) — a full
            # NL-to-filter parser is a separate, larger backend feature, not
            # implemented here. The placeholder sets that expectation honestly
            # only insofar as a literal "tcs" search already works as shown.
            q = st.text_input("Search", key="land_search", label_visibility="collapsed",
                              placeholder='tcs, or "profitable IT companies under 500cr revenue"')
        with search_cols[2]:
            submitted = st.form_submit_button("RUN", type="primary", use_container_width=True)
        if submitted and q and q.strip():
            go("results", q=q.strip())

    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
    render_sector_chips("results", universe=universe)
    browse = st.columns([2, 3, 2])
    if browse[1].button("Browse all companies →", key="land_browse", use_container_width=True):
        go("results")

    st.markdown(f'<div class="sd-hero-stats"><div class="sd-hero-stat">DATA AS OF <strong>{esc(as_of)}</strong></div><div class="sd-hero-stat"><strong>{n:,}</strong> COMPANIES</div></div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# 2 · Results / browsing
# ----------------------------------------------------------------------------

# Sortable column key -> dataframe field. "rank" is the implicit default
# (score descending) and isn't in this dict since it has no single backing
# field of its own (rank is derived from score).
SORTABLE_COLUMNS = {
    "company": "name",
    "sector": "sector_v2",
    "score": "score",
    "revenue": "revenue",
    "margin": "ebitda_margin_pct",
    "roce": "return_on_capital_employed_pct",
    "debt": "total_debt",
}


def current_sort():
    """(column_key, 'asc'|'desc') from ?sort=, e.g. sort=score_desc. Falls
    back to the table's natural default (score, descending -- i.e. rank)."""
    raw = st.query_params.get("sort", "")
    if "_" not in raw:
        return "rank", "desc"
    col, _, direction = raw.rpartition("_")
    if col not in SORTABLE_COLUMNS or direction not in ("asc", "desc"):
        return "rank", "desc"
    return col, direction


def _sort_header_cell(col_key, label, width, align="left"):
    """A clickable header cell: click toggles asc/desc on that column
    (starting descending), with a ▲/▼ indicator on whichever column is
    currently active. Non-active columns show no arrow, per spec."""
    cur_col, cur_dir = current_sort()
    is_active = col_key == cur_col
    next_dir = "asc" if (is_active and cur_dir == "desc") else "desc"
    arrow = (" ▲" if cur_dir == "asc" else " ▼") if is_active else ""
    color = C_T1 if is_active else C_T3
    href = esc(preserved_href(view="results", sort=f"{col_key}_{next_dir}", page=None))
    justify = "flex-end" if align == "right" else "flex-start"
    style = "flex:1;min-width:0;" if width is None else f"width:{width};flex:none;"
    return (f'<a href="{href}" target="_self" style="{style}display:flex;justify-content:{justify};'
            f'text-decoration:none;cursor:pointer">'
            f'<span style="font:700 10.5px \'IBM Plex Mono\',monospace;letter-spacing:.04em;color:{color}">'
            f'{esc(label)}{arrow}</span></a>')


def results_table_html(view, sector_avgs):
    header = (f'<div style="display:flex;padding:9px 14px;background:{C_CARD2};border-bottom:1px solid {C_BORDER}">'
              f'<div style="width:40px;flex:none;font:700 10.5px \'IBM Plex Mono\',monospace;letter-spacing:.04em;color:{C_T3}">RANK</div>'
              + _sort_header_cell("company", "COMPANY", None)
              + _sort_header_cell("sector", "SECTOR", "150px")
              + _sort_header_cell("score", "SCORE", "70px")
              + _sort_header_cell("revenue", "REVENUE", "104px", "right")
              + _sort_header_cell("margin", "MARGIN", "78px", "right")
              + _sort_header_cell("roce", "ROCE", "64px", "right")
              + _sort_header_cell("debt", "DEBT", "110px", "right")
              + '</div>')
    rows = []
    for i, (_, r) in enumerate(view.iterrows()):
        alt = C_ROW_ALT if i % 2 == 0 else "transparent"
        rank = f'{r["_rank"]:.0f}' if pd.notna(r["_rank"]) else "—"
        rank_color = C_T5 if pd.notna(r["_rank"]) else C_T6
        avg = sector_avgs.get(r["sector_v2"])
        ring = ring_html(r["score"], avg, size=34, inner_bg=(C_CARD if i % 2 else "#0e1217"))
        name_color = C_T1 if pd.notna(r["score"]) else C_T3
        rev = format_cr_plain(r["revenue"]); mar = format_pct(r["ebitda_margin_pct"])
        roce = format_pct(r["return_on_capital_employed_pct"]); debt = format_cr_plain(r["total_debt"])

        def cell(width, value):
            color = C_T2 if value != "N/A" else C_T5
            return (f'<div style="width:{width};flex:none;text-align:right;'
                    f'font:500 12.5px \'IBM Plex Mono\',monospace;color:{color}">{esc(value)}</div>')

        href = esc(preserved_href(view="tearsheet", symbol=r["symbol"]))
        rows.append(
            f'<a href="{href}" target="_self" title="{esc(r["name"])}" '
            f'style="display:flex;align-items:center;padding:11px 14px;background:{alt};'
            f'border-radius:0;text-decoration:none">'
            f'<div style="width:40px;flex:none;font:700 12px \'IBM Plex Mono\',monospace;color:{rank_color}">{rank}</div>'
            f'<div style="flex:1;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">'
            f'<span style="font:600 13.5px Inter,sans-serif;color:{name_color}">{esc(r["name"])}</span> '
            f'<span style="font:400 11px \'IBM Plex Mono\',monospace;color:{C_T5}">{esc(r["symbol"])}</span></div>'
            f'<div style="width:150px;flex:none;font:500 12.5px Inter,sans-serif;color:{C_T3}">{esc(sector_display_name(r["sector_v2"]))}</div>'
            f'<div style="width:70px;flex:none">{ring}</div>'
            + cell("104px", rev) + cell("78px", mar) + cell("64px", roce) + cell("110px", debt)
            + '</a>'
        )
    body = header + '<div style="display:flex;flex-direction:column;gap:2px">' + "".join(rows) + '</div>'
    return f'<div class="sd-table-inner">{body}</div>'


def apply_financial_health_filters(df, fh_filters):
    """Post-filter on z_score/f_score. Kept separate from filter_companies()
    (filtering.py) rather than folded into its RANGE_FIELDS mechanism -- these
    aren't simple range filters (min F-score is a floor, the other two are
    booleans over a derived zone label), and filtering.py's composition-order
    contract is deliberately narrow. Same NaN-passes-through-unless-the-filter-
    is-active convention as filter_companies()."""
    mask = pd.Series(True, index=df.index)
    if fh_filters.get("min_fscore", 0) > 0:
        mask &= df["f_score"] >= fh_filters["min_fscore"]
    if fh_filters.get("safe_only"):
        mask &= df["z_score_zone"] == "Safe"
    if fh_filters.get("exclude_distress"):
        mask &= df["z_score_zone"] != "Distress"
    return df[mask].reset_index(drop=True)


def apply_bucket_filters(df, bucket_filters):
    """Apply the discrete numeric bucket filters (market cap / revenue /
    margin / ROCE / debt). Unlike filter_companies()'s range filters, a row
    with NO value on the filtered field is EXCLUDED — a company can't be shown
    inside a "Mega caps" bucket when its market cap is unknown."""
    mask = pd.Series(True, index=df.index)
    for field, (lo, hi) in bucket_filters.items():
        mask &= df[field].between(lo, hi)  # between() is already False for NaN
    return df[mask].reset_index(drop=True)


def render_results(universe):
    filters, bucket_filters, weights, fh_filters, active_filter_count = render_filter_drawer(universe)

    scored = score_universe(universe, tuple(sorted(weights.items())))
    scored = scored.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)
    filtered = filter_companies(scored, filters)
    filtered = apply_bucket_filters(filtered, bucket_filters)
    filtered = apply_financial_health_filters(filtered, fh_filters)

    q = st.query_params.get("q", "")
    if q:
        # regex=False: treat the query as a literal substring, so a search like
        # "L&T" or "(" can't raise a regex error (or be used as a regex-DoS vector).
        mask = (filtered["name"].str.contains(q, case=False, na=False, regex=False)
                | filtered["symbol"].str.contains(q, case=False, na=False, regex=False))
        filtered = filtered[mask].reset_index(drop=True)

    sort_col, sort_dir = current_sort()
    ascending = sort_dir == "asc"
    if sort_col == "rank":
        filtered = filtered.sort_values("score", ascending=not ascending, na_position="last").reset_index(drop=True)
    else:
        sort_field = SORTABLE_COLUMNS[sort_col]
        filtered = filtered.sort_values(sort_field, ascending=ascending, na_position="last").reset_index(drop=True)
    filtered["_rank"] = filtered["score"].rank(ascending=False, method="min", na_option="keep")
    sector_avgs = sector_avg_scores(scored)
    as_of = get_data_as_of(universe)

    render_masthead(universe, active_view="results")

    # ---- top bar (Share removed per request; Search / Filters / CSV only) ----
    bar = st.columns([6, 2, 1.1])
    with bar[0]:
        newq = st.text_input("Search", value=q, key="results_search",
                             label_visibility="collapsed",
                             placeholder="Search company or ticker…")
        if newq != q:
            go("results", q=(newq.strip() or None), page=None)
    with bar[1]:
        filters_label = f"FILTERS ({active_filter_count})" if active_filter_count else "FILTERS"
        if st.button(filters_label, key="open_adv", use_container_width=True):
            go("results", panel="1")
    with bar[2]:
        st.download_button(
            "↓ CSV",
            data=filtered.drop(columns=["ey_bucket", "_rank"], errors="ignore").to_csv(index=False).encode("utf-8"),  # sector_v2 stays in the export
            file_name="nse_ma_screener_results.csv", mime="text/csv",
            use_container_width=True,
        )

    # ---- sector chips ----
    render_sector_chips("results", universe=filtered)

    total = len(filtered)
    st.markdown(f'''<div style="display:flex;justify-content:space-between;align-items:baseline;
margin:14px 0 8px"><span style="font:600 12px Inter,sans-serif;color:{C_T4}">{total:,} companies matched{(" · '" + esc(q) + "'") if q else ""}</span>
<a href="{esc(preserved_href(view="scoring"))}" target="_self" style="font:600 11.5px Inter,sans-serif">How scoring works ⓘ</a></div>''',
                unsafe_allow_html=True)

    if total == 0:
        st.markdown(f'''
<div style="text-align:center;padding:44px;border:1px solid {C_BORDER2};border-radius:0;background:{C_CARD};max-width:620px;margin:24px auto">
  <div style="font:700 20px Inter,sans-serif;color:{C_T1};margin-bottom:8px">No companies match these filters.</div>
  <div style="color:{C_T3};font-size:13px;margin-bottom:18px">Try widening your ranges.</div>
</div>''', unsafe_allow_html=True)
        cc = st.columns([2, 1, 2])
        if cc[1].button("Reset filters", key="reset_zero", type="primary", use_container_width=True):
            for k in FILTER_QP_KEYS + [f"w_{m}" for m in METRICS] + ["q"]:
                st.query_params.pop(k, None)
            for k in FILTER_WIDGET_KEYS + [f"w_{m}" for m in METRICS]:
                st.session_state.pop(k, None)
            st.rerun()
        return

    page = qp_int("page", 1)
    show = min(total, page * ROWS_PER_PAGE)
    view = filtered.head(show)

    st.markdown(
        f'<div class="sd-table-scroll" style="background:{C_CARD};border:1px solid {C_BORDER};'
        f'border-radius:0;padding:10px 14px 16px">'
        + results_table_html(view, sector_avgs) + '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<div style="margin-top:12px;font:400 11px Inter,sans-serif;color:{C_T6}">'
                f'White tick on each ring = sector-average score, for an instant above/below-peer read. '
                f'Showing top {show:,} of {total:,}.</div>', unsafe_allow_html=True)

    if show < total:
        mc = st.columns([2, 1, 2])
        if mc[1].button(f"Show more ({total - show:,} left)", key="show_more", use_container_width=True):
            go("results", page=str(page + 1))


# ----------------------------------------------------------------------------
# 4 & 5 · Tear sheet
# ----------------------------------------------------------------------------

def render_tearsheet(universe, symbol):
    render_masthead(universe, active_view="results")
    weights = current_weights()
    scored = score_universe(universe, tuple(sorted(weights.items())))
    match = scored[scored["symbol"] == symbol]
    if match.empty:
        if st.button("← Back to results", key="back_missing"):
            go("results", symbol=None)
        st.warning("Company not found.")
        return
    row = match.iloc[0]
    bucket = row["sector_v2"]
    as_of = get_data_as_of(universe)
    avg = sector_avg_scores(scored).get(bucket)
    scored_flag = pd.notna(row["score"])

    if st.button("← Back to results", key="back_button"):
        go("results", symbol=None)

    # ---- header + ring ----
    ticker_bg = C_TEAL_LT if scored_flag else "rgba(255,255,255,.08)"
    ticker_col = C_INK if scored_flag else C_T3
    industry = row.get("industry")
    subtitle = sector_display_name(bucket) + (f" · {esc(industry)}" if pd.notna(industry) else " · sector could not be determined")
    ring = ring_html(row["score"], avg, size=104, inner_bg=C_CARD, font_size=26,
                     show_label=True, glow=True)
    avg_caption = (f"| sector avg {avg:.0f}" if (scored_flag and pd.notna(avg)) else
                   ("no sector peers to compare" if not scored_flag else ""))
    st.markdown(f'''
<div class="sd-tearhead" style="display:flex;align-items:flex-end;justify-content:space-between;margin:16px 0 22px">
  <div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">
      <div style="font:700 30px/1.1 Inter,sans-serif;color:{C_T1};letter-spacing:-.01em">{esc(row["name"])}</div>
      <div style="font:700 12px 'IBM Plex Mono',monospace;color:{ticker_col};background:{ticker_bg};border-radius:0;padding:3px 9px">{esc(row["symbol"])}</div>
    </div>
    <div style="font:500 13.5px Inter,sans-serif;color:{C_T3}">{subtitle}</div>
  </div>
  <div style="text-align:center">
    {ring}
    <div style="margin-top:9px;font:500 10.5px Inter,sans-serif;color:{C_T4}">{avg_caption}</div>
  </div>
</div>''', unsafe_allow_html=True)

    # ---- headline stat cards ----
    debt_val = format_cr(row["total_debt"])
    st.markdown(
        '<div class="sd-grid4" style="margin-bottom:22px">'
        + stat_card("MARKET CAP", format_cr(row["market_cap"]),
                    C_T1 if pd.notna(row["market_cap"]) else C_T5)
        + stat_card("REVENUE", format_cr(row["revenue"]),
                    C_T1 if pd.notna(row["revenue"]) else C_T5)
        + stat_card("ROCE", format_pct(row["return_on_capital_employed_pct"]),
                    C_TEAL_LT if pd.notna(row["return_on_capital_employed_pct"]) else C_T5)
        + stat_card("TOTAL DEBT", debt_val, C_T1 if debt_val != "N/A" else C_T5)
        + '</div>', unsafe_allow_html=True)

    # ---- score breakdown ----
    bars = "".join(breakdown_bar_html(FACTOR_LABELS[m], weights[m], row[f"pctl_{m}"]) for m in METRICS)
    sparse_note = ("" if scored_flag else
                   f'<div style="margin-top:16px;font:400 12px Inter,sans-serif;color:{C_T6}">All 4 factors unavailable — this company cannot currently be scored.</div>')
    st.markdown(f'''
<div style="padding:22px 26px;background:{C_CARD2};border-radius:0;border:1px solid {C_BORDER};margin-bottom:22px">
  <div style="font:700 10.5px Inter,sans-serif;letter-spacing:.06em;color:{C_T3};margin-bottom:16px">SCORE BREAKDOWN</div>
  <div style="display:flex;flex-direction:column;gap:14px">{bars}</div>
  {sparse_note}
</div>''', unsafe_allow_html=True)

    # ---- financial health (full-width: 3-card row reads better unsplit) ----
    render_financial_health_section(row)

    # ---- two-column body (spec: 1.1fr/0.9fr) ----
    # Left: remaining key-financials detail + indicative valuation.
    # Right: AI rationale, comparable deals, regulatory filings/news.
    # Two balanced columns for the reading content: Key Financials + Valuation
    # on the left, AI rationale on the right. Comparable Deals and the
    # filings/news feeds move to their OWN full-width sections below — they're
    # wide tables/lists that were colliding when crammed into a half column.
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown('<div class="sd-section-title">Key financials</div>', unsafe_allow_html=True)
        rows_html = "".join(
            key_financial_row(label, value)
            for label, value in [
                ("EBITDA", format_cr(row["ebitda"])),
                ("EBITDA Margin", format_pct(row["ebitda_margin_pct"])),
                ("Net Income", format_cr(row["net_income"])),
                ("Promoter Pledge", format_pct(row["promoter_pledge_pct"])),
            ]
        )
        st.markdown(
            f'<div style="background:{C_CARD2};border:1px solid {C_BORDER};border-radius:var(--r-card);'
            f'overflow:hidden;margin-bottom:22px">{rows_html}</div>',
            unsafe_allow_html=True,
        )
        render_valuation_card(row)
    with right:
        st.markdown('<div class="sd-section-title">AI rationale</div>', unsafe_allow_html=True)
        render_rationale_card(row, scored_flag)

    # ---- full-width sections (room to breathe, no column collision) ----
    render_deals_section(bucket)
    render_filings_news_section(row)


def render_financial_health_section(row):
    z = row.get("z_score")
    zone = row.get("z_score_zone")
    f = row.get("f_score")
    beneish = row.get("beneish_m_score") if "beneish_m_score" in row.index else None

    def card(title, value, detail, color=C_T1):
        return (f'<div style="padding:16px 18px;background:{C_CARD2};border:1px solid {C_BORDER};border-radius:0">'
                f'<div style="font:700 10px Inter,sans-serif;letter-spacing:.06em;color:{C_T5};margin-bottom:6px">{esc(title)}</div>'
                f'<div style="font:700 20px \'IBM Plex Mono\',monospace;color:{color};margin-bottom:4px">{esc(value)}</div>'
                f'<div style="font:400 11px Inter,sans-serif;color:{C_T4};line-height:1.45">{esc(detail)}</div></div>')

    if pd.notna(z):
        zone_text = f"{zone or 'N/A'} zone"
        z_value = f"{z:.2f}"
        z_detail = zone_text
        z_color = C_TEAL_LT if zone == "Safe" else (C_WARN if zone == "Grey" else C_DANGER)
    else:
        z_value = "N/A"
        z_detail = "Insufficient balance-sheet inputs or excluded sector"
        z_color = C_T4

    if pd.notna(f):
        f_value = f"{int(f)}/9"
        f_detail = "All 9 Piotroski signals computable"
        f_color = C_TEAL_LT
    else:
        f_value = "N/A"
        f_detail = "Missing one or more of the 9 required annual inputs"
        f_color = C_T4

    if beneish is not None and pd.notna(beneish):
        b_value = f"{beneish:.2f}"
        b_detail = "Beneish M-Score"
        b_color = C_T1
    else:
        b_value = "N/A"
        b_detail = "Not yet computed in the current dataset"
        b_color = C_T4

    st.markdown(
        '<div style="padding:20px 24px;background:%s;border:1px solid %s;border-radius:0;margin-bottom:22px">'
        '<div style="font:700 10.5px Inter,sans-serif;letter-spacing:.06em;color:%s;margin-bottom:14px">FINANCIAL HEALTH</div>'
        '<div class="sd-grid3">%s%s%s</div></div>' % (
            C_CARD2, C_BORDER, C_T3,
            card("ALTMAN Z''-SCORE", z_value, z_detail, z_color),
            card("PIOTROSKI F-SCORE", f_value, f_detail, f_color),
            card("BENEISH M-SCORE", b_value, b_detail, b_color),
        ),
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def _load_tearsheet_filings(company_name):
    filings, errors = fetch_all_nse_filings()
    matched = match_filings_to_company(filings, company_name)
    matched = sorted(matched, key=lambda f: parse_pub_date(f.get("pub_date", "")) or datetime.min, reverse=True)[:8]
    bse_items, bse_error = fetch_bse_notices()
    return matched, errors, bse_items[:5], bse_error


@st.cache_data(show_spinner=False)
def _load_tearsheet_news(company_name):
    return fetch_company_news(company_name)


def _feed_row(title, meta, link):
    """One feed entry. When a real source link exists the whole row is an
    <a target="_blank"> to the official page (NSE/BSE archive, or the news
    publisher via Google News's redirect); otherwise it's a plain div."""
    ext = ' <span class="sd-feed-ext">↗</span>' if link else ""
    inner = (f'<div class="sd-feed-title">{esc(title)}{ext}</div>'
             f'<div class="sd-feed-meta">{esc(meta)}</div>')
    if link:
        return (f'<a class="sd-feed-row" href="{esc(link)}" target="_blank" '
                f'rel="noopener noreferrer">{inner}</a>')
    return f'<div class="sd-feed-row">{inner}</div>'


def _feed_card(rows_html):
    return (f'<div class="sd-feed" style="border:1px solid {C_BORDER};border-radius:var(--r-card);'
            f'overflow:hidden;background:{C_CARD}">{rows_html}</div>')


def _feed_empty(text):
    return (f'<div style="padding:14px 16px;background:{C_CARD};border:1px solid {C_BORDER};'
            f'border-radius:var(--r-card);color:{C_T4};font-size:12.5px">{esc(text)}</div>')


def render_filings_news_section(row):
    company_name = row["name"]
    matched, feed_errors, bse_items, bse_error = _load_tearsheet_filings(company_name)
    news_items, news_error = _load_tearsheet_news(company_name)

    left, right = st.columns(2, gap="large")

    # ---- left: official regulatory filings (NSE) + BSE notices ----
    with left:
        st.markdown('<div class="sd-section-title" style="margin-top:26px">Regulatory filings</div>', unsafe_allow_html=True)
        if feed_errors:
            st.markdown(f'<div style="margin-bottom:10px;font-size:11px;color:{C_T5}">'
                        f'{len(feed_errors)} of {len(NSE_FEEDS)} NSE feeds temporarily unavailable.</div>',
                        unsafe_allow_html=True)
        if matched:
            rows_html = "".join(
                _feed_row(f.get("title", ""),
                          f'{f.get("category", "")} · {f.get("pub_date", "")}'.strip(" ·"),
                          f.get("link"))
                for f in matched
            )
            st.markdown(_feed_card(rows_html), unsafe_allow_html=True)
        else:
            st.markdown(_feed_empty("No recent company-matching NSE filings found right now."),
                        unsafe_allow_html=True)

        if bse_error:
            st.markdown(f'<div style="margin-top:8px;font-size:10.5px;color:{C_T6}">BSE notices unavailable: {esc(bse_error)}</div>', unsafe_allow_html=True)
        elif bse_items:
            st.markdown('<div class="sd-section-title" style="margin-top:20px">BSE notices</div>', unsafe_allow_html=True)
            bse_rows = "".join(
                _feed_row(n.get("title", ""), n.get("pub_date", ""), n.get("link"))
                for n in bse_items
            )
            st.markdown(_feed_card(bse_rows), unsafe_allow_html=True)

    # ---- right: general news (each links to the publisher) ----
    with right:
        st.markdown('<div class="sd-section-title" style="margin-top:26px">News</div>', unsafe_allow_html=True)
        if news_error:
            st.markdown(_feed_empty(f"News unavailable right now ({news_error})."), unsafe_allow_html=True)
        elif news_items:
            news_rows = "".join(
                _feed_row(item.get("title", ""),
                          f'{item.get("source", "")}'
                          + (f' · {item.get("pub_date", "")}' if item.get("pub_date") else ""),
                          item.get("link"))
                for item in news_items
            )
            st.markdown(_feed_card(news_rows), unsafe_allow_html=True)
        else:
            st.markdown(_feed_empty("No recent news found for this company."), unsafe_allow_html=True)


def render_valuation_card(row):
    have_ev = pd.notna(row["ev_ebitda_low"]) and pd.notna(row["ev_ebitda_high"])
    have_pe = pd.notna(row["pe_implied_low"]) and pd.notna(row["pe_implied_high"])
    if not have_ev and not have_pe:
        note = row["valuation_note"] or "Insufficient sector peer data."
        st.markdown(f'''
<div style="padding:22px 26px;background:{C_PANEL};border-radius:0;border:1px dashed {C_BORDER2};margin-bottom:22px">
  <div style="font:700 10.5px Inter,sans-serif;letter-spacing:.06em;color:{C_T5};margin-bottom:10px">INDICATIVE VALUATION RANGE</div>
  <div style="font:600 15px Inter,sans-serif;color:{C_T3}">Insufficient data to estimate a valuation range.</div>
  <div style="font:400 12.5px Inter,sans-serif;color:{C_T5};margin-top:6px">{esc(note)}</div>
</div>''', unsafe_allow_html=True)
        return

    def block(label, low, high, seg):
        if pd.isna(low) or pd.isna(high):
            return (f'<div><div style="font:500 11px Inter,sans-serif;color:#8fd6c4;margin-bottom:5px">{label}</div>'
                    f'<div style="font:400 12px Inter,sans-serif;color:{C_T3}">{esc(seg)}</div></div>')
        return (f'<div><div style="font:500 11px Inter,sans-serif;color:#8fd6c4;margin-bottom:5px">{label}</div>'
                f'<div style="font:700 22px \'IBM Plex Mono\',monospace;color:{C_T1}">{esc(format_cr(low))} – {esc(format_cr(high))}</div></div>')

    note = row["valuation_note"]
    ev = block("EV/EBITDA-implied", row["ev_ebitda_low"], row["ev_ebitda_high"],
               extract_note_segment(note, "EV/EBITDA:"))
    pe = block("P/E-implied", row["pe_implied_low"], row["pe_implied_high"],
               extract_note_segment(note, "P/E:"))
    st.markdown(f'''
<div style="padding:22px 26px;background:linear-gradient(135deg,{C_TEAL_DK},{C_TEAL_DK2});
border-radius:0;border:1px solid rgba(31,184,163,.3);margin-bottom:22px">
  <div style="font:700 10.5px Inter,sans-serif;letter-spacing:.06em;color:{C_TEAL_LT};margin-bottom:14px">INDICATIVE VALUATION RANGE</div>
  <div style="display:flex;gap:44px;flex-wrap:wrap">{ev}{pe}</div>
</div>''', unsafe_allow_html=True)


def render_rationale_card(row, scored_flag):
    if not scored_flag:
        st.markdown(f'''
<div style="margin-bottom:22px;padding:20px 24px;background:{C_CARD2};border-radius:0;border:1px solid {C_BORDER}">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
    <span style="font:700 9.5px Inter,sans-serif;letter-spacing:.08em;color:{C_T3};background:rgba(255,255,255,.08);padding:3px 8px;border-radius:0">UNAVAILABLE</span>
    <span style="font:700 11px Inter,sans-serif;letter-spacing:.05em;color:{C_T5}">AI RATIONALE</span></div>
  <div style="font:400 13.5px/1.65 Inter,sans-serif;color:{C_T4}">Not enough reported financial data to generate an AI-drafted rationale for this company.</div>
</div>''', unsafe_allow_html=True)
        return
    rationale = get_ai_rationale(row)
    if rationale:
        badge = (f'<span style="font:700 9.5px Inter,sans-serif;letter-spacing:.08em;color:{C_INK};'
                 f'background:{C_TEAL_LT};padding:3px 8px;border-radius:0">AI-DRAFTED</span>')
        body_color = C_T2
        text = esc(rationale)
    else:
        badge = (f'<span style="font:700 9.5px Inter,sans-serif;letter-spacing:.08em;color:{C_T3};'
                 f'background:rgba(255,255,255,.08);padding:3px 8px;border-radius:0">UNAVAILABLE</span>')
        body_color = C_T4
        text = "AI rationale unavailable right now — the rest of this tear sheet is unaffected."
    st.markdown(f'''
<div style="margin-bottom:22px;padding:20px 24px;background:{C_CARD2};border-radius:0;border:1px solid {C_BORDER}">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
    {badge}<span style="font:700 11px Inter,sans-serif;letter-spacing:.05em;color:{C_T5}">RATIONALE</span></div>
  <div style="font:400 13.5px/1.65 Inter,sans-serif;color:{body_color}">{text}</div>
</div>''', unsafe_allow_html=True)


def render_deals_section(bucket):
    deals = load_all_deals()
    comps = deals[deals["sector_v2"] == bucket].copy()
    comps = comps.sort_values("report_year", ascending=False).head(6)
    label = ('<div class="sd-section-title" style="margin-top:26px">Comparable deals · '
             f'{esc(sector_display_name(bucket))}</div>')
    if comps.empty:
        st.markdown(label + f'<div style="padding:16px 18px;background:{C_CARD2};border:1px solid {C_BORDER};'
                    f'border-radius:var(--r-card);font-size:13px;color:{C_T4}">No comparable 2025 Indian M&amp;A deals found in this sector.</div>',
                    unsafe_allow_html=True)
        return
    # Explicit column grid keeps VALUE and TYPE from colliding (the old flex row
    # let the right-aligned value butt straight against the type text). Every
    # cell has its own padded column track; text wraps inside its own cell.
    grid = "grid-template-columns:1.5fr 1.5fr 130px 1fr 68px;"
    head = (f'<div style="display:grid;{grid}gap:16px;padding:11px 18px;'
            f'font:700 10px Inter,sans-serif;letter-spacing:.06em;color:{C_T5};border-bottom:1px solid {C_BORDER}">'
            f'<div>TARGET</div><div>ACQUIRER</div>'
            f'<div style="text-align:right">VALUE</div>'
            f'<div>TYPE</div><div style="text-align:right">YEAR</div></div>')
    body = ""
    for i, (_, d) in enumerate(comps.iterrows()):
        border = f"border-bottom:1px solid {C_BORDER};" if i < len(comps) - 1 else ""
        val = d["deal_value_usdm_numeric"]
        val_txt = f"US${val:,.0f}m" if pd.notna(val) else "—"
        def t(v):
            return esc(v) if pd.notna(v) else "N/A"
        body += (f'<div style="display:grid;{grid}gap:16px;padding:13px 18px;{border}'
                 f'font-size:13px;color:{C_T2};align-items:baseline">'
                 f'<div style="font-weight:600;color:{C_T1}">{t(d["target"])}</div>'
                 f'<div>{t(d["acquirer"])}</div>'
                 f'<div style="text-align:right;font-family:\'IBM Plex Mono\',monospace;font-weight:600;color:{C_TEAL_LT};white-space:nowrap">{val_txt}</div>'
                 f'<div style="color:{C_T3};font-size:12px">{t(d["deal_type"])}</div>'
                 f'<div style="text-align:right;font-family:\'IBM Plex Mono\',monospace;color:{C_T3}">{t(d["report_year"])}</div></div>')
    st.markdown(label + f'<div style="border:1px solid {C_BORDER};border-radius:var(--r-card);'
                f'overflow:hidden;background:{C_CARD2}">{head}{body}</div>',
                unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Scoring-help view (reachable from "How scoring works")
# ----------------------------------------------------------------------------

def render_scoring_help():
    render_masthead(load_universe(), active_view="scoring")
    if st.button("← Back to results", key="back_help"):
        go("results")
    st.markdown(f'''
<div style="max-width:720px">
  <div style="font:700 26px Inter,sans-serif;color:{C_T1};margin:10px 0 18px">How scoring works</div>
  <div style="font:400 14px/1.7 Inter,sans-serif;color:{C_T2}">
  Each company gets a 0–100 <b>composite score</b>, computed <b>relative to its own sector peers</b> (not the whole market).
  Four factors are scored — Revenue Growth, EBITDA Margin, ROCE, and Debt Level (inverted: less debt ranks higher) —
  each as a percentile within the company's EY sector bucket. Your factor-weight sliders blend those four percentiles
  live; raise a weight to rank by what you care about. A company missing a factor has it dropped and the rest reweighted;
  a company with fewer than two of the four factors is left unscored (shown as “—”) rather than given a misleading number.
  Market cap and promoter pledge are filters only — never part of the score. The white tick on each score ring marks
  the sector-average score, so you can read above/below-peer at a glance.
  </div>
</div>''', unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    inject_css()
    universe = load_universe()

    view = st.query_params.get("view")
    if view is None:
        # Bare visit -> landing. But an inbound share/deep link that carries a
        # sector or search selection (from before this redesign, or shared by a
        # user) should open straight into results rather than the empty landing.
        view = "results" if (st.query_params.get("sectors") or st.query_params.get("q")) else "landing"
    symbol = st.query_params.get("symbol")

    if view == "tearsheet" and symbol:
        render_tearsheet(universe, symbol)
    elif view == "scoring":
        render_scoring_help()
    elif view == "results":
        render_results(universe)
    else:
        render_landing(universe)


if __name__ == "__main__":
    main()
