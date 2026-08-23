"""Load and validate the two bundled CSVs into clean, schema-conformant DataFrames."""

from pathlib import Path

import pandas as pd

from .paths import companies_csv_path, deals_csv_path
from .schema import (
    ALL_BUCKETS,
    COMPANY_NUMERIC_COLUMNS,
    REQUIRED_COMPANY_COLUMNS,
    REQUIRED_DEAL_COLUMNS,
    UNCLASSIFIED_BUCKET,
    validate_required_columns,
)
from .deals_sector_v2 import classify_deal_sector_v2
from .sector_mapping import classify_sector
from .sector_taxonomy_v2 import classify_sector_v2

# Live files are named in data/live.json so promotion does not edit this module.
DEFAULT_COMPANIES_PATH = companies_csv_path()
DEFAULT_DEALS_PATH = deals_csv_path()


def load_companies(path=None):
    """Load the company dataset into a validated, typed DataFrame with an ey_bucket column."""
    path = Path(path) if path is not None else companies_csv_path()
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


def load_deals(path=None):
    """Load the deals CSV named in data/live.json into a validated DataFrame.

    Adds `deal_value_usdm_numeric` and `stake_pct_numeric` alongside the
    original raw text columns, so malformed values (commas, "NA", free-text
    notes) are excluded from calculations but the source text is still shown,
    per PRD section 5.
    """
    path = Path(path) if path is not None else deals_csv_path()
    df = pd.read_csv(path)
    validate_required_columns(df, REQUIRED_DEAL_COLUMNS, Path(path).name)

    df["deal_value_usdm_numeric"] = _coerce_numeric_text(df["deal_value_usdm"])
    df["stake_pct_numeric"] = _coerce_numeric_text(df["stake_pct"])

    # Guard against any stray bucket label that isn't one of the 6 EY buckets
    # or "Unclassified" -- never invent a new bucket at load time.
    df["ey_bucket"] = df["ey_bucket"].where(df["ey_bucket"].isin(ALL_BUCKETS), UNCLASSIFIED_BUCKET)

    # 13-sector v2 taxonomy for comps matching. Companies and deals have to
    # speak the same sector vocabulary; ey_bucket stays as the legacy key.
    # Pass target/acquirer/year so the 48 landmark rescues apply when
    # sector_raw is blank; labelled deals still use the sector_raw lookup.
    df["sector_v2"] = [
        classify_deal_sector_v2(raw, target=target, acquirer=acquirer, report_year=year)
        for raw, target, acquirer, year in zip(
            df["sector_raw"], df["target"], df["acquirer"], df["report_year"]
        )
    ]

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
