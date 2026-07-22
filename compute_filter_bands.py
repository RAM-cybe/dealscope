"""Recompute quartile-based band edges for the 8 numeric fields the
frontend's `BUCKET_FIELDS` array (deal-scope-interface/lib/dealscope-data.ts)
uses for filter buckets. Those edges were hardcoded once, when the universe
was 2,046 companies, and never recalculated as it grew to 2,381 -- this
script produces a fresh, versioned artifact instead of a manual re-eyeball.

For each field: pulls non-null values from the current company universe,
winsorizes at the 1st/99th percentile (CLIPS, never drops rows) to neutralize
extreme-but-real outliers from statistically tiny/distressed companies (e.g.
BOHRAIND's ebitda_margin_pct of -92,980%, SWANDEF's revenue_growth_pct of
+14,905% -- real numbers from tiny revenue denominators, not data errors),
then computes p25/p50/p75 as the three band-edge cutpoints (4 bands: bottom
25%, 25-50%, 50-75%, top 25% -- matching the frontend's existing 4-bucket UI
pattern for 7 of the 8 fields).

market_cap and total_debt are converted rupees -> Rs Cr (/1e7) before
winsorizing, matching how the frontend's `raw.marketCap`/`raw.totalDebt`
are already scaled (dealscope-data.ts, ~line 392-398) -- so these cutpoints
are display-ready, not raw-rupee numbers.

promoter_pledge_pct note: the current UI is a 3-tier categorical pattern
(none = exactly 0%, low = 0-10%, elevated = >10%), not a 4-tier percentile
split -- the "none" tier is a real zero, not a quartile boundary, and this
field's distribution is heavily zero-mass (most companies report no pledge
at all). p25/p50/p75 are still computed here as requested for completeness
and consistency with the other 7 fields, but they will very likely collapse
toward 0 and are not a drop-in replacement for the existing 3-tier boundary
without a frontend-side decision on how to handle the zero-mass. Disclosed
here, not silently glossed over.

Does NOT touch any frontend .tsx/.ts file -- BUCKET_FIELDS stays hardcoded
exactly as-is until a separate frontend session wires it to read this file.
This script's only job is producing a correct deal-scope-interface/data/filter-bands.json.

Run standalone, or via export_for_frontend.py (which calls this
automatically before writing companies.json/deals.json, so band
recomputation happens on every export, not as a separate manual step).

Writes:
    deal-scope-interface/data/filter-bands.json
"""

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from src.data.loaders import load_companies

OUT_PATH = REPO_ROOT / "deal-scope-interface" / "data" / "filter-bands.json"

WINSOR_LOW, WINSOR_HIGH = 1, 99

# (backend column, frontend BucketFieldKey, unit, Cr-scale?, decimals, existing tier names)
FIELD_SPECS = [
    ("market_cap", "marketCap", "INR_Cr", True, 0, ["small", "mid", "large", "mega"]),
    ("trailing_pe", "peRatio", "x", False, 1, ["value", "moderate", "growth", "premium"]),
    ("revenue_growth_pct", "revenueGrowth", "%", False, 1, ["declining", "flat", "growing", "highGrowth"]),
    ("ebitda_margin_pct", "ebitdaMargin", "%", False, 1, ["thin", "moderate", "healthy", "high"]),
    ("return_on_capital_employed_pct", "roce", "%", False, 1, ["weak", "average", "strong", "excellent"]),
    ("return_on_equity_pct", "roe", "%", False, 1, ["weak", "average", "strong", "excellent"]),
    ("total_debt", "debtLevel", "INR_Cr", True, 0, ["low", "moderate", "elevated", "high"]),
    ("promoter_pledge_pct", "promoterPledge", "%", False, 1, ["none", "low", "elevated"]),
]

# The frontend's CURRENT hardcoded edges (Rs Cr for market_cap/debt, plain
# numbers otherwise), read directly out of dealscope-data.ts, for the
# before/after drift comparison this script prints.
CURRENT_HARDCODED = {
    "market_cap": [700, 2900, 13000],
    "trailing_pe": [16, 29, 51],
    "revenue_growth_pct": [0, 12, 28],
    "ebitda_margin_pct": [6, 12, 20],
    "return_on_capital_employed_pct": [6, 13, 19],
    "return_on_equity_pct": [5, 11, 17],
    "total_debt": [40, 210, 935],
    "promoter_pledge_pct": [0, 10, None],  # 3-tier: none=0, low<=10, elevated>10
}


def compute_band(series, decimals):
    values = series.dropna().to_numpy(dtype=float)
    n = len(values)
    if n == 0:
        return None
    lo, hi = np.percentile(values, [WINSOR_LOW, WINSOR_HIGH])
    clipped = np.clip(values, lo, hi)
    p25, p50, p75 = np.percentile(clipped, [25, 50, 75])
    return {
        "p25": round(float(p25), decimals) if decimals else round(float(p25)),
        "p50": round(float(p50), decimals) if decimals else round(float(p50)),
        "p75": round(float(p75), decimals) if decimals else round(float(p75)),
        "sample_size": n,
    }


def main():
    companies = load_companies()

    fields_out = {}
    comparison_rows = []

    for col, frontend_key, unit, is_cr, decimals, tiers in FIELD_SPECS:
        series = companies[col]
        if is_cr:
            series = series / 1e7

        band = compute_band(series, decimals)
        if band is None:
            print(f"WARNING: {col} has zero non-null values -- skipping")
            continue

        entry = {
            "frontend_key": frontend_key,
            "unit": unit,
            "tiers": tiers,
            "p25": band["p25"],
            "p50": band["p50"],
            "p75": band["p75"],
            "sample_size": band["sample_size"],
        }
        if col == "promoter_pledge_pct":
            entry["note"] = (
                "Current UI is 3-tier categorical (none=0%, low=0-10%, elevated>10%), "
                "not a 4-tier percentile split; distribution is zero-heavy. p25/p50/p75 "
                "computed for completeness -- see module docstring before wiring into the UI."
            )
        fields_out[col] = entry

        old = CURRENT_HARDCODED.get(col, [None, None, None])
        comparison_rows.append((col, old, [band["p25"], band["p50"], band["p75"]]))

    out = {
        "generated_at": date.today().isoformat(),
        "universe_size": len(companies),
        "winsorize_percentiles": [WINSOR_LOW, WINSOR_HIGH],
        "fields": fields_out,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"Wrote {len(fields_out)} fields -> {OUT_PATH}")
    print(f"\n=== Before (hardcoded) vs after (winsorized p25/p50/p75), universe n={len(companies)} ===")
    header = f"{'field':35s} {'old edges':30s} {'new edges':30s}"
    print(header)
    print("-" * len(header))
    for col, old, new in comparison_rows:
        old_s = ", ".join("N/A" if v is None else str(v) for v in old)
        new_s = ", ".join(str(v) for v in new)
        print(f"{col:35s} {old_s:30s} {new_s:30s}")

    # Sanity: no NaN/None leaked into any written cutpoint.
    bad = [
        col for col, entry in fields_out.items()
        if any(entry[k] is None or (isinstance(entry[k], float) and np.isnan(entry[k])) for k in ("p25", "p50", "p75"))
    ]
    if bad:
        print(f"\nFAIL: NaN/null cutpoints in: {bad}")
        sys.exit(1)
    print(f"\nOK: all {len(fields_out)} fields have 3 non-null cutpoints each.")


if __name__ == "__main__":
    main()
