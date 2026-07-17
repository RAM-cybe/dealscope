"""DealScope — Streamlit app.

Pipeline (composition-order contract from scoring.py / valuation.py):
load_companies() -> score_companies() + valuation_range() on the FULL
universe -> filter_companies() last, purely for display.

UI: the "DealScope - Final Design" direction — a dark, teal-accented,
five-view flow: landing/search -> results (score-ring table) -> tear sheet,
with an advanced-filters slide-over reachable from a top-bar button. The
data/logic layer under src/ is unchanged; this file is presentation only.
"""

import html
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.data.loaders import load_companies, load_deals, get_data_as_of
from src.data.schema import EY_BUCKETS, UNCLASSIFIED_BUCKET, ALL_BUCKETS
from src.logic.filtering import filter_companies
from src.logic.scoring import score_companies, METRICS
from src.logic.valuation import valuation_range
from src.logic.zscore import compute_zscore
from src.logic.piotroski import compute_piotroski
from src.config import get_gemini_api_key, get_groq_api_key, get_cerebras_api_key
from src.data.filings import fetch_all_nse_filings, fetch_bse_notices, match_filings_to_company, parse_pub_date, NSE_FEEDS
from src.data.news import fetch_company_news

# ----------------------------------------------------------------------------
# Palette — "DealScope Final Design" dark/teal system
# ----------------------------------------------------------------------------

C_BG = "#05070a"          # page background
C_CARD = "#0c0f14"        # primary card / results table body
C_CARD2 = "#12161c"       # inner panels, stat cards, inputs
C_PANEL = "#101319"       # drawer, dashed "insufficient data" cards
C_ROW_ALT = "rgba(255,255,255,.025)"
C_TEAL = "#1fb8a3"        # primary accent
C_TEAL_LT = "#5dcaa5"     # lighter teal (links, mono figures)
C_TEAL_DK = "#123834"     # de-emphasised teal chip bg / valuation gradient start
C_TEAL_DK2 = "#0f2b28"    # valuation gradient end
C_INK = "#04110e"         # text on a teal fill
C_T1 = "#eef1f4"          # primary text
C_T2 = "#c7ced6"          # secondary text
C_T3 = "#8b96a5"          # muted text
C_T4 = "#69727d"          # dim text
C_T5 = "#546070"          # dimmer (labels, ranks)
C_T6 = "#3d454e"          # very dim (sparse / disabled)
C_BORDER = "rgba(255,255,255,.08)"
C_BORDER2 = "rgba(255,255,255,.14)"
C_TRACK = "rgba(255,255,255,.1)"
C_WARN = "#d4a441"        # muted amber -- Z''-Score "Grey" zone
C_DANGER = "#d16d65"      # muted coral/red -- Z''-Score "Distress" zone

FACTOR_LABELS = {
    "revenue_growth_pct": "Revenue Growth",
    "ebitda_margin_pct": "EBITDA Margin",
    "return_on_capital_employed_pct": "ROCE",
    "total_debt": "Debt Level",
}

# The design's slide-over carries exactly the original locked-PRD filter set
# (5 range filters + a promoter-pledge ceiling; sector is chips, not a slider).
# The interim 20-slider sidebar's extra enriched-field controls are not part
# of this design and are intentionally not surfaced here — filtering.py still
# supports them at the logic layer, they're simply not exposed as UI controls.
# (Part 3 of the 2026-07-17 round exposes these -- see that round's commits.)
RANGE_FIELD_CONFIG = [
    # (filters.py key, label, unit divisor for crore conversion)
    ("revenue", "REVENUE (₹ CR)", 1e7),
    ("ebitda_margin_pct", "EBITDA MARGIN %", 1),
    ("return_on_capital_employed_pct", "ROCE %", 1),
    ("total_debt", "TOTAL DEBT (₹ CR)", 1e7),
    ("market_cap", "MARKET CAP (₹ CR)", 1e7),
]

RANGE_FIELD_NAMES = [field for field, _, _ in RANGE_FIELD_CONFIG]
FILTER_WIDGET_KEYS = (
    [f"f_{field}" for field in RANGE_FIELD_NAMES] + ["f_pledge_max"]
)
FILTER_QP_KEYS = ["sectors"] + RANGE_FIELD_NAMES + ["pledge_max"]

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
    return {
        "Consumer Products and Retail": "Consumer Products",
        "Industrials and Auto": "Industrials & Auto",
        "Financial Services": "Financial Services",
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
    """load_companies() + valuation_range() + the Part 1 financial-health
    scores (z_score/z_score_zone, f_score) on the full universe.
    Weight-independent -- same composition-order contract as scoring.py's
    module docstring: computed once here on the full unfiltered universe,
    never recomputed on a filtered subset."""
    df = load_companies()
    df = valuation_range(df)
    df = compute_zscore(df)
    df = compute_piotroski(df)
    return df


@st.cache_data(show_spinner=False)
def score_universe(df, weights_tuple):
    weights = dict(weights_tuple)
    return score_companies(df, weights)


@st.cache_data(show_spinner=False)
def load_all_deals():
    return load_deals()


# Part 2: filings/news caching. NSE's archive host silently throttles bursts
# of requests (confirmed empirically -- see src/data/filings.py's module
# docstring), so these are fetched at most once per cache window across ALL
# visitors, never per tear-sheet page view. 30 min for filings (these change
# slowly -- a company files a handful of times a month), 15 min for news
# (moves faster, but still far from per-request).
@st.cache_data(show_spinner=False, ttl=1800)
def load_nse_filings():
    return fetch_all_nse_filings()


@st.cache_data(show_spinner=False, ttl=1800)
def load_bse_notices():
    return fetch_bse_notices()


@st.cache_data(show_spinner=False, ttl=900)
def load_company_news(company_name):
    return fetch_company_news(company_name)


@st.cache_data(show_spinner=False)
def sector_avg_scores(scored):
    """Mean composite score within each ey_bucket, for the ring's sector tick."""
    return scored.groupby("ey_bucket")["score"].mean().to_dict()


# ----------------------------------------------------------------------------
# CSS
# ----------------------------------------------------------------------------

def inject_css():
    panel_open = st.query_params.get("panel") == "1"
    drawer_x = "0" if panel_open else "112%"
    scrim_display = "block" if panel_open else "none"
    css = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
html, body, [class*="css"], .stApp {{
    font-family: 'Inter', system-ui, sans-serif;
    color: {C_T1};
}}
.stApp {{ background: {C_BG}; }}
#MainMenu, header[data-testid="stHeader"], footer, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display: none !important; }}
[data-testid="collapsedControl"] {{ display: none !important; }}
section[data-testid="stSidebar"] {{ display: none !important; }}
.block-container {{ padding: 2.2rem 3rem 4rem; max-width: 1180px; }}
a {{ color: {C_TEAL_LT}; text-decoration: none; }}
hr {{ border-color: {C_BORDER}; }}

/* Generic buttons -> pill/rounded dark */
div.stButton > button, div.stFormSubmitButton > button {{
    background: rgba(255,255,255,.06); color: {C_T2}; border: 1px solid {C_BORDER2};
    border-radius: 10px; font-weight: 600; font-size: 11.5px; padding: 7px 10px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
div.stButton > button:hover, div.stFormSubmitButton > button:hover {{
    border-color: {C_TEAL}; color: {C_T1};
}}
/* Selected sector chip = primary button */
div.stButton > button[kind="primary"], div.stButton > button[data-testid="baseButton-primary"] {{
    background: {C_TEAL}; color: {C_INK}; border: none; font-weight: 700;
}}
div.stButton > button[kind="primary"]:hover {{ background: {C_TEAL_LT}; color: {C_INK}; }}

div.stDownloadButton > button {{
    background: rgba(255,255,255,.06); color: {C_TEAL_LT}; border: 1px solid rgba(31,184,163,.4);
    border-radius: 10px; font-weight: 700; font-size: 12px; padding: 8px 14px;
}}
div.stDownloadButton > button:hover {{ background: {C_TEAL}; color: {C_INK}; border-color: {C_TEAL}; }}

/* Text input -> pill */
div[data-testid="stTextInput"] input {{
    background: {C_CARD2}; border: 1px solid {C_BORDER2}; border-radius: 999px;
    color: {C_T1}; font-size: 14px; padding: 12px 20px;
}}
div[data-testid="stTextInput"] input::placeholder {{ color: {C_T4}; }}
div[data-testid="stTextInput"] input:focus {{ border-color: {C_TEAL}; box-shadow: none; }}

/* Sliders -> teal */
div[data-testid="stSlider"] [data-baseweb="slider"] > div > div {{ background: {C_TEAL} !important; }}
div[data-testid="stSlider"] [role="slider"] {{ background: {C_TEAL} !important; border-color: {C_TEAL} !important; }}
div[data-testid="stSlider"] [data-testid="stTickBarMin"],
div[data-testid="stSlider"] [data-testid="stTickBarMax"] {{ color: {C_T5}; }}

/* Multiselect (sectors, when used) -> dark teal chips */
div[data-testid="stMultiSelect"] [data-baseweb="tag"] {{ background: {C_TEAL_DK}; }}

/* ---- Advanced-filters slide-over ---- */
#dwr-scrim {{
    position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 998;
    display: {scrim_display};
}}
.st-key-filterdrawer {{
    position: fixed; top: 0; right: 0; height: 100vh; width: 380px; z-index: 999;
    background: {C_PANEL}; border-left: 1px solid {C_BORDER2};
    box-shadow: -30px 0 60px -20px rgba(0,0,0,.6);
    padding: 22px 26px; overflow-y: auto;
    transform: translateX({drawer_x}); transition: transform .18s ease;
}}
.st-key-filterdrawer .stSlider {{ margin-bottom: -6px; }}

.dwr-title {{ font-size: 14px; font-weight: 700; color: {C_T1}; }}
.dwr-grouplabel {{ font-size: 10.5px; letter-spacing: .06em; color: {C_T3}; font-weight: 600;
    margin: 18px 0 6px; }}
.dwr-fieldlabel {{ display: flex; justify-content: space-between; align-items: center;
    font-size: 10.5px; letter-spacing: .05em; color: {C_T3}; font-weight: 600; margin-bottom: -6px; }}
.dwr-fieldval {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: {C_TEAL_LT}; font-weight: 500; }}

/* Wordmark */
.brand {{ display: flex; align-items: center; gap: 8px; }}
.brand-dot {{ width: 8px; height: 8px; border-radius: 2px; background: {C_TEAL}; }}
.brand-name {{ font-weight: 800; font-size: 12px; letter-spacing: .2em; color: {C_T1}; }}
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
                    f'background:{C_T1};border-radius:1px;transform:translateX(-50%)"></div></div>')
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
    return (f'<div style="padding:{pad};background:{C_CARD2};border-radius:{"10px" if small else "12px"};'
            f'border:1px solid {C_BORDER}">'
            f'<div style="font:700 {lbl_size} Inter,sans-serif;letter-spacing:.05em;color:{C_T5};margin-bottom:{"5px" if small else "7px"}">{esc(label)}</div>'
            f'<div style="font:700 {val_size} \'IBM Plex Mono\',monospace;color:{value_color}">{esc(value)}</div></div>')


def breakdown_bar_html(label, weight, percentile):
    wt = f'<span style="color:{C_T5};font-weight:400">wt {weight}</span>'
    if pd.isna(percentile):
        return (f'<div><div style="display:flex;justify-content:space-between;margin-bottom:6px">'
                f'<span style="font:600 12.5px Inter,sans-serif;color:{C_T5}">{label} {wt}</span>'
                f'<span style="font:600 11.5px Inter,sans-serif;color:{C_T5}">reweighted — no data</span></div>'
                f'<div style="height:7px;border-radius:4px;background:rgba(255,255,255,.04)"></div></div>')
    pct = max(0, min(100, percentile))
    return (f'<div><div style="display:flex;justify-content:space-between;margin-bottom:6px">'
            f'<span style="font:600 12.5px Inter,sans-serif;color:{C_T2}">{label} {wt}</span>'
            f'<span style="font:700 12.5px \'IBM Plex Mono\',monospace;color:{C_TEAL_LT}">{pct:.0f}</span></div>'
            f'<div style="height:7px;border-radius:4px;background:rgba(255,255,255,.08)">'
            f'<div style="width:{pct}%;height:100%;border-radius:4px;background:{C_TEAL}"></div></div></div>')


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


def qp_list(key, default):
    raw = st.query_params.get(key)
    if raw is None:
        return default
    return [s for s in raw.split(",") if s]


def current_sectors():
    """Selected sectors from the URL; empty list means 'all sectors'."""
    sel = [s for s in qp_list("sectors", []) if s in ALL_BUCKETS]
    return sel


def current_weights():
    return {m: qp_int(f"w_{m}", 5) for m in METRICS}


# ----------------------------------------------------------------------------
# Shared UI pieces
# ----------------------------------------------------------------------------

def brand_markup():
    return (f'<div class="brand"><div class="brand-dot"></div>'
            f'<div class="brand-name">DEALSCOPE</div></div>')


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


def render_sector_chips(target_view):
    """Sector chips as toggle buttons. Clicking one navigates to target_view
    with that sector toggled in the URL."""
    selected = set(current_sectors())
    labels = [(b, sector_display_name(b)) for b in ALL_BUCKETS]
    cols = st.columns(len(labels))
    for (bucket, label), col in zip(labels, cols):
        is_on = bucket in selected
        if col.button(label, key=f"chip_{bucket}",
                      type="primary" if is_on else "secondary",
                      use_container_width=True):
            if is_on:
                selected.discard(bucket)
            else:
                selected.add(bucket)
            new = ",".join(b for b in ALL_BUCKETS if b in selected)
            go(target_view, sectors=new or None, page=None)


def render_filter_drawer(universe):
    """Right slide-over: real range sliders + factor-weight sliders + Reset/Apply.
    Always rendered on results view so its values are readable every run; CSS
    keeps it off-screen unless ?panel=1."""
    range_values = {}
    with st.container(key="filterdrawer"):
        st.markdown('<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
                    f'<span class="dwr-title">Advanced filters</span></div>', unsafe_allow_html=True)

        for field, label, divisor in RANGE_FIELD_CONFIG:
            series = universe[field] / divisor
            data_min = float(series.min(skipna=True))
            data_max = float(series.max(skipna=True))
            data_min = 0.0 if pd.isna(data_min) else data_min
            data_max = 100.0 if pd.isna(data_max) else data_max

            clip_lo = float(series.quantile(0.01)) if series.notna().any() else data_min
            clip_hi = float(series.quantile(0.99)) if series.notna().any() else data_max
            if pd.isna(clip_lo) or pd.isna(clip_hi) or clip_hi <= clip_lo:
                clip_lo, clip_hi = data_min, data_max

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

            slider_min = r(clip_lo)
            slider_max = r(clip_hi) or 1.0
            chosen = st.slider(
                label, min_value=slider_min, max_value=slider_max,
                value=(r(lo_default), r(hi_default)),
                step=step, key=f"f_{field}", label_visibility="visible",
            )
            eff_lo = data_min if chosen[0] <= slider_min else chosen[0]
            eff_hi = data_max if chosen[1] >= slider_max else chosen[1]
            range_values[field] = (eff_lo * divisor, eff_hi * divisor)

        pledge_default = qp_float("pledge_max", 100.0)
        pledge_max = st.slider(
            "MAX PROMOTER PLEDGE %", min_value=0.0, max_value=100.0,
            value=float(pledge_default), step=1.0, key="f_pledge_max",
        )

        st.markdown('<div class="dwr-grouplabel">FACTOR WEIGHTS</div>', unsafe_allow_html=True)
        weights = {}
        for metric in METRICS:
            weights[metric] = st.slider(
                FACTOR_LABELS[metric], min_value=0, max_value=10,
                value=qp_int(f"w_{metric}", 5), step=1, key=f"w_{metric}",
            )

        c1, c2 = st.columns(2)
        if c1.button("Reset", key="dwr_reset", use_container_width=True):
            for k in FILTER_QP_KEYS + [f"w_{m}" for m in METRICS]:
                st.query_params.pop(k, None)
            for k in FILTER_WIDGET_KEYS + [f"w_{m}" for m in METRICS]:
                st.session_state.pop(k, None)
            st.query_params.pop("panel", None)
            st.rerun()
        if c2.button("Apply", key="dwr_apply", type="primary", use_container_width=True):
            _persist_filters(range_values, pledge_max, weights)
            st.query_params.pop("panel", None)
            st.rerun()

    # Persist current slider state to the URL every run so it survives reloads
    # and is shareable, exactly like the pre-redesign behaviour.
    _persist_filters(range_values, pledge_max, weights)

    filters = {"sectors": current_sectors(), **range_values,
               "promoter_pledge_pct_max": pledge_max}
    return filters, weights


def _persist_filters(range_values, pledge_max, weights):
    for field in RANGE_FIELD_NAMES:
        lo, hi = range_values[field]
        st.query_params[field] = f"{lo},{hi}"
    st.query_params["pledge_max"] = str(pledge_max)
    for metric in METRICS:
        st.query_params[f"w_{metric}"] = str(weights[metric])


# ----------------------------------------------------------------------------
# 1 · Landing / search
# ----------------------------------------------------------------------------

def render_landing(universe):
    as_of = get_data_as_of(universe)
    n = len(universe)

    top = st.columns([2, 1])
    with top[1]:
        if st.button("⚙ Advanced filters", key="land_adv", use_container_width=True):
            go("results", panel="1")

    st.markdown(f'''
<div style="text-align:center;padding:40px 0 8px">
  <div style="display:inline-flex;align-items:center;gap:8px;margin-bottom:28px">
    <div class="brand-dot"></div>
    <div class="brand-name">DEALSCOPE</div>
  </div>
  <div style="font:700 42px/1.18 Inter,sans-serif;color:{C_T1};max-width:760px;margin:0 auto 16px;letter-spacing:-.01em">
    Screen NSE-listed companies<br>like a deal team.</div>
  <div style="font:400 15px/1.6 Inter,sans-serif;color:{C_T3};max-width:540px;margin:0 auto 30px">
    Filter, weight-score, and get an indicative M&amp;A valuation across {n:,} real Indian companies — no login, no setup.</div>
</div>''', unsafe_allow_html=True)

    mid = st.columns([1, 4, 1])
    with mid[1]:
        q = st.text_input("Search", key="land_search", label_visibility="collapsed",
                          placeholder="Search company or ticker…")
        if q and q.strip():
            go("results", q=q.strip())

    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
    render_sector_chips("results")
    browse = st.columns([2, 3, 2])
    if browse[1].button("Browse all companies →", key="land_browse", use_container_width=True):
        go("results")

    st.markdown(f'''
<div style="text-align:center;margin-top:34px;font:400 11px 'IBM Plex Mono',monospace;
letter-spacing:.04em;color:{C_T6}">DATA AS OF {esc(as_of)} · {n:,} COMPANIES</div>''',
                unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# 2 · Results / browsing
# ----------------------------------------------------------------------------

def results_table_html(view, sector_avgs):
    header = (f'<div style="display:flex;padding:9px 14px;font:700 10px Inter,sans-serif;'
              f'letter-spacing:.07em;color:{C_T5}">'
              f'<div style="width:40px">RANK</div><div style="flex:1">COMPANY</div>'
              f'<div style="width:150px">SECTOR</div><div style="width:70px">SCORE</div>'
              f'<div style="width:104px;text-align:right">REVENUE</div>'
              f'<div style="width:78px;text-align:right">MARGIN</div>'
              f'<div style="width:64px;text-align:right">ROCE</div>'
              f'<div style="width:110px;text-align:right">DEBT</div></div>')
    rows = []
    for i, (_, r) in enumerate(view.iterrows()):
        alt = C_ROW_ALT if i % 2 == 0 else "transparent"
        rank = f'{r["_rank"]:.0f}' if pd.notna(r["_rank"]) else "—"
        rank_color = C_T5 if pd.notna(r["_rank"]) else C_T6
        avg = sector_avgs.get(r["ey_bucket"])
        ring = ring_html(r["score"], avg, size=34, inner_bg=(C_CARD if i % 2 else "#0e1217"))
        name_color = C_T1 if pd.notna(r["score"]) else C_T3
        rev = format_cr_plain(r["revenue"]); mar = format_pct(r["ebitda_margin_pct"])
        roce = format_pct(r["return_on_capital_employed_pct"]); debt = format_cr_plain(r["total_debt"])

        def cell(width, value):
            color = C_T2 if value != "N/A" else C_T5
            return (f'<div style="width:{width};text-align:right;'
                    f'font:500 12.5px \'IBM Plex Mono\',monospace;color:{color}">{esc(value)}</div>')

        rows.append(
            f'<a href="?view=tearsheet&symbol={esc(r["symbol"])}" target="_self" '
            f'style="display:flex;align-items:center;padding:11px 14px;background:{alt};'
            f'border-radius:8px;text-decoration:none">'
            f'<div style="width:40px;font:700 12px \'IBM Plex Mono\',monospace;color:{rank_color}">{rank}</div>'
            f'<div style="flex:1"><span style="font:600 13.5px Inter,sans-serif;color:{name_color}">{esc(r["name"])}</span> '
            f'<span style="font:400 11px \'IBM Plex Mono\',monospace;color:{C_T5}">{esc(r["symbol"])}</span></div>'
            f'<div style="width:150px;font:500 12.5px Inter,sans-serif;color:{C_T3}">{esc(sector_display_name(r["ey_bucket"]))}</div>'
            f'<div style="width:70px">{ring}</div>'
            + cell("104px", rev) + cell("78px", mar) + cell("64px", roce) + cell("110px", debt)
            + '</a>'
        )
    return header + '<div style="display:flex;flex-direction:column;gap:2px">' + "".join(rows) + '</div>'


def render_results(universe):
    filters, weights = render_filter_drawer(universe)

    scored = score_universe(universe, tuple(sorted(weights.items())))
    scored = scored.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)
    filtered = filter_companies(scored, filters)

    q = st.query_params.get("q", "")
    if q:
        # regex=False: treat the query as a literal substring, so a search like
        # "L&T" or "(" can't raise a regex error (or be used as a regex-DoS vector).
        mask = (filtered["name"].str.contains(q, case=False, na=False, regex=False)
                | filtered["symbol"].str.contains(q, case=False, na=False, regex=False))
        filtered = filtered[mask].reset_index(drop=True)

    filtered["_rank"] = filtered["score"].rank(ascending=False, method="min", na_option="keep")
    sector_avgs = sector_avg_scores(scored)
    as_of = get_data_as_of(universe)

    # ---- top bar ----
    bar = st.columns([2.2, 5, 2, 1, 1])
    with bar[0]:
        if st.button("◆ DEALSCOPE", key="home", use_container_width=True):
            go("landing", q=None, page=None)
    with bar[1]:
        newq = st.text_input("Search", value=q, key="results_search",
                             label_visibility="collapsed",
                             placeholder="Search company or ticker…")
        if newq != q:
            go("results", q=(newq.strip() or None), page=None)
    with bar[2]:
        if st.button("⚙ Advanced filters", key="open_adv", use_container_width=True):
            go("results", panel="1")
    with bar[3]:
        st.download_button(
            "CSV ↓",
            data=filtered.drop(columns=["ey_bucket", "_rank"], errors="ignore").to_csv(index=False).encode("utf-8"),
            file_name="nse_ma_screener_results.csv", mime="text/csv",
            use_container_width=True,
        )
    with bar[4]:
        st.link_button("Share", url="?" + "&".join(f"{k}={v}" for k, v in st.query_params.to_dict().items()),
                       use_container_width=True)

    # ---- sector chips ----
    render_sector_chips("results")

    total = len(filtered)
    st.markdown(f'''<div style="display:flex;justify-content:space-between;align-items:baseline;
margin:14px 0 8px"><span style="font:600 12px Inter,sans-serif;color:{C_T4}">{total:,} companies matched{(" · '" + esc(q) + "'") if q else ""}</span>
<a href="?view=scoring" target="_self" style="font:600 11.5px Inter,sans-serif">How scoring works ⓘ</a></div>''',
                unsafe_allow_html=True)

    if total == 0:
        st.markdown(f'''
<div style="text-align:center;padding:44px;border:1px solid {C_BORDER2};border-radius:14px;background:{C_CARD};max-width:620px;margin:24px auto">
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
        f'<div style="background:{C_CARD};border:1px solid {C_BORDER};border-radius:14px;padding:10px 14px 16px">'
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
    # Primary back navigation, rendered first and kept OUTSIDE the try/except
    # below: go() calls st.rerun(), whose control-flow signal must never be
    # swallowed by the error handler.
    if st.button("← Back to results", key="back_button"):
        go("results", symbol=None)

    try:
        _render_tearsheet_body(universe, symbol)
    except Exception:
        # Never show a raw Streamlit traceback to a visitor. A malformed symbol,
        # an unexpected data shape, or a transient failure lands here with a
        # clean, on-theme message + a recovery button instead of the red screen.
        st.markdown(f'''
<div style="max-width:620px;margin:24px auto;padding:28px;border:1px solid {C_BORDER2};
border-radius:14px;background:{C_CARD};text-align:center">
  <div style="font:700 18px Inter,sans-serif;color:{C_T1};margin-bottom:8px">Couldn't load this company.</div>
  <div style="font:400 13px Inter,sans-serif;color:{C_T3}">Something went wrong building this tear sheet — the rest of the app is unaffected.</div>
</div>''', unsafe_allow_html=True)
        rec = st.columns([2, 1, 2])
        if rec[1].button("← Back to results", key="back_error", use_container_width=True):
            go("results", symbol=None)


def _render_tearsheet_body(universe, symbol):
    weights = current_weights()
    scored = score_universe(universe, tuple(sorted(weights.items())))
    match = scored[scored["symbol"] == symbol]
    if match.empty:
        # Not an error -- a clean empty state (symbol is URL-supplied, so esc it).
        st.markdown(f'''
<div style="max-width:620px;margin:24px auto;padding:28px;border:1px solid {C_BORDER2};
border-radius:14px;background:{C_CARD};text-align:center">
  <div style="font:700 18px Inter,sans-serif;color:{C_T1};margin-bottom:8px">Company not found.</div>
  <div style="font:400 13px Inter,sans-serif;color:{C_T3}">No company matches "{esc(symbol)}". Use "← Back to results" above.</div>
</div>''', unsafe_allow_html=True)
        return
    row = match.iloc[0]
    bucket = row["ey_bucket"]
    as_of = get_data_as_of(universe)
    avg = sector_avg_scores(scored).get(bucket)
    scored_flag = pd.notna(row["score"])

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
<div style="display:flex;align-items:flex-end;justify-content:space-between;margin:16px 0 22px">
  <div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">
      <div style="font:700 30px/1.1 Inter,sans-serif;color:{C_T1};letter-spacing:-.01em">{esc(row["name"])}</div>
      <div style="font:700 12px 'IBM Plex Mono',monospace;color:{ticker_col};background:{ticker_bg};border-radius:6px;padding:3px 9px">{esc(row["symbol"])}</div>
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
        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px">'
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
<div style="padding:22px 26px;background:{C_CARD2};border-radius:14px;border:1px solid {C_BORDER};margin-bottom:22px">
  <div style="font:700 10.5px Inter,sans-serif;letter-spacing:.06em;color:{C_T3};margin-bottom:16px">SCORE BREAKDOWN</div>
  <div style="display:flex;flex-direction:column;gap:14px">{bars}</div>
  {sparse_note}
</div>''', unsafe_allow_html=True)

    # ---- secondary stat cards ----
    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:22px">'
        + stat_card("EBITDA", format_cr(row["ebitda"]), small=True)
        + stat_card("EBITDA MARGIN", format_pct(row["ebitda_margin_pct"]), small=True)
        + stat_card("NET INCOME", format_cr(row["net_income"]), small=True)
        + stat_card("PROMOTER PLEDGE", format_pct(row["promoter_pledge_pct"]), small=True)
        + '</div>', unsafe_allow_html=True)

    # ---- financial health (Part 1: Altman Z''-Score, Piotroski F-Score) ----
    render_financial_health_card(row)

    # ---- valuation ----
    render_valuation_card(row)

    # ---- AI rationale ----
    render_rationale_card(row, scored_flag)

    # ---- comparable deals ----
    render_deals_section(bucket)

    # ---- filings & news (Part 2) ----
    render_filings_news_section(row)


def render_financial_health_card(row):
    """Part 1: Altman Z''-Score + Piotroski F-Score. Every N/A state carries
    its real reason (never a silent blank) -- see src/logic/zscore.py and
    src/logic/piotroski.py module docstrings for exactly why each can be
    unpopulated for a given company."""
    z = row.get("z_score")
    zone = row.get("z_score_zone")
    f = row.get("f_score")

    if pd.notna(z):
        zone_color = {"Safe": C_TEAL_LT, "Grey": C_WARN, "Distress": C_DANGER}.get(zone, C_T3)
        z_html = (f'<div style="font:700 22px \'IBM Plex Mono\',monospace;color:{C_T1}">{z:.2f}</div>'
                  f'<div style="font:700 10px Inter,sans-serif;letter-spacing:.05em;color:{zone_color};margin-top:3px">{esc((zone or "").upper())} ZONE</div>')
    else:
        if row.get("ey_bucket") == "Financial Services":
            z_reason = "not scored for Financial Services — Altman's model assumes a manufacturing/non-lender capital structure"
        else:
            z_reason = "insufficient data (needs working capital, retained earnings, EBIT, market cap and total liabilities all reported)"
        z_html = (f'<div style="font:600 14px Inter,sans-serif;color:{C_T4}">N/A</div>'
                  f'<div style="font:400 11px Inter,sans-serif;color:{C_T5};margin-top:3px;line-height:1.4">{esc(z_reason)}</div>')

    if pd.notna(f):
        f_html = f'<div style="font:700 22px \'IBM Plex Mono\',monospace;color:{C_T1}">{int(f)}/9</div>'
    else:
        f_html = (f'<div style="font:600 14px Inter,sans-serif;color:{C_T4}">N/A</div>'
                  f'<div style="font:400 11px Inter,sans-serif;color:{C_T5};margin-top:3px;line-height:1.4">'
                  f'insufficient two-year financial history to evaluate all 9 signals</div>')

    st.markdown(f'''
<div style="padding:22px 26px;background:{C_CARD2};border-radius:14px;border:1px solid {C_BORDER};margin-bottom:22px">
  <div style="font:700 10.5px Inter,sans-serif;letter-spacing:.06em;color:{C_T3};margin-bottom:16px">FINANCIAL HEALTH</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px">
    <div><div style="font:500 11px Inter,sans-serif;color:{C_T4};margin-bottom:6px">ALTMAN Z&apos;&apos;-SCORE</div>{z_html}</div>
    <div><div style="font:500 11px Inter,sans-serif;color:{C_T4};margin-bottom:6px">PIOTROSKI F-SCORE</div>{f_html}</div>
  </div>
</div>''', unsafe_allow_html=True)


def render_valuation_card(row):
    have_ev = pd.notna(row["ev_ebitda_low"]) and pd.notna(row["ev_ebitda_high"])
    have_pe = pd.notna(row["pe_implied_low"]) and pd.notna(row["pe_implied_high"])
    if not have_ev and not have_pe:
        note = row["valuation_note"] or "Insufficient sector peer data."
        st.markdown(f'''
<div style="padding:22px 26px;background:{C_PANEL};border-radius:14px;border:1px dashed {C_BORDER2};margin-bottom:22px">
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
border-radius:14px;border:1px solid rgba(31,184,163,.3);margin-bottom:22px">
  <div style="font:700 10.5px Inter,sans-serif;letter-spacing:.06em;color:{C_TEAL_LT};margin-bottom:14px">INDICATIVE VALUATION RANGE</div>
  <div style="display:flex;gap:44px;flex-wrap:wrap">{ev}{pe}</div>
</div>''', unsafe_allow_html=True)


def render_rationale_card(row, scored_flag):
    if not scored_flag:
        st.markdown(f'''
<div style="margin-bottom:22px;padding:20px 24px;background:{C_CARD2};border-radius:14px;border:1px solid {C_BORDER}">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
    <span style="font:700 9.5px Inter,sans-serif;letter-spacing:.08em;color:{C_T3};background:rgba(255,255,255,.08);padding:3px 8px;border-radius:5px">UNAVAILABLE</span>
    <span style="font:700 11px Inter,sans-serif;letter-spacing:.05em;color:{C_T5}">AI RATIONALE</span></div>
  <div style="font:400 13.5px/1.65 Inter,sans-serif;color:{C_T4}">Not enough reported financial data to generate an AI-drafted rationale for this company.</div>
</div>''', unsafe_allow_html=True)
        return
    rationale = get_ai_rationale(row)
    if rationale:
        badge = (f'<span style="font:700 9.5px Inter,sans-serif;letter-spacing:.08em;color:{C_INK};'
                 f'background:{C_TEAL_LT};padding:3px 8px;border-radius:5px">AI-DRAFTED</span>')
        body_color = C_T2
        text = esc(rationale)
    else:
        badge = (f'<span style="font:700 9.5px Inter,sans-serif;letter-spacing:.08em;color:{C_T3};'
                 f'background:rgba(255,255,255,.08);padding:3px 8px;border-radius:5px">UNAVAILABLE</span>')
        body_color = C_T4
        text = "AI rationale unavailable right now — the rest of this tear sheet is unaffected."
    st.markdown(f'''
<div style="margin-bottom:22px;padding:20px 24px;background:{C_CARD2};border-radius:14px;border:1px solid {C_BORDER}">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
    {badge}<span style="font:700 11px Inter,sans-serif;letter-spacing:.05em;color:{C_T5}">RATIONALE</span></div>
  <div style="font:400 13.5px/1.65 Inter,sans-serif;color:{body_color}">{text}</div>
</div>''', unsafe_allow_html=True)


def render_deals_section(bucket):
    deals = load_all_deals()
    comps = deals[deals["ey_bucket"] == bucket].copy()
    comps = comps.sort_values("report_year", ascending=False).head(5)
    label = f'<div style="font:700 10.5px Inter,sans-serif;letter-spacing:.06em;color:{C_T3};margin-bottom:10px">COMPARABLE DEALS — {esc(sector_display_name(bucket).upper())}</div>'
    if comps.empty:
        st.markdown(label + f'<div style="padding:16px 18px;background:{C_CARD2};border-radius:12px;'
                    f'font:500 13px Inter,sans-serif;color:{C_T4}">No comparable 2025 Indian M&amp;A deals found in this sector.</div>',
                    unsafe_allow_html=True)
        return
    head = (f'<div style="display:flex;padding:11px 18px;font:700 10px Inter,sans-serif;letter-spacing:.06em;color:{C_T5}">'
            f'<div style="flex:1">TARGET</div><div style="flex:1">ACQUIRER</div>'
            f'<div style="width:120px;text-align:right">VALUE</div>'
            f'<div style="width:170px">TYPE</div><div style="width:60px;text-align:right">YEAR</div></div>')
    body = ""
    for i, (_, d) in enumerate(comps.iterrows()):
        alt = C_ROW_ALT if i % 2 == 0 else "transparent"
        val = d["deal_value_usdm_numeric"]
        val_txt = f"US${val:,.0f}m" if pd.notna(val) else "—"
        def t(v):
            return esc(v) if pd.notna(v) else "N/A"
        body += (f'<div style="display:flex;padding:13px 18px;font:500 13px Inter,sans-serif;color:{C_T2};background:{alt}">'
                 f'<div style="flex:1">{t(d["target"])}</div><div style="flex:1">{t(d["acquirer"])}</div>'
                 f'<div style="width:120px;text-align:right;font:600 13px \'IBM Plex Mono\',monospace;color:{C_TEAL_LT}">{val_txt}</div>'
                 f'<div style="width:170px;color:{C_T3}">{t(d["deal_type"])}</div>'
                 f'<div style="width:60px;text-align:right;font-family:\'IBM Plex Mono\',monospace">{t(d["report_year"])}</div></div>')
    st.markdown(label + f'<div style="border-radius:12px;overflow:hidden;background:{C_CARD2}">{head}{body}</div>',
                unsafe_allow_html=True)


_HIGH_STAKES_CATEGORIES = {"Fraud", "Insolvency", "Litigation / regulatory action"}
_MEDIUM_CATEGORIES = {"Credit rating action", "Auditor resignation"}


def _filing_category_badge(category):
    if category in _HIGH_STAKES_CATEGORIES:
        bg, col = "rgba(209,109,101,.16)", C_DANGER
    elif category in _MEDIUM_CATEGORIES:
        bg, col = "rgba(212,164,65,.16)", C_WARN
    else:
        bg, col = "rgba(255,255,255,.08)", C_T3
    return (f'<span style="font:700 9px Inter,sans-serif;letter-spacing:.04em;color:{col};'
            f'background:{bg};padding:3px 7px;border-radius:5px;white-space:nowrap">{esc(category.upper())}</span>')


def render_filings_news_section(row):
    """Part 2: official NSE/BSE filings (Reg 30-tagged where the category
    is genuinely determinable) + Google News RSS. Every item shown carries
    its real source and a working link back to the original -- see
    src/data/filings.py and src/data/news.py module docstrings for the full
    sourcing/tagging discipline. Both external calls are cached (never
    re-fetched per page view) and every failure shows its real reason,
    never a silent empty state."""
    company_name = row["name"]

    st.markdown(f'<div style="font:700 10.5px Inter,sans-serif;letter-spacing:.06em;color:{C_T3};'
                f'margin:24px 0 10px">OFFICIAL FILINGS — NSE</div>', unsafe_allow_html=True)
    all_filings, feed_errors = load_nse_filings()
    matched = match_filings_to_company(all_filings, company_name)
    matched = sorted(matched, key=lambda f: parse_pub_date(f["pub_date"]) or datetime.min, reverse=True)[:8]

    if not all_filings and feed_errors:
        st.markdown(f'<div style="padding:16px 18px;background:{C_CARD2};border-radius:12px;'
                    f'font:500 13px Inter,sans-serif;color:{C_T4}">NSE filings feed unavailable right now — '
                    f'the rest of this tear sheet is unaffected.</div>', unsafe_allow_html=True)
    elif not matched:
        st.markdown(f'<div style="padding:16px 18px;background:{C_CARD2};border-radius:12px;'
                    f'font:500 13px Inter,sans-serif;color:{C_T4}">No recent official filings found for this company '
                    f'in NSE\'s currently available feeds.</div>', unsafe_allow_html=True)
    else:
        rows_html = ""
        for i, f in enumerate(matched):
            alt = C_ROW_ALT if i % 2 == 0 else "transparent"
            badge = _filing_category_badge(f["category"])
            link = f["link"] or ""
            title_html = (f'<a href="{esc(link)}" target="_blank" rel="noopener" '
                          f'style="color:{C_T1};text-decoration:none">{esc(f["title"])}</a>' if link
                          else f'<span style="color:{C_T1}">{esc(f["title"])}</span>')
            rows_html += (f'<div style="padding:12px 18px;background:{alt}">'
                          f'<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:4px">'
                          f'<div style="font:600 13px Inter,sans-serif">{title_html}</div>{badge}</div>'
                          f'<div style="font:400 11px Inter,sans-serif;color:{C_T4}">{esc(f["pub_date"])} · NSE</div></div>')
        st.markdown(f'<div style="border-radius:12px;overflow:hidden;background:{C_CARD2}">{rows_html}</div>',
                    unsafe_allow_html=True)
    if feed_errors:
        st.markdown(f'<div style="margin-top:6px;font:400 10.5px Inter,sans-serif;color:{C_T6}">'
                    f'{len(feed_errors)} of {len(NSE_FEEDS)} NSE filing categories '
                    f'temporarily unavailable.</div>', unsafe_allow_html=True)

    st.markdown(f'<div style="font:700 10.5px Inter,sans-serif;letter-spacing:.06em;color:{C_T3};'
                f'margin:22px 0 10px">NEWS</div>', unsafe_allow_html=True)
    news_items, news_error = load_company_news(company_name)
    if news_error:
        st.markdown(f'<div style="padding:16px 18px;background:{C_CARD2};border-radius:12px;'
                    f'font:500 13px Inter,sans-serif;color:{C_T4}">News unavailable right now ({esc(news_error)}) — '
                    f'the rest of this tear sheet is unaffected.</div>', unsafe_allow_html=True)
    elif not news_items:
        st.markdown(f'<div style="padding:16px 18px;background:{C_CARD2};border-radius:12px;'
                    f'font:500 13px Inter,sans-serif;color:{C_T4}">No recent news found for this company.</div>',
                    unsafe_allow_html=True)
    else:
        rows_html = ""
        for i, n in enumerate(news_items):
            alt = C_ROW_ALT if i % 2 == 0 else "transparent"
            rows_html += (f'<div style="padding:12px 18px;background:{alt}">'
                          f'<div style="font:600 13px Inter,sans-serif;margin-bottom:4px">'
                          f'<a href="{esc(n["link"])}" target="_blank" rel="noopener" '
                          f'style="color:{C_T1};text-decoration:none">{esc(n["title"])}</a></div>'
                          f'<div style="font:400 11px Inter,sans-serif;color:{C_T4}">{esc(n["source"])}'
                          f'{" · " + esc(n["pub_date"]) if n["pub_date"] else ""}</div></div>')
        st.markdown(f'<div style="border-radius:12px;overflow:hidden;background:{C_CARD2}">{rows_html}</div>',
                    unsafe_allow_html=True)

    st.markdown(f'<div style="margin-top:16px;font:400 10.5px Inter,sans-serif;color:{C_T6}">'
                f'Filings: NSE\'s official RSS feeds only, never scraped. BSE\'s official RSS coverage is '
                f'narrower (exchange-wide notices, not per-company disclosures) and is not shown here for '
                f'individual companies as a result. News: Google News RSS, shown verbatim with source and link — '
                f'not AI-summarized.</div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Scoring-help view (reachable from "How scoring works")
# ----------------------------------------------------------------------------

def render_scoring_help():
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
