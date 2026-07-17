#!/usr/bin/env python3
"""Merge the Part 1 financial-health pull (_financial_health_cache.csv) into
the live dataset, producing a new dated snapshot -- never overwrites the
prior one, same convention as every other dataset change in this project.

Adds 20 new raw fields:
  - ebit, total_liabilities (real new fields, Part 1a)
  - 18 Piotroski F-Score input fields, two annual periods each (t0=latest,
    t1=prior): net_income, operating_cash_flow, total_assets, lt_debt,
    current_assets, current_liabilities, revenue, cogs, shares_outstanding
    (Part 1c's raw inputs -- the actual F-score is computed live from these
    by src/logic/piotroski.py, same "raw fields in the CSV, score computed
    at runtime" pattern as src/logic/scoring.py already uses)

Currency guard: the pull script only blanked ebit/total_liabilities for
non-INR-flagged symbols (INFY, HCLTECH) -- it did NOT blank the 16 other new
absolute-currency fields (net_income/cfo/assets/debt/current-assets/
liabilities/revenue/cogs, both periods). This script closes that gap here,
applying the same guard project-wide: every absolute-currency field blanked
for any symbol with currency_flag != OK, at both t0 and t1. Shares
outstanding is a share count, not a currency figure, and is deliberately
NOT blanked.
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[2]
COMPANIES_IN = BASE / "data" / "enriched" / "dealscope_base_2026-07-12.csv"
CACHE_IN = BASE / "archive" / "data_pipeline_scripts" / "_financial_health_cache.csv"
STAMP = "2026-07-17"
OUT_CSV = BASE / "data" / "enriched" / f"dealscope_base_{STAMP}.csv"
OUT_PARQUET = BASE / "data" / "enriched" / f"dealscope_base_{STAMP}.parquet"

# cache column -> final schema column name
RENAME = {
    "ebit": "ebit",
    "total_liabilities": "total_liabilities",
    "ni_0": "net_income_fy0", "ni_1": "net_income_fy1",
    "cfo_0": "operating_cash_flow_fy0", "cfo_1": "operating_cash_flow_fy1",
    "ta_0": "total_assets_fy0", "ta_1": "total_assets_fy1",
    "ltd_0": "long_term_debt_fy0", "ltd_1": "long_term_debt_fy1",
    "ca_0": "current_assets_fy0", "ca_1": "current_assets_fy1",
    "cl_0": "current_liabilities_fy0", "cl_1": "current_liabilities_fy1",
    "rev_0": "total_revenue_fy0", "rev_1": "total_revenue_fy1",
    "cogs_0": "cost_of_revenue_fy0", "cogs_1": "cost_of_revenue_fy1",
    "shares_0": "shares_outstanding_fy0", "shares_1": "shares_outstanding_fy1",
}
# Every renamed field except the two share-count fields is a currency figure.
CURRENCY_SENSITIVE_NEW_FIELDS = [v for k, v in RENAME.items() if "shares_outstanding" not in v]


def main():
    companies = pd.read_csv(COMPANIES_IN)
    cache = pd.read_csv(CACHE_IN)

    cache = cache.rename(columns=RENAME)
    new_cols = ["symbol"] + list(RENAME.values())
    merged = companies.merge(cache[new_cols], on="symbol", how="left", validate="one_to_one")

    non_ok = merged["currency_flag"] != "OK"
    blanked_cells = 0
    for field in CURRENCY_SENSITIVE_NEW_FIELDS:
        affected = non_ok & merged[field].notna()
        blanked_cells += affected.sum()
        merged.loc[non_ok, field] = pd.NA

    merged["data_pull_date"] = merged["data_pull_date"]  # unchanged, kept explicit
    merged.to_csv(OUT_CSV, index=False)
    merged.to_parquet(OUT_PARQUET, index=False)

    print(f"Wrote {OUT_CSV} and {OUT_PARQUET}: {len(merged)} rows, {len(merged.columns)} columns")
    print(f"Currency guard: blanked {blanked_cells} cells across "
          f"{non_ok.sum()} non-OK symbols x {len(CURRENCY_SENSITIVE_NEW_FIELDS)} fields")
    print()
    print("Population rates for the new fields (post currency-guard):")
    for field in ["ebit", "total_liabilities"] + list(RENAME.values())[2:]:
        pct = 100 * merged[field].notna().mean()
        print(f"  {field:28s} {merged[field].notna().sum():5d} / {len(merged)} = {pct:.1f}%")


if __name__ == "__main__":
    main()
