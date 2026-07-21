"""One-time export: turn the real DealScope dataset into two JSON files bundled
directly inside the Next.js frontend -- no database, no network call, no
account of any kind. The site reads these as local files, on localhost and
once deployed.

Reuses the project's own scoring.py / valuation.py / loaders.py -- no
business logic is reimplemented, so the numbers match the live Streamlit app
exactly.

Run from the repo root:
    python3 export_for_frontend.py

Writes:
    deal-scope-interface/data/companies.json   -- 2,046 companies
    deal-scope-interface/data/deals.json       -- comparable deals, by sector
"""

import json
import math
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.data.loaders import load_companies, load_deals
from src.logic.scoring import score_companies, METRICS
from src.logic.valuation import valuation_range

SECTOR_DISPLAY = {
    "Consumer Products and Retail": "Consumer Products",
    "Industrials and Auto": "Industrials & Auto",
    "Financial Services": "Financial Services",
}

REPO_ROOT = Path(__file__).resolve().parent
OUT_DIR = REPO_ROOT / "deal-scope-interface" / "data"


def sector_display_name(bucket):
    return SECTOR_DISPLAY.get(bucket, bucket)


def load_rationale_cache():
    """Returns {symbol: {"about": str|None, "why_this_score": str|None,
    "rationale": str|None}}, one entry per symbol, always all three keys
    present (None, never omitted, for a symbol not yet processed at all).

    .rationale_cache.json holds two shapes side by side, keyed differently:
      - legacy: "symbol|as_of_date" -> a plain rationale string, written by
        the original get_ai_rationale() before the about/why_this_score
        split existed.
      - current: "symbol|as_of_date|taxonomy_version" -> a
        {"rationale": str (optional, carried forward), "about": str,
        "why_this_score": str} dict, written by get_ai_analysis(). A
        reprocessed symbol keeps BOTH its old legacy-keyed string entry and
        its new taxonomy-versioned dict entry in the same cache file (the
        old key is never deleted), so a symbol can have two entries at
        once -- the versioned dict one always wins when both exist, since
        it's the fresher generation.

    Previously this returned the raw cache value untouched, keyed only by
    symbol (whichever entry's key happened to iterate last) -- for a
    reprocessed symbol that raw value was the WHOLE dict object, written
    straight into company.json's single `rationale` key. The frontend then
    tried to render that object directly as a React child, which crashed
    the tear sheet (confirmed via the actual thrown error: "Objects are not
    valid as a React child (found: object with keys {rationale, about,
    why_this_score})"). This version reads the dict's real fields out
    instead of passing the object through.
    """
    cache_path = REPO_ROOT / ".rationale_cache.json"
    if not cache_path.exists():
        return {}
    with open(cache_path) as f:
        raw = json.load(f)

    out = {}
    for key, value in raw.items():
        symbol = key.split("|", 1)[0]
        entry = out.setdefault(symbol, {"about": None, "why_this_score": None, "rationale": None})

        if isinstance(value, dict):
            # The versioned dict entry always wins, whichever order the two
            # keys happen to iterate in -- unconditional overwrite.
            entry["about"] = value.get("about")
            entry["why_this_score"] = value.get("why_this_score")
            entry["rationale"] = value.get("rationale")
        elif isinstance(value, str) and entry["about"] is None and entry["why_this_score"] is None:
            # Legacy string entry -- only apply it if a dict entry for this
            # symbol hasn't already supplied real about/why_this_score
            # content (from either iteration order).
            entry["rationale"] = value

    return out


def clean(value):
    """NaN/inf aren't valid JSON -- convert to None so JSON.parse never chokes."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if pd.isna(value):
        return None
    return value


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Optional override, same DEALSCOPE_INPUT_FILE convention enrich_dataset.py
    # already uses -- lets quarterly_refresh.yml regenerate the frontend export
    # from a NEW candidate snapshot (still awaiting human review) rather than
    # the currently-committed live file, without changing default behavior for
    # every other caller (daily_price_refresh.yml, local runs) that leaves it
    # unset and gets DEFAULT_COMPANIES_PATH as before.
    input_override = os.environ.get("DEALSCOPE_INPUT_FILE")
    companies = load_companies(input_override) if input_override else load_companies()
    equal_weights = {m: 5 for m in METRICS}
    scored = score_companies(companies, equal_weights)
    valued = valuation_range(scored)
    rationale_cache = load_rationale_cache()

    company_records = []
    for _, r in valued.iterrows():
        # Empty dict, not None, for a symbol with zero cache entries at all
        # (content generation hasn't reached it yet) -- so the three .get()
        # calls below always resolve to None cleanly instead of raising.
        content = rationale_cache.get(r["symbol"], {})
        company_records.append({
            "ticker": clean(r["symbol"]),
            "name": clean(r["name"]),
            "sector": clean(r["ey_bucket"]),
            "sector_display": sector_display_name(r["ey_bucket"]),
            # Granular Yahoo-sourced fields, previously read only to feed
            # classify_sector() and then discarded. clean() already turns
            # NaN into None for the 74/2,046 companies missing both.
            "industry": clean(r["industry"]),
            "sector_raw": clean(r["sector"]),
            "revenue": clean(r["revenue"]),
            "ebitda": clean(r["ebitda"]),
            "ebitda_margin_pct": clean(r["ebitda_margin_pct"]),
            "revenue_growth_pct": clean(r["revenue_growth_pct"]),
            "roce_pct": clean(r["return_on_capital_employed_pct"]),
            "total_debt": clean(r["total_debt"]),
            "market_cap": clean(r["market_cap"]),
            "market_cap_as_of": clean(r.get("market_cap_as_of")),
            "net_income": clean(r["net_income"]),
            # Full financial snapshot -- already computed in the enriched
            # dataset (Phase 2 data-foundation fields), just not previously
            # exported to the frontend. Added for the tear sheet's expanded
            # "Key Financials" grid.
            "trailing_pe": clean(r.get("trailing_pe")),
            "price_to_book": clean(r.get("price_to_book")),
            "return_on_equity_pct": clean(r.get("return_on_equity_pct")),
            # yfinance's debtToEquity is expressed as a percent (e.g. 36.65
            # meaning 36.65%, i.e. a 0.37x ratio) -- divide by 100 here so
            # the frontend's "x" ratio formatting (e.g. "0.37x") is
            # actually correct instead of overstating leverage ~100x.
            "debt_to_equity": clean(r.get("debt_to_equity") / 100 if pd.notna(r.get("debt_to_equity")) else None),
            "current_ratio": clean(r.get("current_ratio")),
            "free_cash_flow": clean(r.get("free_cash_flow")),
            "promoter_pledge_pct": clean(r.get("promoter_pledge_pct")),
            "beta": clean(r.get("beta")),
            "factor_revenue_growth": clean(r["pctl_revenue_growth_pct"]),
            "factor_ebitda_margin": clean(r["pctl_ebitda_margin_pct"]),
            "factor_roce": clean(r["pctl_return_on_capital_employed_pct"]),
            "factor_debt_level": clean(r["pctl_total_debt"]),
            "ev_ebitda_low": clean(r["ev_ebitda_low"]),
            "ev_ebitda_high": clean(r["ev_ebitda_high"]),
            "pe_implied_low": clean(r["pe_implied_low"]),
            "pe_implied_high": clean(r["pe_implied_high"]),
            "valuation_note": clean(r["valuation_note"]) or "",
            "as_of_date": clean(r["as_of_date"]),
            "rationale": content.get("rationale"),
            "about": content.get("about"),
            "why_this_score": content.get("why_this_score"),
        })

    companies_path = OUT_DIR / "companies.json"
    with open(companies_path, "w") as f:
        json.dump(company_records, f, ensure_ascii=False)
    print(f"Wrote {len(company_records)} companies -> {companies_path}")
    print(f"  about available for {sum(1 for c in company_records if c['about'])} / {len(company_records)}")
    print(f"  why_this_score available for {sum(1 for c in company_records if c['why_this_score'])} / {len(company_records)}")
    print(f"  legacy rationale (no why_this_score yet) available for "
          f"{sum(1 for c in company_records if c['rationale'] and not c['why_this_score'])} / {len(company_records)}")

    deals = load_deals()
    deal_records = []
    for _, d in deals.iterrows():
        deal_records.append({
            "target": clean(d["target"]),
            "acquirer": clean(d["acquirer"]),
            "sector_raw": clean(d["sector_raw"]),
            "ey_bucket": clean(d["ey_bucket"]),
            "deal_type": clean(d["deal_type"]),
            "deal_value_usdm": clean(d["deal_value_usdm_numeric"]),
            "stake_pct": clean(d["stake_pct_numeric"]),
            "report_year": clean(d["report_year"]),
        })

    deals_path = OUT_DIR / "deals.json"
    with open(deals_path, "w") as f:
        json.dump(deal_records, f, ensure_ascii=False)
    print(f"Wrote {len(deal_records)} deals -> {deals_path}")


if __name__ == "__main__":
    main()
