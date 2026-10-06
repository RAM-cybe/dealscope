"""Deterministic repair of values that are impossible for a real company.

Replaces the human "NEEDS MANUAL REVIEW" step for the clear-cut cases. The
rule is never to invent a number: an impossible value is replaced by the
last-good value from the live dataset when that value is itself valid,
otherwise it is set to null (the site renders null as "n/a" and the scoring
code already tolerates it).

Only value ranges that are impossible are enforced. "Extreme but possible"
values (a real ROCE of 300%) are left to quality_checks.py to report.

    cleaned, repairs = sanitize(df, live=live_df)

`repairs` has one row per changed cell (see REPAIR_COLUMNS) and is written to
data/quality_reports/ as the audit trail.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.quality_checks import (
    EBITDA_MARGIN_ABS_LIMIT,
    EBITDA_MATERIALITY_FLOOR,
    ZERO_MARGIN_EPSILON,
)

REPAIR_COLUMNS = ["symbol", "field", "before", "after", "reason", "source"]

# field -> (low, high); None means unbounded on that side. Inclusive.
RANGE_RULES = {
    "insider_holding_pct": (0.0, 100.0),
    "promoter_pledge_pct": (0.0, 100.0),
    "revenue": (0.0, None),
    "total_debt": (0.0, None),
    "market_cap": (0.0, None),
    "current_ratio": (0.0, 100.0),
    "quick_ratio": (0.0, 100.0),
    "beta": (-10.0, 10.0),
    "ebitda_margin_pct": (-EBITDA_MARGIN_ABS_LIMIT, EBITDA_MARGIN_ABS_LIMIT),
}

# Fields derived from revenue. When revenue is repaired they cannot be
# trusted, so they travel with it: reverted together to one consistent live
# snapshot, or nulled.
REVENUE_GROUP = ["revenue", "ebitda", "ebitda_margin_pct", "revenue_growth_pct"]
REVENUE_DERIVED = ["ebitda_margin_pct", "revenue_growth_pct"]


def _to_number(value):
    """float, or NaN when missing / not numeric."""
    if value is None:
        return np.nan
    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan
    return number


def _in_range(field, number):
    low, high = RANGE_RULES[field]
    if low is not None and number < low:
        return False
    if high is not None and number > high:
        return False
    return True


def _is_bad(field, value):
    """True when `value` is present but impossible. Missing is not bad."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    number = _to_number(value)
    if np.isnan(number):
        return True  # present but junk text such as "n/a" or "inf"
    if np.isinf(number):
        return True
    return not _in_range(field, number)


def _is_good(field, value):
    number = _to_number(value)
    return not np.isnan(number) and not np.isinf(number) and _in_range(field, number)


def _reason(field, value):
    number = _to_number(value)
    if np.isnan(number):
        return f"{field} is not a number"
    low, high = RANGE_RULES[field]
    bound = f"{low:g}..{high:g}" if low is not None and high is not None else f">= {low:g}"
    return f"{field}={number:g} outside {bound}"


def _live_lookup(live):
    if live is None or live.empty or "symbol" not in live.columns:
        return {}
    return live.drop_duplicates("symbol").set_index("symbol").to_dict("index")


def sanitize(df, live=None):
    out = df.copy(deep=True)
    repairs = []
    live_rows = _live_lookup(live)

    def log(symbol, field, before, after, reason, source):
        repairs.append({"symbol": symbol, "field": field, "before": before,
                        "after": after, "reason": reason, "source": source})

    def set_cell(idx, field, value):
        # Object dtype first so a text/NaN/number mix is assignable on both
        # pandas 2.x and 3.x.
        if out[field].dtype != object and not pd.api.types.is_float_dtype(out[field]):
            out[field] = out[field].astype(object)
        out.at[idx, field] = value

    for idx in out.index:
        symbol = out.at[idx, "symbol"] if "symbol" in out.columns else None
        live_row = live_rows.get(symbol, {})

        # 1. Revenue first: its derived fields depend on the outcome.
        if "revenue" in out.columns and _is_bad("revenue", out.at[idx, "revenue"]):
            before = out.at[idx, "revenue"]
            group = [f for f in REVENUE_GROUP if f in out.columns]
            live_ok = bool(live_row) and _is_good("revenue", live_row.get("revenue"))
            if live_ok:
                for f in group:
                    old = out.at[idx, f]
                    new = live_row.get(f, np.nan)
                    if f == "ebitda_margin_pct" and not _is_good(f, new):
                        new = np.nan
                    if not (pd.isna(old) and pd.isna(new)) and old != new:
                        set_cell(idx, f, new)
                        log(symbol, f, old, new, _reason("revenue", before), "live")
            else:
                set_cell(idx, "revenue", np.nan)
                log(symbol, "revenue", before, np.nan, _reason("revenue", before), "null")
                for f in REVENUE_DERIVED:
                    if f in out.columns and pd.notna(out.at[idx, f]):
                        old = out.at[idx, f]
                        set_cell(idx, f, np.nan)
                        log(symbol, f, old, np.nan, "derived from invalid revenue", "null")

        # 2. Every other ranged field.
        for field in RANGE_RULES:
            if field == "revenue" or field not in out.columns:
                continue
            value = out.at[idx, field]
            if not _is_bad(field, value):
                continue
            fallback = live_row.get(field, np.nan) if live_row else np.nan
            if _is_good(field, fallback):
                set_cell(idx, field, fallback)
                log(symbol, field, value, fallback, _reason(field, value), "live")
            else:
                set_cell(idx, field, np.nan)
                log(symbol, field, value, np.nan, _reason(field, value), "null")

        # 3. Margin stored as ~0 while EBITDA is materially non-zero is
        #    impossible for any finite revenue: recompute or null.
        if {"ebitda_margin_pct", "ebitda"} <= set(out.columns):
            margin = _to_number(out.at[idx, "ebitda_margin_pct"])
            ebitda = _to_number(out.at[idx, "ebitda"])
            if (not np.isnan(margin) and abs(margin) <= ZERO_MARGIN_EPSILON
                    and not np.isnan(ebitda) and abs(ebitda) >= EBITDA_MATERIALITY_FLOOR):
                revenue = _to_number(out.at[idx, "revenue"]) if "revenue" in out.columns else np.nan
                recomputed = ebitda / revenue * 100.0 if revenue > 0 else np.nan
                if not np.isnan(recomputed) and abs(recomputed) <= EBITDA_MARGIN_ABS_LIMIT:
                    set_cell(idx, "ebitda_margin_pct", recomputed)
                    log(symbol, "ebitda_margin_pct", margin, recomputed,
                        "margin ~0 with material ebitda", "recomputed")
                else:
                    set_cell(idx, "ebitda_margin_pct", np.nan)
                    log(symbol, "ebitda_margin_pct", margin, np.nan,
                        "margin ~0 with material ebitda", "null")

    return out, pd.DataFrame(repairs, columns=REPAIR_COLUMNS)
