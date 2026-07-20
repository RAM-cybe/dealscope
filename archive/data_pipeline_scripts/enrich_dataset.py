"""Quarterly fundamentals refresh: re-pull the subset of fields this script
actually sources from yfinance for all companies, and merge them back into
the CURRENT base dataset column-by-column, per symbol -- every other column
(including ones this script has never known about, like the Part 1
financial-health fields below) passes through completely untouched.

2026-07-20 rewrite -- column-safe merge, not row-replacement. The previous
version built a brand-new `new_row` dict per company containing only the ~34
fields it explicitly named, then wrote `pd.DataFrame(results)` as the output.
That silently DROPPED every column not in that list -- including `ebit`,
`total_liabilities`, and the 18 Piotroski F-Score fy0/fy1 fields that
REQUIRED_COMPANY_COLUMNS (src/data/schema.py) has required since the
2026-07-17 data pull. Confirmed, not assumed: the old script's output was
missing all 21 of those columns, so `check_snapshot_quality.py`'s call to
`load_companies()` (which validates every required column is present) would
raise SchemaError and hard-fail on the very next real quarterly run -- this
wasn't a "some data goes stale" bug, it was a "the workflow crashes" bug.
Loading the full base CSV and updating only the fields this script actually
refreshes, in place on a copy of that full frame, fixes both: nothing gets
silently dropped, and the fields genuinely not sourced from this pull are
preserved exactly as they were before this run touched anything.

Run from the repo root:
    python3 archive/data_pipeline_scripts/enrich_dataset.py

Env vars (set by quarterly_refresh.yml; safe defaults for a standalone run):
    DEALSCOPE_INPUT_FILE   path to the current live base CSV to merge into
                           (defaults to companies_full_v2.csv for a local run)
    DEALSCOPE_OUTPUT_DIR   where to write the new dated snapshot
    DEALSCOPE_LIMIT        test-only: only re-pull the first N symbols (see
                           the "limited run" note below)
"""

import os
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
from pathlib import Path

INPUT_FILE = os.environ.get("DEALSCOPE_INPUT_FILE", "companies_full_v2.csv")
OUTPUT_DIR = Path(os.environ.get("DEALSCOPE_OUTPUT_DIR", "."))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
_STAMP = datetime.now().strftime('%Y-%m-%d')
OUTPUT_PARQUET = OUTPUT_DIR / f"dealscope_{_STAMP}.parquet"
OUTPUT_CSV = OUTPUT_DIR / f"dealscope_{_STAMP}.csv"
BATCH_SIZE = 100
SLEEP_BETWEEN = 1.2

# The exact set of columns this script re-derives from a *live* yfinance call
# this run -- everything else in the base CSV (revenue, ebitda, total_debt,
# market_cap, promoter_pledge_pct, the Piotroski fy0/fy1 fields, etc.) is
# passed through unchanged because this script was never given a fresh
# source for it. Keeping this list explicit (rather than inferring it from
# whatever keys happen to get set) is what makes the merge column-safe: a
# future field added to the base schema is preserved by default, not by
# remembering to add it to some "don't touch" list.
YFINANCE_REFRESHED_FIELDS = [
    "financial_currency", "currency_flag",
    "total_assets", "retained_earnings", "working_capital",
    "current_ratio", "quick_ratio", "debt_to_equity", "return_on_assets",
    "beta", "peg_ratio", "enterprise_value", "total_cash",
    "operating_cash_flow", "free_cash_flow", "price_to_book", "trailing_pe",
    "data_pull_date",
]

# currency_flag != "OK" means yfinance's own financialCurrency metadata says
# this symbol's *.info-sourced figures aren't in INR. Confirmed empirically
# (2026-07-13, not assumed): for both currency-flagged symbols in this
# dataset (INFY, HCLTECH), every one of these 6 fields is USD-scale --
# roughly 100x too small versus same-sector INR peers on a value/market_cap
# ratio basis. Do not narrow this to a subset of the 6 based on how any one
# field looks -- a field looking "plausible" for one flagged symbol doesn't
# confirm it's actually INR (see HCLTECH: total_assets/working_capital
# happened to sit in a peer-plausible ratio range while total_cash/
# operating_cash_flow/free_cash_flow did not, for the same company, same
# flag) -- blank defensively per the project's established currency-bug
# precedent. Note revenue/ebitda/total_debt/net_income get this same
# protection "for free" -- they aren't in YFINANCE_REFRESHED_FIELDS at all,
# so a currency-flagged symbol's existing (already-blanked, per the
# 2026-07-13 fix) values for those simply pass through untouched.
CURRENCY_SENSITIVE_NEW_FIELDS = [
    "total_assets", "retained_earnings", "working_capital",
    "total_cash", "operating_cash_flow", "free_cash_flow",
]


def fetch_refreshed_fields(symbol):
    """Pull only YFINANCE_REFRESHED_FIELDS for one symbol. Returns a dict with
    exactly those keys (never more, never fewer) so a caller can safely
    assign df.loc[mask, key] = value for each one without risk of writing an
    unexpected column. Raises on failure -- the caller decides per-row
    whether to skip (never silently applies a partial/stale value)."""
    ticker = f"{symbol}.NS"
    stock = yf.Ticker(ticker)
    info = stock.info
    fin_currency = info.get('financialCurrency', 'INR')
    currency_flag = "OK" if fin_currency == "INR" else "USD_REPORTED"

    bs = stock.balance_sheet
    total_assets = retained_earnings = working_capital = None
    if not bs.empty:
        latest = bs.columns[0]
        if 'Total Assets' in bs.index:
            total_assets = bs.loc['Total Assets', latest]
        if 'Retained Earnings' in bs.index:
            retained_earnings = bs.loc['Retained Earnings', latest]
        if 'Current Assets' in bs.index and 'Current Liabilities' in bs.index:
            working_capital = bs.loc['Current Assets', latest] - bs.loc['Current Liabilities', latest]

    fields = {
        "financial_currency": fin_currency,
        "currency_flag": currency_flag,
        "total_assets": total_assets,
        "retained_earnings": retained_earnings,
        "working_capital": working_capital,
        "current_ratio": info.get('currentRatio'),
        "quick_ratio": info.get('quickRatio'),
        "debt_to_equity": info.get('debtToEquity'),
        "return_on_assets": info.get('returnOnAssets'),
        "beta": info.get('beta'),
        "peg_ratio": info.get('pegRatio'),
        "enterprise_value": info.get('enterpriseValue'),
        "total_cash": info.get('totalCash'),
        "operating_cash_flow": info.get('operatingCashflow'),
        "free_cash_flow": info.get('freeCashflow'),
        "price_to_book": info.get('priceToBook'),
        "trailing_pe": info.get('trailingPE'),
        "data_pull_date": datetime.now().strftime('%Y-%m-%d'),
    }

    if currency_flag != "OK":
        for field in CURRENCY_SENSITIVE_NEW_FIELDS:
            fields[field] = None

    return fields


NUMERIC_CLEAN_COLUMNS = [
    'trailing_pe', 'forward_pe', 'peg_ratio', 'beta', 'price_to_book',
    'current_ratio', 'quick_ratio', 'debt_to_equity',
]


def clean_numeric(df):
    """Coerce known-numeric columns and fix Infinity/bad values -- same
    columns/behavior as the original script, just applied to the full
    merged frame instead of the narrower `results` frame."""
    for col in NUMERIC_CLEAN_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def main():
    print("Loading existing dataset...")
    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df)} companies, {len(df.columns)} columns")

    symbols = df["symbol"].tolist()

    # Test-only: DEALSCOPE_LIMIT re-pulls fresh data for only the first N
    # symbols, so a workflow_dispatch smoke-test can confirm the whole
    # pipeline (pull -> snapshot -> quality check -> PR) in under a minute
    # instead of the ~45+ minutes a full 2,046-company quarterly run takes.
    # The OUTPUT is still the full 2,046-row frame -- only the first N rows'
    # YFINANCE_REFRESHED_FIELDS actually change, everything else (including
    # the other ~2,026 companies, in full, all columns) passes through
    # unchanged. A truncated-to-N-rows output would both fail schema
    # validation trivially (missing symbols a reviewer would need to
    # cross-check) and misrepresent what a "snapshot" is. Unset (the
    # default) for every real scheduled run -- never used to silently skip
    # companies in production.
    _limit = os.environ.get("DEALSCOPE_LIMIT")
    if _limit:
        symbols = symbols[:int(_limit)]
        print(f"DEALSCOPE_LIMIT set -- refreshing only the first {len(symbols)} "
              f"of {len(df)} companies (test run only; output still has all "
              f"{len(df)} rows)")

    merged = df.copy()
    updated, failed = 0, 0

    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {symbol}.NS ...", end=" ")
        try:
            fields = fetch_refreshed_fields(symbol)
            row_mask = merged["symbol"] == symbol
            for field, value in fields.items():
                merged.loc[row_mask, field] = value
            updated += 1
            print("OK")
        except Exception as e:
            failed += 1
            print(f"ERROR: {str(e)[:50]}")
            # Leave every column for this symbol exactly as it was in the
            # base file -- never partially apply a fetch that raised partway
            # through, and never blank a real prior value just because
            # today's pull failed for one ticker.

        if i % BATCH_SIZE == 0:
            clean_numeric(merged).to_parquet(OUTPUT_PARQUET, index=False)
            print(f"  Saved progress... ({updated} updated, {failed} failed so far)")

        time.sleep(SLEEP_BETWEEN)

    clean_numeric(merged)
    merged.to_parquet(OUTPUT_PARQUET, index=False)
    merged.to_csv(OUTPUT_CSV, index=False)

    print(f"\nDone: {updated} updated, {failed} failed out of {len(symbols)} "
          f"(refreshed); {len(merged)} total rows, {len(merged.columns)} columns "
          f"in output (unchanged from input's {len(df.columns)})")
    print(f"Files created:\n- {OUTPUT_PARQUET}\n- {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
