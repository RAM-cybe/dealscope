"""Per-sector percentile bands, so "high ROCE" and "low debt" mean something
different in Financial Services than in Industrials.

compute_filter_bands.py already produces UNIVERSE-wide p25/p50/p75 for the
frontend's fixed filter buckets. That's right for a bucket UI, where every
user sees the same labelled band edges. It is wrong for the natural-language
screener: "high margin pharma" and "high margin industrials" should not both
resolve to the same absolute EBITDA-margin cutoff, because the two sectors'
margin distributions genuinely differ. A 12% margin is unremarkable in
Lifesciences and strong in Industrials & Auto.

This produces the same three cutpoints PER SECTOR (the 13-sector v2 taxonomy
the frontend groups by, via `sector_v2`/`sector_display`), for the fields a
qualitative word can attach to:

    roce, ebitda_margin, revenue_growth, total_debt, trailing_pe

The frontend's query parser reads these to turn "strong ROCE" into a real
number: when the query also names a sector, it uses that sector's p75; with
no sector named it falls back to the `__all__` universe-wide row, which is
computed here too so the consumer never needs a second file.

Methodology is deliberately identical to compute_filter_bands.py -- winsorize
at the 1st/99th percentile (clip, never drop) before taking quartiles, so a
handful of penny-stock-scale outliers can't drag a sector's edges. Sectors
with fewer than MIN_SECTOR_N populated values for a field fall back to the
universe-wide numbers for that field rather than publishing a cutpoint
derived from a handful of companies; `sample_size` is emitted either way so
the consumer can see what it's standing on.

Currency fields are converted rupees -> Rs Cr (/1e7) to match how the
frontend's `raw.*` values are already scaled.

Run standalone, or via export_for_frontend.py (which calls this alongside
compute_filter_bands.py so both artifacts regenerate on every export).

Writes:
    deal-scope-interface/data/sector-bands.json
"""

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from src.data.loaders import load_companies

OUT_PATH = REPO_ROOT / "deal-scope-interface" / "data" / "sector-bands.json"

WINSOR_LOW, WINSOR_HIGH = 1, 99

# Below this many populated values, a sector's own quartiles are too thin to
# trust -- fall back to the universe-wide row for that field instead.
MIN_SECTOR_N = 30

ALL_KEY = "__all__"

# (backend column, frontend key, Cr-scale?, decimals)
FIELD_SPECS = [
    ("return_on_capital_employed_pct", "roce", False, 1),
    # ROE is not optional here: the parser resolves a qualitative word by
    # looking its field up in this file, and a missing field makes it skip the
    # constraint SILENTLY. Omitting roe meant "high roce high roe" quietly
    # applied only the ROCE half -- the query looked like it worked, returned a
    # plausible number of companies, and was simply wrong. Every field the
    # frontend's NumericFieldKey can name must have a row here.
    ("return_on_equity_pct", "roe", False, 1),
    ("ebitda_margin_pct", "ebitdaMargin", False, 1),
    ("revenue_growth_pct", "revenueGrowth", False, 1),
    ("total_debt", "totalDebt", True, 0),
    ("trailing_pe", "peRatio", False, 1),
    ("revenue", "revenue", True, 0),
    ("market_cap", "marketCap", True, 0),
]

def sector_display_name(bucket):
    """Keys in this file must match `company.sector` on the frontend exactly.
    sector_v2 labels are already display-ready."""
    return bucket if isinstance(bucket, str) else "Unclassified"


def quartiles(series, decimals):
    """Winsorized p25/p50/p75, or None when there's nothing populated."""
    values = series.dropna().to_numpy(dtype=float)
    n = len(values)
    if n == 0:
        return None
    lo, hi = np.percentile(values, [WINSOR_LOW, WINSOR_HIGH])
    clipped = np.clip(values, lo, hi)
    p25, p50, p75 = np.percentile(clipped, [25, 50, 75])
    r = (lambda v: round(float(v), decimals)) if decimals else (lambda v: round(float(v)))
    return {"p25": r(p25), "p50": r(p50), "p75": r(p75), "sample_size": n}


def main():
    companies = load_companies()
    companies = companies.copy()
    companies["sector_display"] = [sector_display_name(b) for b in companies["sector_v2"]]

    out_sectors = {}

    # Universe-wide row first -- every sector falls back to it on a thin field.
    universe = {}
    for col, key, is_cr, decimals in FIELD_SPECS:
        series = companies[col] / 1e7 if is_cr else companies[col]
        band = quartiles(series, decimals)
        if band:
            universe[key] = band
    out_sectors[ALL_KEY] = universe

    for sector_name, group in companies.groupby("sector_display"):
        fields = {}
        for col, key, is_cr, decimals in FIELD_SPECS:
            series = group[col] / 1e7 if is_cr else group[col]
            band = quartiles(series, decimals)
            if band is None or band["sample_size"] < MIN_SECTOR_N:
                fallback = universe.get(key)
                if fallback is None:
                    continue
                fields[key] = {
                    **fallback,
                    "sample_size": 0 if band is None else band["sample_size"],
                    "fallback": True,
                }
            else:
                fields[key] = band
        out_sectors[sector_name] = fields

    out = {
        "generated_at": date.today().isoformat(),
        "universe_size": len(companies),
        "winsorize_percentiles": [WINSOR_LOW, WINSOR_HIGH],
        "min_sector_n": MIN_SECTOR_N,
        "sectors": out_sectors,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"Wrote {len(out_sectors)} sector rows ({len(FIELD_SPECS)} fields each) -> {OUT_PATH}")
    print(f"\n=== Sector-relative p75 (the number 'high/strong X' resolves to) ===")
    header = f"{'sector':28s} {'roce':>8s} {'margin':>8s} {'growth':>8s} {'debt Cr':>10s} {'p/e':>8s}"
    print(header)
    print("-" * len(header))
    for name in [ALL_KEY] + sorted(n for n in out_sectors if n != ALL_KEY):
        f = out_sectors[name]

        def p75(k):
            return f"{f[k]['p75']}" + ("*" if f.get(k, {}).get("fallback") else "") if k in f else "-"

        print(f"{name:28s} {p75('roce'):>8s} {p75('ebitdaMargin'):>8s} "
              f"{p75('revenueGrowth'):>8s} {p75('totalDebt'):>10s} {p75('peRatio'):>8s}")
    print("(* = too few companies in that sector for this field; universe-wide value used)")

    bad = []
    for name, fields in out_sectors.items():
        for k, v in fields.items():
            if any(v.get(p) is None or (isinstance(v.get(p), float) and np.isnan(v[p])) for p in ("p25", "p50", "p75")):
                bad.append(f"{name}.{k}")
    if bad:
        print(f"\nFAIL: null/NaN cutpoints in: {bad}")
        sys.exit(1)
    print(f"\nOK: every published cutpoint is a real number.")


if __name__ == "__main__":
    main()
