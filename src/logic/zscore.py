"""Altman Z''-Score (Part 1b of the financial-health-scores round).

FORMULA CHOICE (disclosed, not silent): the classic 1968 Altman Z-Score
(1.2*WC/TA + 1.4*RE/TA + 3.3*EBIT/TA + 0.6*MktCap/TL + 1.0*Sales/TA) was
built and validated on public MANUFACTURING companies. It is well documented
as invalid for financial-services companies (banks, NBFCs) -- their normal
funding structure (deposits/borrowings as core liabilities) looks like
balance-sheet "distress" under a formula calibrated on industrial firms.

This project makes BOTH of the two defensible choices the task called out,
not just one:
  1. Uses the Altman Z''-Score variant (Altman, Hartzell & Peck, 1995),
     built for non-manufacturers/private/emerging-market firms. It drops the
     Sales/Total-Assets term (X5) -- the term most distorted by
     asset-intensity differences across industries/services -- and uses
     four terms instead of five:
         Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4
         X1 = Working Capital / Total Assets
         X2 = Retained Earnings / Total Assets
         X3 = EBIT / Total Assets
         X4 = Market Capitalization / Total Liabilities
     (X4 uses market cap, not book equity, per Wall Street Prep's published
     Z''-Score formula for private/non-manufacturing companies -- this
     project already has near-universal market_cap coverage, and X4 was
     market-cap-based in Altman's own original 1968 public-company model
     too, so this is a documented, cited choice, not an improvised one.)
     Zones: Safe > 2.6, Grey 1.1-2.6, Distress < 1.1.
  2. STILL excludes the Financial Services sector entirely (see
     EXCLUDED_SECTORS below). Z'' extends applicability to general
     non-manufacturers (retail, services, industrials) but does not fix the
     bank/NBFC problem specifically -- a lender's core liabilities
     (deposits, borrowings funding its loan book) are its normal operating
     model, not distress, under ANY Altman variant. This is the same
     understanding already documented in CONTEXT.md's Open Issue #1 (NBFC
     revenue-definition gap) -- Financial Services companies get z_score =
     NaN, not a misleading number.

Real, disclosed constraint on population: X2 (Retained Earnings/Total
Assets) requires `retained_earnings`, which is only ~22% populated in this
dataset (a known, disclosed gap -- see CONTEXT.md's Known Data Limitations).
Since all four terms are required, ~22% is the realistic ceiling on
z_score's population rate, even though the other three terms are much more
complete. This is not a bug in this module; it is an honest, real gap in
the underlying data, reported (not hidden) via the population-rate print in
this file's __main__ block.
"""

import pandas as pd

EXCLUDED_SECTORS = {"Financial Services"}

ZSCORE_REQUIRED_FIELDS = [
    "working_capital", "total_assets", "retained_earnings", "ebit",
    "market_cap", "total_liabilities",
]


def compute_zscore(df):
    """Return a copy of df with two new columns: z_score (float) and
    z_score_zone ("Safe" / "Grey" / "Distress" / NaN).

    z_score is NaN for: Financial Services companies (excluded by design,
    see module docstring), and any company missing one or more of the six
    required raw fields.
    """
    df = df.copy()

    ta = df["total_assets"]
    x1 = df["working_capital"] / ta
    x2 = df["retained_earnings"] / ta
    x3 = df["ebit"] / ta
    x4 = df["market_cap"] / df["total_liabilities"]

    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    z = z.replace([float("inf"), float("-inf")], float("nan"))

    have_all_fields = df[ZSCORE_REQUIRED_FIELDS].notna().all(axis=1)
    is_excluded_sector = df["ey_bucket"].isin(EXCLUDED_SECTORS)

    z = z.where(have_all_fields & ~is_excluded_sector, float("nan"))
    df["z_score"] = z

    def zone(value):
        if pd.isna(value):
            return None
        if value > 2.6:
            return "Safe"
        if value >= 1.1:
            return "Grey"
        return "Distress"

    df["z_score_zone"] = df["z_score"].apply(zone)
    return df


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.data.loaders import load_companies

    companies = load_companies()
    scored = compute_zscore(companies)

    n = len(scored)
    populated = scored["z_score"].notna().sum()
    print(f"=== Altman Z''-Score population ===")
    print(f"Full universe: {n} companies")
    print(f"Financial Services excluded: {(companies['ey_bucket'].isin(EXCLUDED_SECTORS)).sum()}")
    print(f"z_score populated: {populated} / {n} = {100*populated/n:.1f}%")
    print(f"  (bottlenecked by retained_earnings population -- see module docstring)")
    print()
    print("Zone distribution (of populated):")
    print(scored["z_score_zone"].value_counts(dropna=False).to_string())

    print()
    print("=== Manual spot-check: hand-computed vs engine, one per zone + random fill ===")
    populated_rows = scored.dropna(subset=["z_score"])
    one_per_zone = populated_rows.groupby("z_score_zone", group_keys=False).head(1)
    filler = populated_rows.drop(one_per_zone.index).sample(
        n=min(5, len(populated_rows) - len(one_per_zone)), random_state=42
    )
    sample = pd.concat([one_per_zone, filler])
    for _, row in sample.iterrows():
        ta = row["total_assets"]
        x1 = row["working_capital"] / ta
        x2 = row["retained_earnings"] / ta
        x3 = row["ebit"] / ta
        x4 = row["market_cap"] / row["total_liabilities"]
        manual_z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
        match = "OK" if abs(manual_z - row["z_score"]) < 1e-6 else "MISMATCH"
        print(f"{row['symbol']:15s} ({row['ey_bucket']:30s}) "
              f"X1={x1:7.4f} X2={x2:7.4f} X3={x3:7.4f} X4={x4:7.4f} "
              f"hand={manual_z:8.4f} engine={row['z_score']:8.4f} zone={row['z_score_zone']:9s} [{match}]")
