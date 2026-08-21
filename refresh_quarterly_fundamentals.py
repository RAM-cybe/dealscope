"""Quarterly fundamentals refresh.

Re-pulls the numbers that actually change when companies report — revenue,
EBITDA, margins, ROCE, debt, and the related income-statement / ratio fields —
and merges them into a NEW dated snapshot. Never overwrites the live dataset.
A human reviews the snapshot, then runs the Promote snapshot workflow.

Column-safe: only the fields this script actually fetched are written, and
only when the new value is real. A missing yfinance field never blanks a
last-good number. A failed ticker is left byte-for-byte as it was.

Currency guard: USD-reported symbols (currency_flag != OK) do not get
currency-denominated fields written — the 2026-07 INFY/HCLTECH bug.

Run from the repo root:
    python3 refresh_quarterly_fundamentals.py

Env vars (set by quarterly_refresh.yml):
    DEALSCOPE_INPUT_FILE   live base CSV to merge into
    DEALSCOPE_OUTPUT_DIR   where to write the dated snapshot
    DEALSCOPE_LIMIT        test-only: first N symbols
"""

from __future__ import annotations

import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "archive" / "data_pipeline_scripts"))

from enrich_v2 import fetch_roce  # noqa: E402 — established ROCE formula, not reimplemented
from src.data.paths import companies_csv_path  # noqa: E402

INPUT_FILE = os.environ.get("DEALSCOPE_INPUT_FILE", str(companies_csv_path()))
OUTPUT_DIR = Path(os.environ.get("DEALSCOPE_OUTPUT_DIR", REPO_ROOT / "data" / "snapshots"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
_STAMP = datetime.now().strftime("%Y-%m-%d")
OUTPUT_CSV = OUTPUT_DIR / f"dealscope_{_STAMP}.csv"

SLEEP_BETWEEN = 1.2
BATCH_SIZE = 100
MAX_RETRIES = 2

# yfinance info keys -> dataset columns. Ratios arrive as fractions (0.129)
# and are stored as percentages (12.9), same convention as enrich_universe_gap.py.
INFO_CORE = {
    "revenue": ("totalRevenue", False),
    "ebitda": ("ebitda", False),
    "total_debt": ("totalDebt", False),
    "net_income": ("netIncomeToCommon", False),
    "revenue_growth_pct": ("revenueGrowth", True),
    "ebitda_margin_pct": ("ebitdaMargins", True),
    "return_on_equity_pct": ("returnOnEquity", True),
    "current_ratio": ("currentRatio", False),
    "quick_ratio": ("quickRatio", False),
    "debt_to_equity": ("debtToEquity", False),
    "return_on_assets": ("returnOnAssets", False),
    "beta": ("beta", False),
    "peg_ratio": ("pegRatio", False),
    "enterprise_value": ("enterpriseValue", False),
    "total_cash": ("totalCash", False),
    "operating_cash_flow": ("operatingCashflow", False),
    "free_cash_flow": ("freeCashflow", False),
    "price_to_book": ("priceToBook", False),
    "trailing_pe": ("trailingPE", False),
}

# Never write these from a USD-reported yfinance payload.
CURRENCY_SENSITIVE = {
    "revenue",
    "ebitda",
    "total_debt",
    "net_income",
    "total_assets",
    "retained_earnings",
    "working_capital",
    "total_cash",
    "operating_cash_flow",
    "free_cash_flow",
    "enterprise_value",
}


def pct(value):
    return round(value * 100, 4) if isinstance(value, (int, float)) else None


def scalar(frame, label):
    if frame is None or getattr(frame, "empty", True) or label not in frame.index:
        return None
    latest = frame.columns[0]
    value = frame.loc[label, latest]
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_fundamentals(symbol):
    """Return a dict of dataset-column -> value. Missing keys mean 'leave last good'."""
    ticker = yf.Ticker(f"{symbol}.NS")
    info = None
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            info = ticker.info
            break
        except Exception as exc:
            last_err = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(SLEEP_BETWEEN * 2)
    if info is None:
        raise RuntimeError(f".info failed: {last_err}")

    fin_currency = info.get("financialCurrency", "INR") or "INR"
    currency_ok = fin_currency == "INR"
    out = {
        "financial_currency": fin_currency,
        "currency_flag": "OK" if currency_ok else "USD_REPORTED",
        "data_pull_date": date.today().isoformat(),
    }

    for column, (info_key, as_pct) in INFO_CORE.items():
        raw = info.get(info_key)
        value = pct(raw) if as_pct else raw
        if value is None:
            continue
        if isinstance(value, float) and (pd.isna(value) or value in (float("inf"), float("-inf"))):
            continue
        if not currency_ok and column in CURRENCY_SENSITIVE:
            continue
        out[column] = value

    # Impossible margin is a data error, not a real company. Keep last good.
    margin = out.get("ebitda_margin_pct")
    if margin is not None and abs(margin) > 100:
        out.pop("ebitda_margin_pct", None)
        out.pop("ebitda", None)

    try:
        bs = ticker.balance_sheet
    except Exception:
        bs = pd.DataFrame()

    if not getattr(bs, "empty", True) and currency_ok:
        total_assets = scalar(bs, "Total Assets")
        retained = scalar(bs, "Retained Earnings")
        current_assets = scalar(bs, "Current Assets")
        current_liab = scalar(bs, "Current Liabilities")
        if total_assets is not None:
            out["total_assets"] = total_assets
        if retained is not None:
            out["retained_earnings"] = retained
        if current_assets is not None and current_liab is not None:
            out["working_capital"] = current_assets - current_liab

    roce_value, _reason = fetch_roce(symbol)
    if roce_value not in ("", None):
        try:
            out["return_on_capital_employed_pct"] = float(roce_value)
        except (TypeError, ValueError):
            pass

    # Stamp as_of_date only when at least one core P&L / leverage field landed.
    core_landed = any(k in out for k in ("revenue", "ebitda", "total_debt", "return_on_capital_employed_pct", "ebitda_margin_pct"))
    if core_landed:
        out["as_of_date"] = date.today().isoformat()

    return out


def apply_fields(frame, symbol, fields):
    """Write only provided fields onto the matching row."""
    mask = frame["symbol"] == symbol
    for column, value in fields.items():
        if column not in frame.columns:
            frame[column] = pd.NA
        frame.loc[mask, column] = value


def main():
    print(f"Loading live dataset: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df)} companies, {len(df.columns)} columns")

    symbols = df["symbol"].tolist()
    limit = os.environ.get("DEALSCOPE_LIMIT")
    if limit:
        symbols = symbols[: int(limit)]
        print(f"DEALSCOPE_LIMIT={limit} — refreshing first {len(symbols)} of {len(df)} "
              f"(output still has all {len(df)} rows)")

    merged = df.copy()
    updated, failed = 0, 0

    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {symbol}.NS ...", end=" ", flush=True)
        try:
            fields = fetch_fundamentals(symbol)
            apply_fields(merged, symbol, fields)
            updated += 1
            print("OK")
        except Exception as exc:
            failed += 1
            print(f"ERROR: {str(exc)[:80]}")

        if i % BATCH_SIZE == 0:
            merged.to_csv(OUTPUT_CSV, index=False)
            print(f"  Saved progress ({updated} updated, {failed} failed)")

        time.sleep(SLEEP_BETWEEN)

    merged.to_csv(OUTPUT_CSV, index=False)
    print(f"\nDone: {updated} updated, {failed} failed of {len(symbols)} attempted; "
          f"{len(merged)} rows written -> {OUTPUT_CSV}")

    attempted = updated + failed
    if attempted and failed / attempted > 0.25:
        print("WARNING: more than 25% of tickers failed. Snapshot is for review only "
              "and must not be promoted until the pull is healthy.")
        # Still write the snapshot — promotion, not this job, publishes.
        sys.exit(0)

    if limit:
        print("TEST MODE: snapshot written for pipeline smoke-test. Do not promote a limited run.")


if __name__ == "__main__":
    main()
