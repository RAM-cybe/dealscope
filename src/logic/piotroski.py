"""Piotroski F-Score (Part 1c of the financial-health-scores round).

FEASIBILITY FINDING (Part 1c's first requirement, checked before writing any
scoring code): yfinance's balance_sheet / financials / cashflow calls each
return up to 5 ANNUAL periods in a single pull for a given ticker -- this was
confirmed empirically (not assumed) against a sample of companies including
both currency-flagged symbols (INFY, HCLTECH) before the full-universe pull
ran. This means the prior-period deltas the F-Score needs (ROA change,
leverage change, current-ratio change, margin change, asset-turnover change)
are available from ONE pull per company, not dependent on this project's own
quarterly snapshots accumulating over multiple refresh cycles. Per the task's
explicit instruction, the full F-Score is therefore built and shown live now,
not hidden behind a "pending" state.

The 9 raw two-period input fields (fy0=latest annual period, fy1=prior) were
pulled once for the whole universe by archive/data_pipeline_scripts/
pull_financial_health.py and merged into the live dataset by
merge_financial_health.py -- see src/data/schema.py for the full field list.

The 9 classic Piotroski (2000) signals, each worth 1 point:
  Profitability
    1. ROA > 0 (current year)
    2. Operating cash flow > 0 (current year)
    3. ROA increased year-over-year
    4. Accruals: operating cash flow > net income (earnings quality)
  Leverage / liquidity
    5. Long-term debt / total assets decreased year-over-year
    6. Current ratio increased year-over-year
    7. No new shares issued (shares outstanding did not increase)
  Operating efficiency
    8. Gross margin increased year-over-year
    9. Asset turnover (revenue / total assets) increased year-over-year

DESIGN CHOICE (disclosed): f_score is only computed when ALL 9 signals are
computable for a company -- a "6 of 9" partial score is not what Piotroski
(2000) defined, and rescaling it (the way this project's own from-scratch
composite `score` column reweights around missing metrics) would misrepresent
a textbook methodology as something it isn't. A company missing any one of
the 9 underlying signals gets f_score = NaN, same "never fabricate, a genuine
gap is blank" rule as everywhere else in this project. The real resulting
population rate is reported by this file's __main__ block, not assumed.
"""

import pandas as pd

F0 = "fy0"
F1 = "fy1"


def _safe_div(numerator, denominator):
    result = numerator / denominator
    return result.replace([float("inf"), float("-inf")], float("nan"))


def compute_piotroski(df):
    """Return a copy of df with f_score (0-9 int, or NaN) and
    f_score_signals_computable (0-9, how many of the 9 signals had all the
    raw inputs needed to evaluate -- always 9 when f_score is populated,
    useful for diagnosing why a given company is NaN)."""
    df = df.copy()

    roa0 = _safe_div(df["net_income_fy0"], df["total_assets_fy0"])
    roa1 = _safe_div(df["net_income_fy1"], df["total_assets_fy1"])
    lev0 = _safe_div(df["long_term_debt_fy0"], df["total_assets_fy0"])
    lev1 = _safe_div(df["long_term_debt_fy1"], df["total_assets_fy1"])
    cr0 = _safe_div(df["current_assets_fy0"], df["current_liabilities_fy0"])
    cr1 = _safe_div(df["current_assets_fy1"], df["current_liabilities_fy1"])
    gm0 = _safe_div(df["total_revenue_fy0"] - df["cost_of_revenue_fy0"], df["total_revenue_fy0"])
    gm1 = _safe_div(df["total_revenue_fy1"] - df["cost_of_revenue_fy1"], df["total_revenue_fy1"])
    at0 = _safe_div(df["total_revenue_fy0"], df["total_assets_fy0"])
    at1 = _safe_div(df["total_revenue_fy1"], df["total_assets_fy1"])

    signals = {}
    computable = {}

    signals["s1_roa_positive"] = (df["net_income_fy0"] > 0).astype("float")
    computable["s1_roa_positive"] = df["net_income_fy0"].notna()

    signals["s2_cfo_positive"] = (df["operating_cash_flow_fy0"] > 0).astype("float")
    computable["s2_cfo_positive"] = df["operating_cash_flow_fy0"].notna()

    signals["s3_roa_increased"] = (roa0 > roa1).astype("float")
    computable["s3_roa_increased"] = roa0.notna() & roa1.notna()

    signals["s4_accruals_quality"] = (df["operating_cash_flow_fy0"] > df["net_income_fy0"]).astype("float")
    computable["s4_accruals_quality"] = df["operating_cash_flow_fy0"].notna() & df["net_income_fy0"].notna()

    signals["s5_leverage_decreased"] = (lev0 < lev1).astype("float")
    computable["s5_leverage_decreased"] = lev0.notna() & lev1.notna()

    signals["s6_current_ratio_increased"] = (cr0 > cr1).astype("float")
    computable["s6_current_ratio_increased"] = cr0.notna() & cr1.notna()

    signals["s7_no_new_shares"] = (df["shares_outstanding_fy0"] <= df["shares_outstanding_fy1"]).astype("float")
    computable["s7_no_new_shares"] = df["shares_outstanding_fy0"].notna() & df["shares_outstanding_fy1"].notna()

    signals["s8_gross_margin_increased"] = (gm0 > gm1).astype("float")
    computable["s8_gross_margin_increased"] = gm0.notna() & gm1.notna()

    signals["s9_asset_turnover_increased"] = (at0 > at1).astype("float")
    computable["s9_asset_turnover_increased"] = at0.notna() & at1.notna()

    computable_df = pd.DataFrame(computable)
    signals_df = pd.DataFrame(signals)

    n_computable = computable_df.sum(axis=1)
    all_computable = n_computable == 9

    raw_score = pd.Series(0.0, index=df.index)
    for key in signals_df.columns:
        raw_score += signals_df[key].where(computable_df[key], 0.0)

    df["f_score"] = raw_score.where(all_computable, float("nan"))
    df["f_score_signals_computable"] = n_computable
    return df


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.data.loaders import load_companies

    companies = load_companies()
    scored = compute_piotroski(companies)

    n = len(scored)
    populated = scored["f_score"].notna().sum()
    print("=== Piotroski F-Score population ===")
    print(f"Full universe: {n} companies")
    print(f"f_score populated (all 9 signals computable): {populated} / {n} = {100*populated/n:.1f}%")
    print()
    print("Distribution of how many of the 9 signals WERE computable (all companies):")
    print(scored["f_score_signals_computable"].value_counts().sort_index(ascending=False).to_string())
    print()
    print("f_score distribution (of populated):")
    print(scored.loc[scored["f_score"].notna(), "f_score"].astype(int).value_counts().sort_index().to_string())

    print()
    print("=== Manual spot-check: 6 companies, hand-recomputed signal-by-signal ===")
    sample = scored.dropna(subset=["f_score"]).sample(n=min(6, populated), random_state=7)
    for _, row in sample.iterrows():
        roa0 = row["net_income_fy0"] / row["total_assets_fy0"]
        roa1 = row["net_income_fy1"] / row["total_assets_fy1"]
        lev0 = row["long_term_debt_fy0"] / row["total_assets_fy0"]
        lev1 = row["long_term_debt_fy1"] / row["total_assets_fy1"]
        cr0 = row["current_assets_fy0"] / row["current_liabilities_fy0"]
        cr1 = row["current_assets_fy1"] / row["current_liabilities_fy1"]
        gm0 = (row["total_revenue_fy0"] - row["cost_of_revenue_fy0"]) / row["total_revenue_fy0"]
        gm1 = (row["total_revenue_fy1"] - row["cost_of_revenue_fy1"]) / row["total_revenue_fy1"]
        at0 = row["total_revenue_fy0"] / row["total_assets_fy0"]
        at1 = row["total_revenue_fy1"] / row["total_assets_fy1"]
        manual_signals = [
            row["net_income_fy0"] > 0,
            row["operating_cash_flow_fy0"] > 0,
            roa0 > roa1,
            row["operating_cash_flow_fy0"] > row["net_income_fy0"],
            lev0 < lev1,
            cr0 > cr1,
            row["shares_outstanding_fy0"] <= row["shares_outstanding_fy1"],
            gm0 > gm1,
            at0 > at1,
        ]
        manual_score = sum(manual_signals)
        match = "OK" if manual_score == int(row["f_score"]) else "MISMATCH"
        print(f"{row['symbol']:15s} hand={manual_score}/9  engine={int(row['f_score'])}/9  "
              f"signals={['Y' if s else 'N' for s in manual_signals]}  [{match}]")
