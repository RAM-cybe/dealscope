#!/usr/bin/env python3
"""One-time (per quarter, via the same GitHub Actions pattern as enrich_dataset.py)
pull of the fields needed for Part 1 of the financial-health/risk-score round:

  - ebit, total_liabilities (real new fields on the live dataset, currency-guarded
    the same way as the other 6 currency-sensitive fields already in
    enrich_dataset.py)
  - two annual periods (latest + prior) of everything needed to compute the
    Piotroski F-Score deltas, pulled from the SAME yfinance balance_sheet /
    financials / cashflow calls already being made for ebit/total_liabilities
    (no extra network cost -- these statements return up to 5 annual periods
    in a single call, confirmed empirically before writing this script)
  - the extra fields Beneish M-Score would need, pulled the same way, purely
    to measure real population/coverage before deciding whether to build it

This is a measurement + field-collection pass. Scoring logic (Z-Score,
F-Score) lives in src/logic/ and is computed from this cache's output, not
inside this script -- keeps the network-pull code and the scoring math
independently testable.

Resumable: writes to a CSV cache after every company, safe to Ctrl-C and
rerun (already-fetched symbols are skipped).
"""
import csv
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

BASE = Path(__file__).resolve().parents[2]
COMPANIES = BASE / "data" / "enriched" / "dealscope_base_2026-07-12.csv"
CACHE = BASE / "archive" / "data_pipeline_scripts" / "_financial_health_cache.csv"

FIELDS = [
    "symbol", "financial_currency", "currency_flag", "periods_available",
    "ebit", "total_liabilities",
    "ni_0", "ni_1", "cfo_0", "cfo_1", "ta_0", "ta_1", "ltd_0", "ltd_1",
    "ca_0", "ca_1", "cl_0", "cl_1", "rev_0", "rev_1", "cogs_0", "cogs_1",
    "shares_0", "shares_1",
    "ar_0", "ar_1", "ppe_net_0", "ppe_net_1", "ppe_gross_0", "ppe_gross_1",
    "dep_0", "dep_1", "sga_0", "sga_1", "sti_0", "sti_1",
    "error_reason",
]


def load_cache():
    if not CACHE.exists():
        return {}
    with CACHE.open(newline="", encoding="utf-8") as f:
        return {r["symbol"]: r for r in csv.DictReader(f) if r.get("symbol")}


def save_cache(values):
    tmp = CACHE.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for symbol in sorted(values):
            w.writerow({k: values[symbol].get(k, "") for k in FIELDS})
    tmp.replace(CACHE)


def at(df, label, i):
    """Scalar at row `label`, column index i (0=latest), or None."""
    if label not in df.index or i >= len(df.columns):
        return None
    v = df.loc[label, df.columns[i]]
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def pull_one(symbol):
    row = {"symbol": symbol}
    last_reason = ""
    for attempt in range(4):
        try:
            ticker = yf.Ticker(symbol + ".NS")
            info = ticker.info
            fin_currency = info.get("financialCurrency", "INR")
            currency_flag = "OK" if fin_currency == "INR" else "USD_REPORTED"
            row["financial_currency"] = fin_currency
            row["currency_flag"] = currency_flag

            bs = ticker.balance_sheet
            fin = ticker.financials
            cf = ticker.cashflow

            if bs.empty or fin.empty:
                row["error_reason"] = "empty balance_sheet or financials from yfinance"
                row["periods_available"] = 0
                return row

            row["periods_available"] = min(len(bs.columns), len(fin.columns))

            ebit = at(fin, "EBIT", 0)
            total_liab = at(bs, "Total Liabilities Net Minority Interest", 0)
            if currency_flag != "OK":
                ebit = None
                total_liab = None
            row["ebit"] = ebit
            row["total_liabilities"] = total_liab

            for i in (0, 1):
                row[f"ni_{i}"] = at(fin, "Net Income", i)
                row[f"cfo_{i}"] = at(cf, "Operating Cash Flow", i)
                row[f"ta_{i}"] = at(bs, "Total Assets", i)
                row[f"ltd_{i}"] = at(bs, "Long Term Debt", i)
                row[f"ca_{i}"] = at(bs, "Current Assets", i)
                row[f"cl_{i}"] = at(bs, "Current Liabilities", i)
                row[f"rev_{i}"] = at(fin, "Total Revenue", i)
                row[f"cogs_{i}"] = at(fin, "Cost Of Revenue", i)
                row[f"shares_{i}"] = at(bs, "Ordinary Shares Number", i)
                row[f"ar_{i}"] = at(bs, "Accounts Receivable", i)
                row[f"ppe_net_{i}"] = at(bs, "Net PPE", i)
                row[f"ppe_gross_{i}"] = at(bs, "Gross PPE", i)
                row[f"dep_{i}"] = at(fin, "Reconciled Depreciation", i)
                row[f"sga_{i}"] = at(fin, "Selling General And Administration", i)
                row[f"sti_{i}"] = at(bs, "Other Short Term Investments", i)

            row["error_reason"] = ""
            return row
        except Exception as exc:
            last_reason = str(exc).replace("\n", " ")[:200]
            # "Invalid Crumb" / 401s are Yahoo's rate-limit response, not a
            # per-symbol data problem -- back off harder than a normal retry
            # so a burst of these doesn't just fail the whole remaining batch.
            backoff = 8 * (attempt + 1) if "Crumb" in last_reason or "401" in last_reason else 2 * (attempt + 1)
            time.sleep(backoff)
    row["error_reason"] = f"failed after 4 attempts: {last_reason}"
    row["periods_available"] = 0
    return row


def main():
    df = pd.read_csv(COMPANIES)
    symbols = df["symbol"].tolist()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if limit:
        symbols = symbols[:limit]
        print(f"LIMIT set -- only pulling first {limit} symbols (test mode)")

    cache = load_cache()
    todo = [s for s in symbols if s not in cache]
    print(f"{len(symbols)} total symbols, {len(cache)} already cached, {len(todo)} to pull")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(pull_one, s): s for s in todo}
        done = 0
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"symbol": symbol, "error_reason": f"unhandled: {exc}"}
            cache[symbol] = result
            done += 1
            if done % 20 == 0 or done == len(todo):
                save_cache(cache)
                print(f"{done}/{len(todo)} done (cumulative cache: {len(cache)})", flush=True)

    save_cache(cache)
    print(f"DONE. Wrote {CACHE} with {len(cache)} rows.")


if __name__ == "__main__":
    main()
