"""DealScope — Streamlit app.

Pipeline (composition-order contract from scoring.py / valuation.py):
load_companies() -> score_companies() + valuation_range() on the FULL
universe -> filter_companies() last, purely for display.
"""

import html
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.data.loaders import load_companies, load_deals, get_data_as_of
from src.data.schema import EY_BUCKETS, UNCLASSIFIED_BUCKET, ALL_BUCKETS
from src.logic.filtering import filter_companies
from src.logic.scoring import score_companies, METRICS
from src.logic.valuation import valuation_range
from src.config import get_gemini_api_key, get_groq_api_key, get_cerebras_api_key

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

COLOR_BG = "#EDEBE6"  # mockup's design-tool presentation canvas, not part of the real app
COLOR_CARD = "#FBF7EE"
COLOR_SIDEBAR = "#F1EADA"
COLOR_TEXT = "#1C1B19"
COLOR_ACCENT = "#9C7A3C"
COLOR_MUTED = "#8A7F63"
COLOR_BORDER = "#E7DCC1"
COLOR_NEGATIVE = "#7A3B33"
COLOR_TAN = "#D9CDAA"
COLOR_TAN_DARK = "#B9AC85"

FACTOR_LABELS = {
    "revenue_growth_pct": "Revenue Growth",
    "ebitda_margin_pct": "EBITDA Margin",
    "return_on_capital_employed_pct": "ROCE",
    "total_debt": "Debt Level",
}

RANGE_FIELD_CONFIG = [
    # (filters.py key, label, unit divisor for crore conversion)
    ("revenue", "REVENUE (₹ CR)", 1e7),
    ("ebitda_margin_pct", "EBITDA MARGIN %", 1),
    ("return_on_capital_employed_pct", "ROCE %", 1),
    ("total_debt", "TOTAL DEBT (₹ CR)", 1e7),
    ("market_cap", "MARKET CAP (₹ CR)", 1e7),
    # Phase 2 fields (data/enriched/dealscope_base_2026-07-12.csv) -- filters
    # only, per the locked decision not to fold these into the 4-factor score.
    ("total_assets", "TOTAL ASSETS (₹ CR)", 1e7),
    ("retained_earnings", "RETAINED EARNINGS (₹ CR)", 1e7),
    ("working_capital", "WORKING CAPITAL (₹ CR)", 1e7),
    ("enterprise_value", "ENTERPRISE VALUE (₹ CR)", 1e7),
    ("total_cash", "TOTAL CASH (₹ CR)", 1e7),
    ("operating_cash_flow", "OPERATING CASH FLOW (₹ CR)", 1e7),
    ("free_cash_flow", "FREE CASH FLOW (₹ CR)", 1e7),
    ("current_ratio", "CURRENT RATIO", 1),
    ("quick_ratio", "QUICK RATIO", 1),
    ("debt_to_equity", "DEBT/EQUITY %", 1),
    # return_on_assets is stored as a raw fraction (e.g. 0.09), not a
    # whole-number percentage like the other _pct fields -- divide by 0.01
    # (i.e. multiply by 100) for display only, same crore-style unit
    # conversion the currency fields already use, real value untouched.
    ("return_on_assets", "RETURN ON ASSETS %", 0.01),
    ("beta", "BETA", 1),
    ("peg_ratio", "PEG RATIO", 1),
    ("price_to_book", "PRICE/BOOK", 1),
    ("trailing_pe", "TRAILING P/E", 1),
]

# Derived from RANGE_FIELD_CONFIG so adding/removing a range filter can never
# silently desync these from render_sidebar()/sync_query_params() again --
# exactly this kind of drift (stale hardcoded field lists) caused a real
# "Reset all filters" bug earlier in this project's history.
RANGE_FIELD_NAMES = [field for field, _, _ in RANGE_FIELD_CONFIG]
FILTER_WIDGET_KEYS = (
    ["f_sectors"] + [f"f_{field}" for field in RANGE_FIELD_NAMES] + ["f_pledge_max"]
)
FILTER_QP_KEYS = ["sectors"] + RANGE_FIELD_NAMES + ["pledge_max"]
WEIGHT_WIDGET_KEYS = ["w_revenue_growth_pct", "w_ebitda_margin_pct",
                      "w_return_on_capital_employed_pct", "w_total_debt"]

st.set_page_config(page_title="DealScope", layout="wide")


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


def ordinal(n):
    n = int(round(n))
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def sector_display_name(bucket):
    return {
        "Consumer Products and Retail": "Consumer Products",
        "Industrials and Auto": "Industrials & Auto",
        "Financial Services": "Financial Services",
    }.get(bucket, bucket)


# ----------------------------------------------------------------------------
# AI rationale — tries Gemini, then Groq, then Cerebras (in that order), cached
# by (symbol, as_of_date) on disk so repeat clicks and app restarts (free-tier
# sleep/wake) don't re-burn API quota on any provider. Any provider's failure
# (or empty response) falls through to the next; if all three fail, returns
# None so the PRD fallback text renders instead of crashing the tear sheet.
# ----------------------------------------------------------------------------

RATIONALE_CACHE_PATH = Path(__file__).resolve().parent / ".rationale_cache.json"
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


def _save_rationale_cache(cache):
    try:
        RATIONALE_CACHE_PATH.write_text(json.dumps(cache))
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
Sector (peer group for all percentiles below): {sector_display_name(company_row['ey_bucket'])}
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


# Every provider call gets an explicit, bounded timeout (Phase 4 goal: no
# external HTTP call left to whatever a given SDK defaults to -- some of
# which run to several minutes). A slow/unresponsive provider should fail
# fast into the next one in RATIONALE_PROVIDERS, not tie up the request.
AI_CALL_TIMEOUT_SECONDS = 30


def _call_gemini(api_key, prompt):
    # Imported here, not at module load, so a cold start only pays the
    # memory/import cost of whichever SDK is actually used. Mitigates (does
    # not provably fix) a recurring Render status-139 crash observed after
    # two separate deploys, when all three AI SDKs loaded unconditionally.
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
    cache_key = f"{company_row['symbol']}|{company_row['as_of_date']}"
    cache = _load_rationale_cache()
    if cache_key in cache:
        return cache[cache_key]

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
        _save_rationale_cache(cache)
        return text

    return None


# ----------------------------------------------------------------------------
# Cached data pipeline
# ----------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_universe():
    """load_companies() + valuation_range() on the full universe. Weight-independent."""
    df = load_companies()
    df = valuation_range(df)
    return df


@st.cache_data(show_spinner=False)
def score_universe(df, weights_tuple):
    weights = dict(weights_tuple)
    return score_companies(df, weights)


@st.cache_data(show_spinner=False)
def load_all_deals():
    return load_deals()


# ----------------------------------------------------------------------------
# CSS
# ----------------------------------------------------------------------------

def inject_css():
    css = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600;8..60,700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
html, body, [class*="css"] {{
    font-family: 'IBM Plex Sans', system-ui, sans-serif;
    color: {COLOR_TEXT};
}}
.stApp {{ background: {COLOR_CARD}; }}
[data-testid="stDecoration"] {{ display: none; }}
[data-testid="stSidebar"] {{
    background: {COLOR_SIDEBAR};
    border-right: 2px solid {COLOR_TEXT};
}}
[data-testid="stSidebar"] > div:first-child {{ padding-top: 1.2rem; }}
.block-container {{ padding-top: 2rem; max-width: 1400px; }}

.app-title-eyebrow {{
    font-size: 10px; letter-spacing: .14em; color: {COLOR_MUTED};
    font-weight: 700; margin-bottom: 2px;
}}
.app-title {{
    font-family: 'Source Serif 4', serif; font-weight: 700; font-size: 24px;
    letter-spacing: -.01em; color: {COLOR_TEXT}; margin-bottom: 18px;
}}
.sidebar-section-label {{
    font-size: 10.5px; letter-spacing: .08em; color: {COLOR_TEXT};
    font-weight: 700; margin-bottom: 9px; margin-top: 4px;
}}
.sidebar-subtitle {{
    font-family: 'Source Serif 4', serif; font-style: italic; font-size: 11.5px;
    color: {COLOR_MUTED}; margin-bottom: 10px;
}}
.data-as-of {{ font-size: 11.5px; font-weight: 700; color: {COLOR_TEXT}; margin-top: 12px; }}
.data-as-of span {{ color: {COLOR_ACCENT}; }}

table.rank-header {{ width: 100%; border-collapse: collapse; }}

/* Streamlit widget restyling toward the mockup's flat, high-contrast look */
[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] {{
    background-color: {COLOR_TEXT} !important;
    border-radius: 2px !important;
}}
[data-testid="stSidebar"] .stSlider [data-baseweb="slider"] > div > div {{
    background: {COLOR_ACCENT} !important;
}}
[data-testid="stSidebar"] .stSlider [role="slider"] {{
    background-color: {COLOR_TEXT} !important;
    border-color: {COLOR_TEXT} !important;
}}
div.stButton > button {{
    background: {COLOR_TEXT}; color: #fff; border: none; border-radius: 2px;
    font-weight: 800; font-size: 11px; letter-spacing: .06em; width: 100%;
    text-transform: uppercase; padding: 10px;
}}
div.stButton > button:hover {{ background: {COLOR_ACCENT}; color: #fff; }}
/* "Back to results" reads as a plain nav label in the mockup, not a filled
   button -- scoped via a marker + adjacent-sibling selector since this
   Streamlit version has no per-widget CSS hook. */
div[data-testid="element-container"]:has(.back-btn-marker)
  + div[data-testid="element-container"] div.stButton > button {{
    background: transparent; color: {COLOR_TEXT}; padding: 0; width: auto;
    font-size: 11.5px; letter-spacing: .04em;
}}
div[data-testid="element-container"]:has(.back-btn-marker)
  + div[data-testid="element-container"] div.stButton > button:hover {{
    background: transparent; color: {COLOR_ACCENT};
}}
div.stDownloadButton > button {{
    background: {COLOR_ACCENT}; color: #fff; border: none; border-radius: 2px;
    font-weight: 800; font-size: 11px; letter-spacing: .04em; padding: 10px 18px;
    text-transform: uppercase;
}}
div.stDownloadButton > button:hover {{ background: {COLOR_TEXT}; color: #fff; }}

.sector-badge {{
    font-size: 11px; font-weight: 700; padding: 5px 12px; border-radius: 2px;
    background: {COLOR_TEXT}; color: {COLOR_SIDEBAR}; letter-spacing: .02em;
}}
.tearsheet-name {{
    font-family: 'Source Serif 4', serif; font-weight: 700; font-size: 38px;
    letter-spacing: -.01em; color: {COLOR_TEXT};
}}
.tearsheet-meta {{ font-size: 12.5px; color: {COLOR_MUTED}; font-weight: 600; }}
.back-link {{
    font-size: 11.5px; font-weight: 800; color: {COLOR_TEXT}; letter-spacing: .04em;
    margin-bottom: 6px;
}}
.section-label {{
    font-size: 10.5px; letter-spacing: .06em; color: {COLOR_MUTED};
    font-weight: 700; margin-bottom: 10px; margin-top: 6px;
}}
.card {{ border: 2px solid {COLOR_TEXT}; background: {COLOR_CARD}; }}
.card-header {{
    padding: 10px 16px; font-size: 10.5px; font-weight: 800; letter-spacing: .06em;
    background: {COLOR_TEXT}; color: {COLOR_SIDEBAR};
}}
.card-row {{
    display: flex; justify-content: space-between; padding: 11px 16px;
    border-bottom: 1px solid {COLOR_BORDER}; font-size: 13px;
}}
.card-row:last-child {{ border-bottom: none; }}
.card-row-label {{ color: {COLOR_MUTED}; font-weight: 600; }}
.card-row-value {{ font-family: 'IBM Plex Mono', monospace; font-weight: 700; }}
.card-row-na {{ color: {COLOR_MUTED}; font-style: italic; }}
.no-results-card {{
    text-align: center; padding: 36px; border: 2px solid {COLOR_TEXT};
    background: {COLOR_CARD}; max-width: 640px; margin: 40px auto;
}}
.no-results-title {{
    font-family: 'Source Serif 4', serif; font-weight: 700; font-style: italic;
    font-size: 20px; color: {COLOR_TEXT}; margin-bottom: 8px;
}}
.no-results-sub {{ color: {COLOR_MUTED}; font-size: 12.5px; margin-bottom: 18px; }}
.deal-header {{
    display: flex; gap: 12px; padding: 9px 4px; font-size: 10.5px; color: {COLOR_MUTED};
    font-weight: 700; border-bottom: 2px solid {COLOR_TEXT};
}}
.deal-row {{
    display: flex; gap: 12px; padding: 12px 4px; border-bottom: 1px solid {COLOR_BORDER};
    font-size: 13px; align-items: center;
}}
.deal-target {{ font-family: 'Source Serif 4', serif; font-weight: 600; }}
.no-comps {{ color: {COLOR_MUTED}; font-size: 13px; font-style: italic; padding: 16px 4px; }}
.rationale-quote {{ display: flex; gap: 16px; align-items: flex-start; }}
.rationale-mark {{
    font-family: 'Source Serif 4', serif; font-weight: 700; font-size: 48px;
    color: {COLOR_ACCENT}; line-height: .6;
}}
.rationale-text {{
    font-family: 'Source Serif 4', serif; font-size: 15px; line-height: 1.7;
    color: {COLOR_MUTED}; font-weight: 500; font-style: italic; padding-top: 8px;
}}
</style>
"""
    # react-markdown treats a blank line inside a raw-HTML block as a paragraph
    # break, splitting the <style> tag and leaking the tail as visible text.
    css = "\n".join(line for line in css.splitlines() if line.strip())
    st.markdown(css, unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# HTML component renderers
# ----------------------------------------------------------------------------

def donut_html(score, outer=150, inner=114, font_size=42, show_denominator=True):
    if pd.isna(score):
        deg, score_text = 0, "N/A"
    else:
        deg = max(0, min(360, score / 100 * 360))
        score_text = f"{score:.0f}"
    sub = (f'<div style="font-size:9px;color:{COLOR_MUTED};font-weight:700">/ 100</div>'
           if show_denominator else "")
    return f'''<div style="position:relative;width:{outer}px;height:{outer}px;border-radius:50%;
background:conic-gradient({COLOR_ACCENT} {deg}deg,{COLOR_BORDER} 0);display:flex;
align-items:center;justify-content:center">
  <div style="width:{inner}px;height:{inner}px;border-radius:50%;background:{COLOR_CARD};
  display:flex;flex-direction:column;align-items:center;justify-content:center">
    <div style="font-family:'Source Serif 4',serif;font-weight:700;font-size:{font_size}px;
    color:{COLOR_TEXT};line-height:1">{score_text}</div>
    {sub}
  </div>
</div>'''


def factor_bar_html(label, percentile):
    if pd.isna(percentile):
        return f'''<div style="display:flex;align-items:center;gap:14px;margin-bottom:10px">
  <div style="width:132px;font-size:12px;font-weight:700;color:{COLOR_MUTED}">{label}</div>
  <div style="flex:1;height:10px;background:repeating-linear-gradient(90deg,{COLOR_BORDER} 0 8px,transparent 8px 13px)"></div>
  <div style="width:220px;text-align:right;font-size:11px;color:{COLOR_MUTED};font-style:italic">N/A — excluded, reweighted</div>
</div>'''
    pct = max(0, min(100, percentile))
    return f'''<div style="display:flex;align-items:center;gap:14px;margin-bottom:10px">
  <div style="width:132px;font-size:12px;font-weight:700;color:{COLOR_TEXT}">{label}</div>
  <div style="flex:1;height:10px;background:{COLOR_BORDER}"><div style="height:10px;width:{pct}%;background:{COLOR_ACCENT}"></div></div>
  <div style="width:50px;text-align:right;font-weight:900;color:{COLOR_TEXT}">{ordinal(pct)}</div>
</div>'''


def extract_note_segment(full_note, prefix):
    """Pull just this method's reason out of valuation_range()'s combined valuation_note."""
    if not full_note or prefix not in full_note:
        return "Insufficient sector peer data to compute this range."
    rest = full_note[full_note.index(prefix) + len(prefix):].strip()
    for other_prefix in ("EV/EBITDA:", "P/E:"):
        if other_prefix != prefix and other_prefix in rest:
            rest = rest.split(other_prefix)[0].strip()
    return rest if rest.endswith(".") else rest + "."


def valuation_block_html(low, high, label, note_segment):
    if pd.isna(low) or pd.isna(high):
        return f'''<div style="font-size:11px;font-weight:700;color:{COLOR_MUTED};margin-bottom:9px">{label}</div>
<div style="font-size:12px;color:{COLOR_MUTED};font-style:italic">{note_segment}</div>'''
    return f'''<div style="font-size:11px;font-weight:700;color:{COLOR_MUTED};margin-bottom:9px">{label}</div>
<div style="height:8px;background:{COLOR_BORDER};position:relative;margin-bottom:8px">
  <div style="position:absolute;left:8%;right:8%;top:0;bottom:0;background:{COLOR_ACCENT}"></div>
</div>
<div style="display:flex;justify-content:space-between;font-family:'IBM Plex Mono',monospace;font-size:12px;font-weight:700">
  <span>{format_cr(low)}</span><span>{format_cr(high)}</span>
</div>'''


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


def qp_list(key, default):
    raw = st.query_params.get(key)
    if raw is None:
        return default
    return [s for s in raw.split(",") if s]


def sync_query_params(filters_state, weights_state):
    st.query_params["sectors"] = ",".join(filters_state["sectors"])
    for field in RANGE_FIELD_NAMES:
        lo, hi = filters_state[field]
        st.query_params[field] = f"{lo},{hi}"
    st.query_params["pledge_max"] = str(filters_state["promoter_pledge_pct_max"])
    for metric in METRICS:
        st.query_params[f"w_{metric}"] = str(weights_state[metric])


# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------

def render_sidebar(universe):
    with st.sidebar:
        st.markdown('<div class="app-title-eyebrow">DEALSCOPE</div>', unsafe_allow_html=True)
        st.markdown('<div class="app-title">Target Screener</div>', unsafe_allow_html=True)

        st.markdown('<div class="sidebar-section-label">SECTOR</div>', unsafe_allow_html=True)
        default_sectors = qp_list("sectors", list(ALL_BUCKETS))
        default_sectors = [s for s in default_sectors if s in ALL_BUCKETS] or list(ALL_BUCKETS)
        sectors = st.multiselect(
            "Sector", options=list(ALL_BUCKETS),
            default=default_sectors,
            format_func=sector_display_name,
            key="f_sectors", label_visibility="collapsed",
        )

        range_values = {}
        for field, label, divisor in RANGE_FIELD_CONFIG:
            series = universe[field] / divisor
            data_min = float(series.min(skipna=True))
            data_max = float(series.max(skipna=True))
            data_min = 0.0 if pd.isna(data_min) else data_min
            data_max = 100.0 if pd.isna(data_max) else data_max

            # Slider min/max are percentile-clipped (1st-99th) so one extreme
            # value (e.g. a company whose revenue is near zero, producing a
            # legitimate but huge EBITDA-margin ratio) can't stretch the
            # control out of a usable shape for everyone else. The real data
            # is untouched -- an outlier past the visible ticks is still
            # included by the "slider left at its edge" handling below, so it
            # never silently disappears from the ranked table.
            clip_lo = float(series.quantile(0.01)) if series.notna().any() else data_min
            clip_hi = float(series.quantile(0.99)) if series.notna().any() else data_max
            if pd.isna(clip_lo) or pd.isna(clip_hi) or clip_hi <= clip_lo:
                clip_lo, clip_hi = data_min, data_max

            # Step (and rounding precision) scales to the clipped range itself
            # rather than a fixed whole-number floor -- large-range currency
            # fields (revenue, market cap) still get whole-crore steps, but
            # small-range ratio fields (beta, current ratio, price/book) get
            # fractional steps instead of collapsing to a near-useless 2-3
            # tick slider.
            span = clip_hi - clip_lo
            raw_step = span / 200 if span > 0 else 1.0
            if raw_step >= 1:
                decimals = 0
                step = float(max(1.0, round(raw_step)))
            elif raw_step >= 0.01:
                decimals = 2
                step = round(raw_step, 2) or 0.01
            else:
                decimals = 4
                step = round(raw_step, 4) or 0.0001

            def r(x, _decimals=decimals):
                return round(x, _decimals) if _decimals else float(round(x))

            lo_default, hi_default = qp_float_pair(field, (clip_lo, clip_hi))
            lo_default = max(clip_lo, min(lo_default, clip_hi))
            hi_default = max(clip_lo, min(hi_default, clip_hi))

            st.markdown(f'<div class="sidebar-section-label">{label}</div>', unsafe_allow_html=True)
            slider_min = r(clip_lo)
            slider_max = r(clip_hi) or 1.0
            chosen = st.slider(
                label, min_value=slider_min, max_value=slider_max,
                value=(r(lo_default), r(hi_default)),
                step=step, key=f"f_{field}", label_visibility="collapsed",
            )
            # indian_number() rounds to whole numbers -- fine for the
            # crore-scale currency fields, but a small-range ratio field
            # (beta, quick ratio, PEG) at decimals=0 would show a misleading
            # "0 - 0" for a real, non-empty (0.00, 0.50) selection.
            if decimals:
                value_line = f"{chosen[0]:.{decimals}f} – {chosen[1]:.{decimals}f}"
            else:
                value_line = f"{indian_number(chosen[0])} – {indian_number(chosen[1])}"
            st.markdown(
                f'<div style="font-family:\'IBM Plex Mono\',monospace;font-weight:600;'
                f'font-size:12.5px;color:{COLOR_ACCENT};margin:-4px 0 7px">{value_line}</div>',
                unsafe_allow_html=True,
            )
            # A slider left (or dragged back out) at its clipped edge means
            # "no limit" on that side -- otherwise the clip above would
            # exclude the very outlier it's meant to keep filterable, not hide.
            eff_lo = data_min if chosen[0] <= slider_min else chosen[0]
            eff_hi = data_max if chosen[1] >= slider_max else chosen[1]
            range_values[field] = (eff_lo * divisor, eff_hi * divisor)

        st.markdown('<div class="sidebar-section-label">MAX PROMOTER PLEDGE</div>', unsafe_allow_html=True)
        pledge_default = qp_float("pledge_max", 100.0)
        pledge_max = st.slider(
            "Max promoter pledge", min_value=0.0, max_value=100.0,
            value=float(pledge_default), step=1.0,
            key="f_pledge_max", label_visibility="collapsed",
        )

        if st.button("Reset all filters"):
            for key in FILTER_WIDGET_KEYS:
                st.session_state.pop(key, None)
            for qp_key in FILTER_QP_KEYS:
                if qp_key in st.query_params:
                    del st.query_params[qp_key]
            st.rerun()

        st.markdown('<div style="height:2px;background:#1C1B19;margin:18px 0"></div>', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-section-label" style="margin-bottom:2px">FACTOR WEIGHTS</div>', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-subtitle">re-rank live by what you value</div>', unsafe_allow_html=True)

        weights = {}
        for metric in METRICS:
            label = FACTOR_LABELS[metric]
            default_w = qp_int(f"w_{metric}", 5)
            weights[metric] = st.slider(
                label, min_value=0, max_value=10, value=default_w, step=1,
                key=f"w_{metric}",
            )

    filters = {
        "sectors": sectors,
        **range_values,
        "promoter_pledge_pct_max": pledge_max,
    }
    return filters, weights


# ----------------------------------------------------------------------------
# Main ranked table view
# ----------------------------------------------------------------------------

def build_display_table(filtered):
    display = pd.DataFrame({
        "Rank": range(1, len(filtered) + 1),
        "Company": filtered["name"] + "  ·  " + filtered["symbol"],
        "Sector": filtered["ey_bucket"].map(sector_display_name),
        "Score": filtered["score"].round(0),
        "Revenue": filtered["revenue"].apply(format_cr_plain),
        "Margin": filtered["ebitda_margin_pct"].apply(lambda v: format_pct(v)),
        "ROCE": filtered["return_on_capital_employed_pct"].apply(lambda v: format_pct(v)),
        "Debt": filtered["total_debt"].apply(format_cr_plain),
        "Mcap": filtered["market_cap"].apply(format_cr_plain),
        "Pledge": filtered["promoter_pledge_pct"].apply(lambda v: format_pct(v)),
    })
    return display


def render_table_view(universe, filters, weights):
    as_of = get_data_as_of(universe)

    scored = score_universe(universe, tuple(sorted(weights.items())))
    scored = scored.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)
    filtered = filter_companies(scored, filters)

    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(
            f'<div class="data-as-of">DATA AS OF <span>{as_of}</span></div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.download_button(
            "Download CSV ↓",
            data=filtered.drop(columns=["ey_bucket"], errors="ignore").to_csv(index=False).encode("utf-8"),
            file_name="nse_ma_screener_results.csv",
            mime="text/csv",
            use_container_width=True,
        )

    if filtered.empty:
        st.markdown(f'''
<div class="no-results-card">
  <div class="no-results-title">No companies match these filters.</div>
  <div class="no-results-sub">Try widening your ranges.</div>
</div>''', unsafe_allow_html=True)
        if st.button("Reset Filters", key="reset_zero_results"):
            for key in FILTER_WIDGET_KEYS:
                st.session_state.pop(key, None)
            for qp_key in FILTER_QP_KEYS:
                if qp_key in st.query_params:
                    del st.query_params[qp_key]
            st.rerun()
        return

    display = build_display_table(filtered)

    event = st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=min(36 * (len(display) + 1) + 3, 720),
        column_config={
            "Rank": st.column_config.NumberColumn(width="small"),
            "Company": st.column_config.TextColumn(width="large"),
            "Sector": st.column_config.TextColumn(width="medium"),
            "Score": st.column_config.ProgressColumn(
                format="%.0f", min_value=0, max_value=100, width="medium",
            ),
            "Revenue": st.column_config.TextColumn(width="small"),
            "Margin": st.column_config.TextColumn(width="small"),
            "ROCE": st.column_config.TextColumn(width="small"),
            "Debt": st.column_config.TextColumn(width="small"),
            "Mcap": st.column_config.TextColumn(width="small"),
            "Pledge": st.column_config.TextColumn(width="small"),
        },
        on_select="rerun",
        selection_mode="single-row",
        key="results_table",
    )

    if event.selection and event.selection.get("rows"):
        selected_idx = event.selection["rows"][0]
        symbol = filtered.iloc[selected_idx]["symbol"]
        st.query_params["view"] = "tearsheet"
        st.query_params["symbol"] = symbol
        st.rerun()


# ----------------------------------------------------------------------------
# Tear sheet view
# ----------------------------------------------------------------------------

def render_tearsheet(universe, weights, symbol):
    scored = score_universe(universe, tuple(sorted(weights.items())))
    match = scored[scored["symbol"] == symbol]
    if match.empty:
        st.warning("Company not found.")
        if st.button("← Back to results"):
            del st.query_params["view"]
            del st.query_params["symbol"]
            st.rerun()
        return
    row = match.iloc[0]
    bucket = row["ey_bucket"]
    as_of = get_data_as_of(universe)

    st.markdown('<span class="back-btn-marker"></span>', unsafe_allow_html=True)
    if st.button("← Back to results", key="back_button"):
        del st.query_params["view"]
        del st.query_params["symbol"]
        st.rerun()

    st.markdown(f'''
<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:30px">
  <div>
    <div class="tearsheet-name">{row["name"]}</div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:10px">
      <span class="sector-badge">{sector_display_name(bucket).upper()}</span>
      <span class="tearsheet-meta">{row["symbol"]} · MKT CAP {format_cr(row["market_cap"])} · AS OF {as_of}</span>
    </div>
  </div>
</div>''', unsafe_allow_html=True)

    donut = donut_html(row["score"])
    factor_bars = "".join(
        factor_bar_html(FACTOR_LABELS[m], row[f"pctl_{m}"]) for m in METRICS
    )
    st.markdown(f'''
<div style="display:flex;gap:44px;margin-bottom:34px;align-items:center">
  <div style="flex:0 0 170px;display:flex;align-items:center;justify-content:center">{donut}</div>
  <div style="flex:1;display:flex;flex-direction:column;gap:4px">
    <div class="section-label">SCORE — VS. {sector_display_name(bucket).upper()} SECTOR PEERS</div>
    {factor_bars}
  </div>
</div>''', unsafe_allow_html=True)

    financial_rows = [
        ("Revenue", format_cr(row["revenue"])),
        ("EBITDA", format_cr(row["ebitda"])),
        ("EBITDA Margin", format_pct(row["ebitda_margin_pct"])),
        ("ROCE", format_pct(row["return_on_capital_employed_pct"])),
        ("Total Debt", format_cr(row["total_debt"])),
        ("Market Cap", format_cr(row["market_cap"])),
        ("Promoter Pledge", format_pct(row["promoter_pledge_pct"])),
    ]
    rows_html = "".join(
        f'<div class="card-row"><span class="card-row-label">{label}</span>'
        f'<span class="{"card-row-na" if value == "N/A" else "card-row-value"}">{value}</span></div>'
        for label, value in financial_rows
    )
    note = row["valuation_note"]
    ev_ebitda_html = valuation_block_html(
        row["ev_ebitda_low"], row["ev_ebitda_high"], "EV / EBITDA IMPLIED",
        extract_note_segment(note, "EV/EBITDA:"),
    )
    pe_html = valuation_block_html(
        row["pe_implied_low"], row["pe_implied_high"], "P/E-IMPLIED",
        extract_note_segment(note, "P/E:"),
    )

    st.markdown(f'''
<div style="display:flex;gap:24px;margin-bottom:34px">
  <div class="card" style="flex:1">
    <div class="card-header">KEY FINANCIALS</div>
    {rows_html}
  </div>
  <div class="card" style="flex:1">
    <div class="card-header">INDICATIVE VALUATION</div>
    <div style="padding:16px">{ev_ebitda_html}</div>
    <div style="padding:0 16px 16px">{pe_html}</div>
  </div>
</div>''', unsafe_allow_html=True)

    rationale = get_ai_rationale(row)
    rationale_text = rationale or "AI rationale unavailable right now — the rest of this tear sheet is unaffected."
    # Escaped, unlike the rest of this file's static/from-CSV markdown blocks --
    # this is the one string on the page generated at request time by an LLM
    # rather than sourced from the bundled data files, so it's treated as
    # untrusted before going into an unsafe_allow_html block (defense in depth
    # against the model ever echoing back HTML/script-like content).
    rationale_html = html.escape(rationale_text)
    st.markdown(f'''
<div style="margin-bottom:34px">
  <div class="section-label">AI RATIONALE</div>
  <div class="rationale-quote">
    <div class="rationale-mark">"</div>
    <div class="rationale-text">{rationale_html}</div>
  </div>
</div>''', unsafe_allow_html=True)

    deals = load_all_deals()
    comps = deals[deals["ey_bucket"] == bucket].copy()
    comps = comps.sort_values("report_year", ascending=False).head(5)

    st.markdown(f'<div class="section-label">COMPARABLE DEALS — {sector_display_name(bucket).upper()}</div>', unsafe_allow_html=True)
    if comps.empty:
        st.markdown('<div class="no-comps">No comparable 2025 Indian M&A deals found in this sector.</div>', unsafe_allow_html=True)
    else:
        def text_or_na(value):
            return value if pd.notna(value) else "N/A"

        deal_rows = ""
        for _, deal in comps.iterrows():
            value = deal["deal_value_usdm_numeric"]
            value_text = f"US${value:,.0f}m" if pd.notna(value) else "N/A"
            deal_rows += f'''<div class="deal-row">
  <div style="flex:1" class="deal-target">{text_or_na(deal["target"])}</div>
  <div style="flex:1">{text_or_na(deal["acquirer"])}</div>
  <div style="width:110px;text-align:right;font-family:'IBM Plex Mono',monospace">{value_text}</div>
  <div style="width:180px">{text_or_na(deal["deal_type"])}</div>
  <div style="width:56px;text-align:right">{text_or_na(deal["report_year"])}</div>
</div>'''
        st.markdown(f'''
<div style="border-top:2px solid {COLOR_TEXT}">
  <div class="deal-header"><div style="flex:1">TARGET</div><div style="flex:1">ACQUIRER</div>
    <div style="width:110px;text-align:right">VALUE</div><div style="width:180px">TYPE</div>
    <div style="width:56px;text-align:right">YEAR</div></div>
  {deal_rows}
</div>''', unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    inject_css()
    universe = load_universe()

    view = st.query_params.get("view", "table")
    symbol = st.query_params.get("symbol")

    if view == "tearsheet" and symbol:
        filters, weights = render_sidebar(universe)
        sync_query_params(filters, weights)
        render_tearsheet(universe, weights, symbol)
    else:
        filters, weights = render_sidebar(universe)
        sync_query_params(filters, weights)
        render_table_view(universe, filters, weights)


if __name__ == "__main__":
    main()
