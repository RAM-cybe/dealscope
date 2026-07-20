"""Targeted backfill of the 8 tear-sheet "core fields" for companies currently
missing them -- NOT a full 2,046-company re-pull. Part of the 2026-07-20 data
quality audit's follow-up enrichment pass (see DATA_QUALITY_AUDIT_2026-07.md).

Only re-attempts a field for a company that is CURRENTLY MISSING that specific
field -- a company already has a value for a field, this script never
touches it, no matter what a fresh pull would return. This is the same
column-safe discipline as the 2026-07-20 enrich_dataset.py rewrite, applied
per-field instead of per-refresh-cycle.

Sources, matching each field's existing/established provenance in this
pipeline (not a new formula invented for this script):
  revenue, market_cap, total_debt   -> yfinance info["totalRevenue"/"marketCap"/"totalDebt"],
                                        raw, same as archive/data_pipeline_scripts/pull_remaining.py
  ebitda_margin_pct, return_on_equity_pct
                                     -> yfinance info["ebitdaMargins"/"returnOnEquity"] * 100,
                                        same pct() convention as pull_remaining.py
  trailing_pe                       -> yfinance info["trailingPE"], raw. No fallback --
                                        yfinance only returns a P/E for positive trailing
                                        earnings, so some real fraction of small-caps with
                                        negative/negligible earnings will legitimately have
                                        no valid P/E. Left as NaN, not chased further (see
                                        the audit report's "real data-availability wall").
  return_on_capital_employed_pct    -> fetch_roce() from enrich_v2.py, UNCHANGED: 100 x
                                        EBIT / (Total Assets - Current Liabilities) from
                                        Yahoo's own annual-statement timeseries. Already
                                        intentionally blank for banks (Yahoo doesn't expose
                                        Current Liabilities for financial-company balance
                                        sheets) -- this script does not change that.
  promoter_pledge_pct               -> fetch_pledge() from enrich_v2.py, UNCHANGED: NSE's
                                        own corporate-shareholding XBRL. NOT a yfinance
                                        field at all (yfinance carries no Indian promoter
                                        pledge data) -- reusing the existing NSE scraper is
                                        the only correct source, per this run's own
                                        investigation.

Currency guard: HCLTECH and INFY are the only two currency_flag != "OK"
(USD_REPORTED) companies in this dataset, and both are missing revenue and
total_debt -- exactly the two fields that get deliberately blanked for
USD-reported symbols elsewhere in this pipeline (see enrich_dataset.py's
CURRENCY_SENSITIVE_NEW_FIELDS and its own comment on why). If this script
backfilled revenue/total_debt for these two from a fresh yfinance pull, it
would silently re-introduce the exact USD-scale bug that was deliberately
fixed by blanking those fields in the first place. So: revenue and
total_debt are skipped (left blank, reason logged) for any company whose
EXISTING currency_flag column is not "OK" -- every other field (ratios,
which are currency-invariant) is unaffected and still gets attempted.

Bank/NBFC revenue definition (see this run's own investigation, documented
in DATA_QUALITY_AUDIT_2026-07.md and the report accompanying this script):
yfinance's own "Total Revenue"/info["totalRevenue"] for Indian banks sits
consistently BETWEEN Net Interest Income and gross Interest Income (verified
directly against HDFCBANK/SBIN/AXISBANK's raw yfinance income-statement
data) -- neither a bug nor equivalent to the "Total Income" figure banks
themselves publish or that screener.in/news headlines cite. DECISION: fill
missing revenue for Financial Services companies the same way as every
other sector (same field, same formula, no special-casing) -- the
definitional caveat applies equally to every already-populated bank revenue
value in this dataset already, so a newly-filled value is exactly as
consistent (and exactly as caveated) as its peers. This script does not
attempt to source a different figure for banks; it documents the caveat
instead, per the explicit instruction not to silently overwrite bank
revenue with a guessed/scraped number.

Writes a full audit log (every symbol x field attempt, source, before/after
value, timestamp) to data/quality_reports/backfill_log_<date>.csv, and a new
dated snapshot to data/snapshots/ (NEVER overwrites the currently-committed
base CSV directly) -- a human reviews the snapshot + log before promoting it,
same "never auto-apply a data change" discipline as quarterly_refresh.yml.

Run from the repo root:
    python3 archive/data_pipeline_scripts/backfill_core_fields_2026-07.py
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "archive" / "data_pipeline_scripts"))

from src.data.loaders import DEFAULT_COMPANIES_PATH  # noqa: E402
from enrich_v2 import fetch_roce, fetch_pledge  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "snapshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = REPO_ROOT / "data" / "quality_reports"
LOG_DIR.mkdir(parents=True, exist_ok=True)
_STAMP = datetime.now().strftime("%Y-%m-%d")
OUTPUT_CSV = OUT_DIR / f"dealscope_backfill_{_STAMP}.csv"
LOG_CSV = LOG_DIR / f"backfill_log_{_STAMP}.csv"

# The 6 fields sourced directly from a single yfinance .info call -- fetched
# together per symbol (one HTTP round-trip covers all 6) rather than one call
# per field, matching pull_remaining.py's own "one call gets everything"
# convention and keeping this a genuinely targeted, not wasteful, re-pull.
INFO_FIELDS = [
    "revenue", "ebitda_margin_pct", "total_debt", "market_cap",
    "trailing_pe", "return_on_equity_pct",
]
# Fields that need currency-guard protection -- see module docstring.
CURRENCY_SENSITIVE_FIELDS = {"revenue", "total_debt"}

REQUEST_DELAY_SECONDS = 1.0
MAX_RETRIES = 2


def pct(x):
    """Same convention as pull_remaining.py: yfinance reports these as a
    fraction (0.129), the dataset stores a percentage (12.9)."""
    return round(x * 100, 4) if isinstance(x, (int, float)) else None


def fetch_info_fields(symbol, needed_fields):
    """Pull only the subset of INFO_FIELDS this symbol is actually missing,
    from a single yfinance .info call. Returns {field: value_or_None}."""
    for attempt in range(MAX_RETRIES):
        try:
            info = yf.Ticker(f"{symbol}.NS").info
            result = {}
            if "revenue" in needed_fields:
                result["revenue"] = info.get("totalRevenue")
            if "total_debt" in needed_fields:
                result["total_debt"] = info.get("totalDebt")
            if "market_cap" in needed_fields:
                result["market_cap"] = info.get("marketCap")
            if "trailing_pe" in needed_fields:
                result["trailing_pe"] = info.get("trailingPE")
            if "ebitda_margin_pct" in needed_fields:
                result["ebitda_margin_pct"] = pct(info.get("ebitdaMargins"))
            if "return_on_equity_pct" in needed_fields:
                result["return_on_equity_pct"] = pct(info.get("returnOnEquity"))
            return result
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY_SECONDS * 2)
    return {}


def main():
    print(f"Loading base dataset: {DEFAULT_COMPANIES_PATH}")
    df = pd.read_csv(DEFAULT_COMPANIES_PATH)
    print(f"Loaded {len(df)} companies, {len(df.columns)} columns")

    core_fields = INFO_FIELDS + ["return_on_capital_employed_pct", "promoter_pledge_pct"]
    missing_mask = df[core_fields].isna()

    # Test-only: cap how many companies each pass attempts, so a smoke test
    # can validate the whole pipeline (fetch -> merge -> log -> snapshot) in
    # a couple minutes instead of the ~15-20 minutes a real full run takes.
    # Unset (the default) for the real backfill.
    _limit = os.environ.get("DEALSCOPE_LIMIT")
    _limit = int(_limit) if _limit else None

    merged = df.copy()
    log_rows = []
    now_iso = datetime.now().isoformat(timespec="seconds")

    def record(symbol, field, source, before, after, note):
        log_rows.append({
            "symbol": symbol, "field": field, "source": source,
            "before": before, "after": after, "note": note, "timestamp": now_iso,
        })

    # --- Pass 1: the 6 yfinance .info fields, one call per symbol that needs
    # at least one of them ---
    info_needed_mask = missing_mask[INFO_FIELDS].any(axis=1)
    info_symbols = df.loc[info_needed_mask, "symbol"].tolist()
    if _limit:
        info_symbols = info_symbols[:_limit]
    print(f"\nPass 1/3: yfinance .info fields for {len(info_symbols)} companies")

    for i, symbol in enumerate(info_symbols, 1):
        row_mask = merged["symbol"] == symbol
        row = df[df["symbol"] == symbol].iloc[0]
        needed = [f for f in INFO_FIELDS if pd.isna(row[f])]
        currency_flag = row.get("currency_flag", "OK")

        # Currency guard: never backfill revenue/total_debt for a
        # USD-reported symbol -- see module docstring.
        skipped_for_currency = [f for f in needed if f in CURRENCY_SENSITIVE_FIELDS and currency_flag != "OK"]
        for f in skipped_for_currency:
            record(symbol, f, "skipped", None, None,
                   f"currency_flag={currency_flag}, would silently reintroduce the "
                   f"USD-scale bug this field was originally blanked to avoid")
        needed = [f for f in needed if f not in skipped_for_currency]

        if not needed:
            continue

        print(f"  [{i}/{len(info_symbols)}] {symbol}: {needed} ...", end=" ")
        fetched = fetch_info_fields(symbol, needed)
        applied = []
        for field in needed:
            value = fetched.get(field)
            if value is None:
                record(symbol, field, "yfinance.info", None, None, "no value returned")
                continue
            merged.loc[row_mask, field] = value
            record(symbol, field, "yfinance.info", None, value, "backfilled")
            applied.append(field)
        print(f"filled {applied}" if applied else "nothing available")
        time.sleep(REQUEST_DELAY_SECONDS)

    # --- Pass 2: ROCE (separate Yahoo annual-statement endpoint) ---
    roce_symbols = df.loc[missing_mask["return_on_capital_employed_pct"], "symbol"].tolist()
    if _limit:
        roce_symbols = roce_symbols[:_limit]
    print(f"\nPass 2/3: ROCE (Yahoo annual statements) for {len(roce_symbols)} companies")

    for i, symbol in enumerate(roce_symbols, 1):
        print(f"  [{i}/{len(roce_symbols)}] {symbol} ...", end=" ")
        value, reason = fetch_roce(symbol)
        row_mask = merged["symbol"] == symbol
        if value:
            merged.loc[row_mask, "return_on_capital_employed_pct"] = float(value)
            record(symbol, "return_on_capital_employed_pct", "yfinance (Yahoo annual stmt)",
                   None, value, "backfilled")
            print(f"filled ({value})")
        else:
            record(symbol, "return_on_capital_employed_pct", "yfinance (Yahoo annual stmt)",
                   None, None, reason)
            print(f"no value ({reason})")
        time.sleep(REQUEST_DELAY_SECONDS)

    # --- Pass 3: promoter pledge (NSE XBRL, not yfinance at all) ---
    pledge_symbols = df.loc[missing_mask["promoter_pledge_pct"], "symbol"].tolist()
    if _limit:
        pledge_symbols = pledge_symbols[:_limit]
    print(f"\nPass 3/3: promoter pledge (NSE XBRL) for {len(pledge_symbols)} companies")

    for i, symbol in enumerate(pledge_symbols, 1):
        print(f"  [{i}/{len(pledge_symbols)}] {symbol} ...", end=" ")
        value, reason = fetch_pledge(symbol)
        row_mask = merged["symbol"] == symbol
        if value != "":
            merged.loc[row_mask, "promoter_pledge_pct"] = float(value)
            record(symbol, "promoter_pledge_pct", "NSE XBRL", None, value, "backfilled")
            print(f"filled ({value})")
        else:
            record(symbol, "promoter_pledge_pct", "NSE XBRL", None, None, reason)
            print(f"no value ({reason})")
        time.sleep(REQUEST_DELAY_SECONDS)

    # --- Write outputs ---
    merged.to_csv(OUTPUT_CSV, index=False)
    log_df = pd.DataFrame(log_rows)
    log_df.to_csv(LOG_CSV, index=False)

    filled = log_df[log_df["note"] == "backfilled"]
    print(f"\n=== Done ===")
    print(f"Attempts logged: {len(log_df)}")
    print(f"Fields actually backfilled: {len(filled)}")
    print(f"By field:\n{filled['field'].value_counts().to_string()}")
    print(f"\nSnapshot written to: {OUTPUT_CSV} (NOT the live base CSV -- for review)")
    print(f"Full audit log written to: {LOG_CSV}")


if __name__ == "__main__":
    main()
