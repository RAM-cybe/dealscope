"""Filtering logic for the ranked company table (PRD section 3, feature 1).

COMPOSITION-ORDER CONTRACT (do not violate this in Module 4 or anywhere else):
filter_companies() is a pure display-layer operation. It must be called
AFTER score_companies(), never before, and its output must never be fed back
into score_companies(). See scoring.py's module docstring for why: scoring
a narrowed, filter-dependent subset would make a company's sector-relative
percentile -- and therefore its score -- drift every time the user changes a
filter, even though nothing about the company itself changed.

NaN handling: NaN always PASSES a filter on the field it's missing (approved
default). A company is only excluded by a filter when it has a present,
out-of-range value for that field -- never for lacking data. This matches
the project's rule everywhere else: never hide a company for missing data.
"""

import pandas as pd

RANGE_FIELDS = [
    "revenue",
    "ebitda_margin_pct",
    "return_on_capital_employed_pct",
    "total_debt",
    "market_cap",
    # Phase 2 fields (data/enriched/dealscope_base_2026-07-12.csv) -- filters
    # only, per the locked decision not to fold these into the scored 4.
    "total_assets",
    "retained_earnings",
    "working_capital",
    "enterprise_value",
    "total_cash",
    "operating_cash_flow",
    "free_cash_flow",
    "current_ratio",
    "quick_ratio",
    "debt_to_equity",
    "return_on_assets",
    "beta",
    "peg_ratio",
    "price_to_book",
    "trailing_pe",
    # Part 1 fields (2026-07-17 financial-health-scores round).
    "ebit",
    "total_liabilities",
    "z_score",
    "f_score",
]


def filter_companies(df, filters):
    """Apply the 7 PRD filters to a company DataFrame.

    Call this on the output of score_companies(), never on unscored data
    that will later be scored -- see the module docstring's composition-
    order contract.

    filters is a dict; every key is optional (omit or set to None to skip
    that filter):
      - "sectors": list[str], matched against the ey_bucket column
      - "revenue", "ebitda_margin_pct", "return_on_capital_employed_pct",
        "total_debt", "market_cap": (min, max) tuples
      - "promoter_pledge_pct_max": ceiling value; keeps rows with
        promoter_pledge_pct <= ceiling

    A company with NaN in a filtered field always passes that filter (see
    module docstring). Returns the filtered DataFrame with a fresh index.
    """
    filters = filters or {}
    mask = pd.Series(True, index=df.index)

    sectors = filters.get("sectors")
    if sectors:
        mask &= df["ey_bucket"].isin(sectors)

    for field in RANGE_FIELDS:
        bounds = filters.get(field)
        if bounds is None:
            continue
        lo, hi = bounds
        col = df[field]
        mask &= col.between(lo, hi) | col.isna()

    pledge_max = filters.get("promoter_pledge_pct_max")
    if pledge_max is not None:
        col = df["promoter_pledge_pct"]
        mask &= (col <= pledge_max) | col.isna()

    return df[mask].reset_index(drop=True)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.data.loaders import load_companies
    from src.logic.scoring import score_companies

    companies = load_companies()
    scored = score_companies(companies, {m: 5 for m in
                                          ["revenue_growth_pct", "ebitda_margin_pct",
                                           "return_on_capital_employed_pct", "total_debt"]})

    print("=== filter_companies manual-verification ===")
    print(f"full universe: {len(scored)} rows")

    pledge_ceiling = 10.0
    filtered = filter_companies(scored, {"promoter_pledge_pct_max": pledge_ceiling})
    manual_kept = scored[(scored["promoter_pledge_pct"] <= pledge_ceiling) | scored["promoter_pledge_pct"].isna()]
    print(
        f"promoter_pledge_pct_max={pledge_ceiling}: engine kept {len(filtered)} rows, "
        f"manual check kept {len(manual_kept)} rows "
        f"({'OK' if len(filtered) == len(manual_kept) else 'MISMATCH'})"
    )
    nan_pledge_count = scored["promoter_pledge_pct"].isna().sum()
    nan_pledge_kept = filtered["promoter_pledge_pct"].isna().sum()
    print(
        f"  companies with NaN promoter_pledge_pct in full universe: {nan_pledge_count}, "
        f"still present after filter: {nan_pledge_kept} (should be equal -- NaN must pass)"
    )

    sector_filtered = filter_companies(scored, {"sectors": ["Lifesciences"]})
    manual_sector = scored[scored["ey_bucket"] == "Lifesciences"]
    print(
        f"\nsectors=['Lifesciences']: engine kept {len(sector_filtered)} rows, "
        f"manual check kept {len(manual_sector)} rows "
        f"({'OK' if len(sector_filtered) == len(manual_sector) else 'MISMATCH'})"
    )

    revenue_bounds = (1e9, 1e10)
    revenue_filtered = filter_companies(scored, {"revenue": revenue_bounds})
    manual_revenue = scored[
        scored["revenue"].between(*revenue_bounds) | scored["revenue"].isna()
    ]
    print(
        f"\nrevenue={revenue_bounds}: engine kept {len(revenue_filtered)} rows, "
        f"manual check kept {len(manual_revenue)} rows "
        f"({'OK' if len(revenue_filtered) == len(manual_revenue) else 'MISMATCH'})"
    )
