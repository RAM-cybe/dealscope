"""Load and validate the two bundled CSVs into clean, schema-conformant DataFrames."""

from pathlib import Path

import pandas as pd

from .schema import (
    ALL_BUCKETS,
    COMPANY_NUMERIC_COLUMNS,
    REQUIRED_COMPANY_COLUMNS,
    REQUIRED_DEAL_COLUMNS,
    UNCLASSIFIED_BUCKET,
    validate_required_columns,
)
from .sector_mapping import classify_sector
from .sector_taxonomy_v2 import classify_sector_v2

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Phase 2 data-foundation file: same 2,046 companies/symbols as the original
# companies_full_v2.csv (kept in place, unused by the app now) plus 18 new
# fields. Its currency-guard gap (Infosys and HCL Tech's balance-sheet/
# cash-flow fields silently USD-denominated) was fixed before this switch --
# see git history for the exact blanked fields.
# 2026-07-17: superseded by dealscope_base_2026-07-17.csv, same 2,046 rows
# plus 20 more fields (ebit, total_liabilities, and 18 two-period Piotroski
# F-Score inputs) -- see archive/data_pipeline_scripts/merge_financial_health.py.
# 2026-07-20: superseded by dealscope_base_2026-07-20.csv, same 2,046 rows and
# columns -- a targeted core-field backfill (Tier-1 completeness 73.7% ->
# 75.1%, 1,508 -> 1,536 companies with all 8 tear-sheet fields present) via
# archive/data_pipeline_scripts/backfill_core_fields_2026-07.py. Column-safe:
# only the specific missing cells for the specific companies that got a real
# value changed; everything else is byte-identical to the 07-17 file. See
# data/quality_reports/targeted_backfill_2026-07-20.md for the full report,
# per-field results, and the confirmed data-availability ceiling on the
# remaining gap (ROCE/trailing_pe/promoter_pledge/market_cap/total_debt).
# 2026-07-21: superseded by dealscope_base_2026-07-21.csv, 2,046 -> 2,381 rows
# (+335), same 56 columns -- the original universe build accidentally kept
# only NSE SERIES == "EQ" securities, silently dropping every BE/BZ security
# (discovered via MTAR Technologies (MTARTECH) being absent despite being a
# real, actively-traded company). See
# data/quality_reports/universe_gap_be_bz_2026-07-21.csv for the full target
# list and enrich_universe_gap.py for the pull (2 companies -- IL&FSENGG,
# IL&FSTRANS -- excluded: tied to the 2018 IL&FS group insolvency, not
# meaningfully operating). Byte-identical to the 07-20 file for all
# pre-existing rows; only appended rows are new.
DEFAULT_COMPANIES_PATH = _PROJECT_ROOT / "data" / "enriched" / "dealscope_base_2026-07-21.csv"
DEFAULT_DEALS_PATH = _PROJECT_ROOT / "deals_full_v2.csv"


def load_companies(path=DEFAULT_COMPANIES_PATH):
    """Load the company dataset into a validated, typed DataFrame with an ey_bucket column."""
    df = pd.read_csv(path)
    validate_required_columns(df, REQUIRED_COMPANY_COLUMNS, Path(path).name)

    for col in COMPANY_NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # +/-inf (seen in trailing_pe, from a near-zero-earnings division) isn't a
    # real, displayable, or filterable value -- treat it the same as any other
    # genuine gap (NaN), never show "inf" in the UI.
    df[COMPANY_NUMERIC_COLUMNS] = df[COMPANY_NUMERIC_COLUMNS].replace([float("inf"), float("-inf")], float("nan"))

    # A blank company name would otherwise render an unreadable row; the ticker
    # symbol is always present and keeps the row visible per BLUEPRINT's
    # "never a blank screen" principle.
    df["name"] = df["name"].fillna(df["symbol"])

    # status is a yfinance fetch-status flag, not part of the PRD schema. Every
    # row is currently "ok"; filtering defensively means a future non-"ok" row
    # (e.g. delisted) can't silently corrupt the universe.
    df = df[df["status"] == "ok"].copy()

    df["ey_bucket"] = [
        classify_sector(sector, industry)
        for sector, industry in zip(df["sector"], df["industry"])
    ]

    # 13-sector v2 taxonomy (sector_taxonomy_v2.py) -- app.py's live peer
    # grouping since the 2026-07-18 redesign. classify_sector_v2() existed but
    # was never actually wired into load_companies(), so app.py's
    # `df.groupby("sector_v2")` calls (load_universe(), get_ai_rationale(),
    # the sector filter/UI) raised KeyError: 'sector_v2' on this checkout.
    # ey_bucket is left untouched -- still the deals-comps peer key per
    # sector_taxonomy_v2.py's own module docstring.
    df["sector_v2"] = [
        classify_sector_v2(symbol, industry)
        for symbol, industry in zip(df["symbol"], df["industry"])
    ]

    return df.reset_index(drop=True)


def _coerce_numeric_text(series):
    """Strip commas/%% and blank out 'NA' or free-text notes, then coerce to float."""
    cleaned = (
        series.astype(str)
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def load_deals(path=DEFAULT_DEALS_PATH):
    """Load deals_full_v2.csv into a validated DataFrame.

    Adds `deal_value_usdm_numeric` and `stake_pct_numeric` alongside the
    original raw text columns, so malformed values (commas, "NA", free-text
    notes) are excluded from calculations but the source text is still shown,
    per PRD section 5.
    """
    df = pd.read_csv(path)
    validate_required_columns(df, REQUIRED_DEAL_COLUMNS, "deals_full_v2.csv")

    df["deal_value_usdm_numeric"] = _coerce_numeric_text(df["deal_value_usdm"])
    df["stake_pct_numeric"] = _coerce_numeric_text(df["stake_pct"])

    # Guard against any stray bucket label that isn't one of the 6 EY buckets
    # or "Unclassified" -- never invent a new bucket at load time.
    df["ey_bucket"] = df["ey_bucket"].where(df["ey_bucket"].isin(ALL_BUCKETS), UNCLASSIFIED_BUCKET)

    return df.reset_index(drop=True)


def get_data_as_of(companies_df):
    """Return the latest as_of_date across all companies, for display in the UI."""
    dates = pd.to_datetime(companies_df["as_of_date"], errors="coerce")
    return dates.max().strftime("%Y-%m-%d")


if __name__ == "__main__":
    companies = load_companies()
    deals = load_deals()

    print(f"companies: {len(companies)} rows loaded")
    print(f"  null name after fill: {companies['name'].isna().sum()}")
    print("  ey_bucket distribution:")
    print(companies["ey_bucket"].value_counts().to_string())
    unclassified_pct = (companies["ey_bucket"] == UNCLASSIFIED_BUCKET).mean() * 100
    classified_pct = 100 - unclassified_pct
    print(f"  classified (non-Unclassified): {classified_pct:.1f}% "
          f"({'meets' if classified_pct >= 90 else 'BELOW'} 90% PRD acceptance bar)")

    print()
    print(f"deals: {len(deals)} rows loaded")
    print(f"  deal_value_usdm_numeric NaN count: {deals['deal_value_usdm_numeric'].isna().sum()} "
          f"(of which raw 'NA' text: {(deals['deal_value_usdm'].astype(str).str.strip() == 'NA').sum()})")
    print(f"  stake_pct_numeric NaN count: {deals['stake_pct_numeric'].isna().sum()}")
    print(f"  ey_bucket distribution:")
    print(deals["ey_bucket"].value_counts().to_string())

    print()
    print(f"data as of: {get_data_as_of(companies)}")
