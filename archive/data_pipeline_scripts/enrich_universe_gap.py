"""Enrich the 335 newly-discovered NSE BE/BZ-series companies (excluded from
the original 2,046-company universe by an accidental SERIES == "EQ" filter --
see data/quality_reports/universe_gap_be_bz_2026-07-21.csv) with the full
current dataset schema, from scratch.

Unlike enrich_dataset.py (re-pulls a *subset* of fields for companies
ALREADY in the base CSV) or backfill_core_fields_2026-07.py (fills specific
missing fields on EXISTING rows), this is a from-scratch pull for companies
that have no row at all yet. No new field logic is invented here -- every
field is sourced exactly the way the scripts that originally built the
current 2,046-company universe source it:

  - core v1 fields (name/sector/industry/revenue/ebitda/ebitda_margin_pct/
    total_debt/market_cap/insider_holding_pct/revenue_growth_pct/
    return_on_equity_pct) + net_income: one yfinance .info call, same fields
    as pull_remaining.py + pull_net_income.py.
  - return_on_capital_employed_pct, promoter_pledge_pct: fetch_roce() /
    fetch_pledge() imported UNCHANGED from enrich_v2.py -- not reimplemented.
  - extended ratios (financial_currency, currency_flag, total_assets,
    retained_earnings, working_capital, current_ratio, quick_ratio,
    debt_to_equity, return_on_assets, beta, peg_ratio, enterprise_value,
    total_cash, operating_cash_flow, free_cash_flow, price_to_book,
    trailing_pe): same .info / .balance_sheet fields as enrich_dataset.py's
    fetch_refreshed_fields().
  - ebit, total_liabilities, and the Piotroski fy0/fy1 fields: same
    .balance_sheet / .financials / .cashflow labels as pull_financial_health.py's
    pull_one(), renamed to the live schema's column names exactly as
    merge_financial_health.py's RENAME map does.

Currency guard applied identically to enrich_dataset.py / pull_financial_health.py:
a non-INR-reported symbol (currency_flag != "OK") gets every currency-sensitive
field blanked, never a USD-scale number written as if it were INR.

Resumable, same pattern as batch_generate_rationale.py: every company's fully
assembled row is cached to a CSV after that company completes, keyed by
symbol. Re-running skips symbols already in the cache and continues with the
rest -- the cache IS the progress, there is no "start over" state. Never
writes to the live base CSV -- output is a separate file for human review.

Run from the repo root:
    python3 enrich_universe_gap.py [--limit N] [--delay SECONDS]

    --limit N    stop after N successful pulls this run (for a smoke test)
    --delay S    seconds between companies (default 1.5)

Writes:
    data/quality_reports/universe_gap_enrichment_cache.csv   one row per company, appended as it goes
    data/quality_reports/universe_gap_enrichment_log_<date>.csv   per-company outcome log
"""

import argparse
import csv
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "archive" / "data_pipeline_scripts"))
from enrich_v2 import fetch_roce, fetch_pledge  # noqa: E402 -- reused unchanged, not reimplemented

TARGET_LIST_PATH = REPO_ROOT / "data" / "quality_reports" / "universe_gap_be_bz_2026-07-21.csv"
# RAM's explicit decision: tied to the 2018 IL&FS group insolvency, may not
# be meaningfully operating companies -- scoring them normally would mislead.
EXCLUDED_SYMBOLS = {"IL&FSENGG", "IL&FSTRANS"}

CACHE_PATH = REPO_ROOT / "data" / "quality_reports" / "universe_gap_enrichment_cache.csv"
LOG_DIR = REPO_ROOT / "data" / "quality_reports"
LOG_PATH = LOG_DIR / f"universe_gap_enrichment_log_{datetime.now().strftime('%Y-%m-%d')}.csv"

# Full live schema, in the same column order as data/enriched/dealscope_base_2026-07-20.csv
# (checked directly against that file's header -- not guessed).
SCHEMA_COLUMNS = [
    "symbol", "name", "sector", "industry", "revenue", "ebitda", "ebitda_margin_pct",
    "total_debt", "market_cap", "insider_holding_pct", "revenue_growth_pct",
    "return_on_equity_pct", "return_on_capital_employed_pct", "promoter_pledge_pct",
    "net_income", "as_of_date", "status", "financial_currency", "currency_flag",
    "total_assets", "retained_earnings", "working_capital", "current_ratio",
    "quick_ratio", "debt_to_equity", "return_on_assets", "beta", "peg_ratio",
    "enterprise_value", "total_cash", "operating_cash_flow", "free_cash_flow",
    "price_to_book", "trailing_pe", "data_pull_date", "ebit", "total_liabilities",
    "net_income_fy0", "net_income_fy1", "operating_cash_flow_fy0", "operating_cash_flow_fy1",
    "total_assets_fy0", "total_assets_fy1", "long_term_debt_fy0", "long_term_debt_fy1",
    "current_assets_fy0", "current_assets_fy1", "current_liabilities_fy0", "current_liabilities_fy1",
    "total_revenue_fy0", "total_revenue_fy1", "cost_of_revenue_fy0", "cost_of_revenue_fy1",
    "shares_outstanding_fy0", "shares_outstanding_fy1", "market_cap_as_of",
]

# Same currency-sensitive field lists as enrich_dataset.py / merge_financial_health.py.
CURRENCY_SENSITIVE_INFO_FIELDS = [
    "total_assets", "retained_earnings", "working_capital",
    "total_cash", "operating_cash_flow", "free_cash_flow",
]
CURRENCY_SENSITIVE_FY_FIELDS = [
    "net_income_fy0", "net_income_fy1", "operating_cash_flow_fy0", "operating_cash_flow_fy1",
    "total_assets_fy0", "total_assets_fy1", "long_term_debt_fy0", "long_term_debt_fy1",
    "current_assets_fy0", "current_assets_fy1", "current_liabilities_fy0", "current_liabilities_fy1",
    "total_revenue_fy0", "total_revenue_fy1", "cost_of_revenue_fy0", "cost_of_revenue_fy1",
]
CURRENCY_SENSITIVE_FIELDS = CURRENCY_SENSITIVE_INFO_FIELDS + CURRENCY_SENSITIVE_FY_FIELDS + ["ebit", "total_liabilities"]


def pct(x):
    """Same convention as pull_remaining.py / pull_net_income.py: yfinance
    reports these as a fraction (0.129), the dataset stores a percentage (12.9)."""
    return round(x * 100, 4) if isinstance(x, (int, float)) else None


def stmt_at(df, label, i=0):
    """Scalar at row `label`, column index i (0=latest), or None. Same helper
    as pull_financial_health.py's at() / enrich_dataset.py's scalar_at()."""
    if label not in df.index or i >= len(df.columns):
        return None
    v = df.loc[label, df.columns[i]]
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def load_cache():
    if not CACHE_PATH.exists():
        return {}
    with CACHE_PATH.open(newline="", encoding="utf-8") as f:
        return {r["symbol"]: r for r in csv.DictReader(f) if r.get("symbol")}


def save_cache(cache):
    tmp = CACHE_PATH.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA_COLUMNS)
        w.writeheader()
        for symbol in cache:
            w.writerow({k: cache[symbol].get(k, "") for k in SCHEMA_COLUMNS})
    tmp.replace(CACHE_PATH)


def fetch_company_row(symbol):
    """Pull the full current schema for one brand-new company.

    Returns (row_dict, reason). row_dict is None only on a total failure (no
    name AND no market cap AND no revenue -- same "likely delisted/invalid"
    check pull_remaining.py uses). Otherwise row_dict always has every
    SCHEMA_COLUMNS key, blank/None for whatever a specific source genuinely
    couldn't provide -- never fabricated, matching this project's
    established "a real gap beats a guessed number" discipline throughout.
    """
    ticker = yf.Ticker(f"{symbol}.NS")

    last_err = None
    info = None
    for attempt in range(3):
        try:
            info = ticker.info
            break
        except Exception as exc:
            last_err = str(exc).replace("\n", " ")[:180]
            time.sleep(3 * (attempt + 1))
    if info is None:
        return None, f"yfinance .info unavailable after 3 attempts: {last_err}"

    name = info.get("longName") or info.get("shortName")
    market_cap = info.get("marketCap")
    revenue = info.get("totalRevenue")
    if not name and market_cap is None and revenue is None:
        return None, "no data returned (possibly delisted/invalid symbol)"

    fin_currency = info.get("financialCurrency", "INR")
    currency_flag = "OK" if fin_currency == "INR" else "USD_REPORTED"
    today_iso = date.today().isoformat()

    row = {
        "symbol": symbol,
        "name": name or "",
        "sector": info.get("sector") or "",
        "industry": info.get("industry") or "",
        "revenue": revenue,
        "ebitda": info.get("ebitda"),
        "ebitda_margin_pct": pct(info.get("ebitdaMargins")),
        "total_debt": info.get("totalDebt"),
        "market_cap": market_cap,
        "insider_holding_pct": pct(info.get("heldPercentInsiders")),
        "revenue_growth_pct": pct(info.get("revenueGrowth")),
        "return_on_equity_pct": pct(info.get("returnOnEquity")),
        "net_income": info.get("netIncomeToCommon"),
        "as_of_date": today_iso,
        "status": "ok",
        "financial_currency": fin_currency,
        "currency_flag": currency_flag,
        "current_ratio": info.get("currentRatio"),
        "quick_ratio": info.get("quickRatio"),
        "debt_to_equity": info.get("debtToEquity"),
        "return_on_assets": info.get("returnOnAssets"),
        "beta": info.get("beta"),
        "peg_ratio": info.get("pegRatio"),
        "enterprise_value": info.get("enterpriseValue"),
        "total_cash": info.get("totalCash"),
        "operating_cash_flow": info.get("operatingCashflow"),
        "free_cash_flow": info.get("freeCashflow"),
        "price_to_book": info.get("priceToBook"),
        "trailing_pe": info.get("trailingPE"),
        "data_pull_date": today_iso,
        "market_cap_as_of": today_iso,
    }

    try:
        bs = ticker.balance_sheet
        fin = ticker.financials
        cf = ticker.cashflow
    except Exception:
        bs = fin = cf = pd.DataFrame()

    if not bs.empty:
        row["total_assets"] = stmt_at(bs, "Total Assets", 0)
        row["retained_earnings"] = stmt_at(bs, "Retained Earnings", 0)
        ca0 = stmt_at(bs, "Current Assets", 0)
        cl0 = stmt_at(bs, "Current Liabilities", 0)
        row["working_capital"] = (ca0 - cl0) if ca0 is not None and cl0 is not None else None
    else:
        row["total_assets"] = row["retained_earnings"] = row["working_capital"] = None

    if not bs.empty and not fin.empty:
        row["ebit"] = stmt_at(fin, "EBIT", 0)
        row["total_liabilities"] = stmt_at(bs, "Total Liabilities Net Minority Interest", 0)
        for i in (0, 1):
            row[f"net_income_fy{i}"] = stmt_at(fin, "Net Income", i)
            row[f"operating_cash_flow_fy{i}"] = stmt_at(cf, "Operating Cash Flow", i)
            row[f"total_assets_fy{i}"] = stmt_at(bs, "Total Assets", i)
            row[f"long_term_debt_fy{i}"] = stmt_at(bs, "Long Term Debt", i)
            row[f"current_assets_fy{i}"] = stmt_at(bs, "Current Assets", i)
            row[f"current_liabilities_fy{i}"] = stmt_at(bs, "Current Liabilities", i)
            row[f"total_revenue_fy{i}"] = stmt_at(fin, "Total Revenue", i)
            row[f"cost_of_revenue_fy{i}"] = stmt_at(fin, "Cost Of Revenue", i)
            row[f"shares_outstanding_fy{i}"] = stmt_at(bs, "Ordinary Shares Number", i)
    else:
        row["ebit"] = row["total_liabilities"] = None
        for i in (0, 1):
            for prefix in ("net_income_fy", "operating_cash_flow_fy", "total_assets_fy",
                            "long_term_debt_fy", "current_assets_fy", "current_liabilities_fy",
                            "total_revenue_fy", "cost_of_revenue_fy", "shares_outstanding_fy"):
                row[f"{prefix}{i}"] = None

    if currency_flag != "OK":
        for f in CURRENCY_SENSITIVE_FIELDS:
            row[f] = None

    roce_value, _roce_reason = fetch_roce(symbol)
    row["return_on_capital_employed_pct"] = float(roce_value) if roce_value else None

    pledge_value, _pledge_reason = fetch_pledge(symbol)
    row["promoter_pledge_pct"] = float(pledge_value) if pledge_value not in ("", None) else None

    return row, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--symbols", type=str, default=None,
                         help="comma-separated symbols to enrich instead of the full pending list "
                              "(for smoke-testing specific companies, e.g. --symbols MTARTECH,GANGAFO-RE)")
    args = parser.parse_args()

    print(f"Loading target list: {TARGET_LIST_PATH}")
    with TARGET_LIST_PATH.open(newline="", encoding="utf-8") as f:
        target_rows = list(csv.DictReader(f))
    symbols = [r["symbol"] for r in target_rows if r["symbol"] not in EXCLUDED_SYMBOLS]
    print(f"{len(target_rows)} in target list, {len(EXCLUDED_SYMBOLS)} excluded "
          f"({', '.join(sorted(EXCLUDED_SYMBOLS))}), {len(symbols)} to enrich")

    cache = load_cache()

    if args.symbols:
        requested = [s.strip() for s in args.symbols.split(",") if s.strip()]
        unknown = [s for s in requested if s not in symbols]
        if unknown:
            print(f"WARNING: not in the target list (or excluded): {unknown}")
        pending = [s for s in requested if s in symbols and s not in cache]
        print(f"--symbols: {len(pending)} of {len(requested)} requested still pending "
              f"({len(requested) - len(pending)} already cached or invalid)")
    else:
        pending = [s for s in symbols if s not in cache]
        print(f"{len(cache)} already cached, {len(pending)} still pending")
        if args.limit:
            pending = pending[: args.limit]
            print(f"--limit {args.limit}: this run will attempt {len(pending)} companies")

    log_is_new = not LOG_PATH.exists()
    generated = failed = 0

    with LOG_PATH.open("a", newline="", encoding="utf-8") as log_file:
        writer = csv.writer(log_file)
        if log_is_new:
            writer.writerow(["timestamp", "symbol", "outcome", "detail"])

        for i, symbol in enumerate(pending, 1):
            print(f"  [{i}/{len(pending)}] {symbol} ...", end=" ", flush=True)
            try:
                row, reason = fetch_company_row(symbol)
            except Exception as exc:
                row, reason = None, f"{type(exc).__name__}: {str(exc)[:160]}"

            now = datetime.now().isoformat(timespec="seconds")
            if row:
                cache[symbol] = row
                save_cache(cache)
                generated += 1
                blanks = sum(1 for c in SCHEMA_COLUMNS if row.get(c) in (None, ""))
                writer.writerow([now, symbol, "ok", f"{blanks}/{len(SCHEMA_COLUMNS)} fields blank"])
                print(f"ok ({blanks}/{len(SCHEMA_COLUMNS)} fields blank)")
            else:
                failed += 1
                writer.writerow([now, symbol, "failed", reason])
                print(f"FAILED -- {reason}")
            log_file.flush()

            time.sleep(args.delay)

    print(f"\n=== Done ===")
    print(f"This run: {generated} ok, {failed} failed")
    print(f"Total cached now: {len(cache)} / {len(symbols)}")
    print(f"Cache: {CACHE_PATH}")
    print(f"Log:   {LOG_PATH}")
    if len(cache) < len(symbols):
        print(f"\n{len(symbols) - len(cache)} still pending -- re-run this script to resume "
              f"exactly where it stopped (cached companies are skipped without any pull).")


if __name__ == "__main__":
    main()
