"""Daily lightweight refresh: market cap and share price only, for all ~2,046
companies. NOT a full fundamentals pull -- revenue, EBITDA, margins, ROCE,
debt, promoter pledge, etc. only change when a company reports (quarterly),
so re-pulling those daily would burn yfinance free-tier quota for numbers
that haven't moved and risk getting the pipeline's IP throttled or blocked.

This script only overwrites market_cap and a same-day share price snapshot,
on top of the current committed dataset (whatever quarterly_refresh.yml last
merged) -- every other field passes through untouched.

Run from the repo root:
    python3 refresh_daily_prices.py

Writes IN PLACE to the companies CSV named in data/live.json. The quarterly
job writes a NEW dated file under data/snapshots/ and a human promotes it
(which updates live.json). Daily refresh cannot wait on that step.

Intended to run on a daily GitHub Actions schedule and open a small,
low-risk auto-mergeable PR (unlike the quarterly fundamentals refresh, which
always requires human review) -- see .github/workflows/daily_price_refresh.yml.
"""

import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.data.paths import companies_csv_path

# Deliberately conservative pacing -- this runs every day (365x/year vs. the
# quarterly job's 4x/year), so being gentle with yfinance matters far more
# here. A slow, reliable daily job beats a fast one that gets the pipeline's
# IP rate-limited and breaks the quarterly fundamentals pull too.
REQUEST_DELAY_SECONDS = 0.6
MAX_RETRIES = 2
# If more than this share of companies that already had a market cap fail
# to refresh, do not write anything — keep the last good file as-is.
FAILURE_RATE_LIMIT = 0.10


def circuit_breaker_tripped(failed, attempted):
    """True when the pull is too broken to publish."""
    if attempted <= 0:
        return True
    return (failed / attempted) > FAILURE_RATE_LIMIT


def fetch_price_snapshot(symbol):
    """Return (market_cap, price) for one NSE symbol via yfinance, or
    (None, None) on any failure -- a single bad ticker must never abort the
    whole run."""
    import yfinance as yf

    for attempt in range(MAX_RETRIES):
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            fast_info = ticker.fast_info
            market_cap = getattr(fast_info, "market_cap", None)
            price = getattr(fast_info, "last_price", None)
            if market_cap or price:
                return market_cap, price
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY_SECONDS * 2)
                continue
    return None, None


def main():
    limit = None
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        limit = int(sys.argv[1])

    live_path = companies_csv_path()
    df = pd.read_csv(live_path)
    symbols = df["symbol"].tolist()
    if limit:
        symbols = symbols[:limit]
        print(f"TEST MODE: limiting to first {limit} symbols")

    updated, failed, skipped = 0, 0, 0
    today_iso = date.today().isoformat()
    if "market_cap_as_of" not in df.columns:
        df["market_cap_as_of"] = pd.NA

    for i, symbol in enumerate(symbols, 1):
        market_cap, price = fetch_price_snapshot(symbol)
        row_mask = df["symbol"] == symbol
        previous = df.loc[row_mask, "market_cap"].iloc[0]

        if market_cap is not None:
            df.loc[row_mask, "market_cap"] = market_cap
            df.loc[row_mask, "market_cap_as_of"] = today_iso
            updated += 1
        elif pd.notna(previous):
            # Had a real cap yesterday, didn't get one today — keep last good,
            # do not stamp today's date on a number we did not refresh.
            failed += 1
        else:
            skipped += 1

        if i % 100 == 0:
            print(f"  {i}/{len(symbols)} processed ({updated} updated, {failed} failed, {skipped} no-cap)")

        time.sleep(REQUEST_DELAY_SECONDS)

    attempted = updated + failed
    print(f"\nDone: {updated} updated, {failed} failed, {skipped} already-uncapped "
          f"out of {len(symbols)} (attempted={attempted})")

    if circuit_breaker_tripped(failed, attempted):
        rate = (failed / attempted) if attempted else 1.0
        print(
            f"CIRCUIT BREAKER: {failed}/{attempted} previously-capped tickers failed "
            f"({rate:.0%} > {FAILURE_RATE_LIMIT:.0%}). "
            "Not writing. Last good dataset is unchanged."
        )
        sys.exit(1)

    if limit:
        print("TEST MODE: not writing the live companies CSV (a limited run only "
              "refreshed a subset — stamping market_cap_as_of over the full file "
              "would misrepresent untouched rows as freshly pulled). Re-run without "
              "a limit for a real refresh.")
        return

    df.to_csv(live_path, index=False)
    print(f"Wrote {live_path}")
    print(f"market_cap_as_of stamped only on the {updated} rows actually refreshed today.")


if __name__ == "__main__":
    main()
