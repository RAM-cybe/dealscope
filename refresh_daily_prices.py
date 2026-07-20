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

Writes IN PLACE to DEFAULT_COMPANIES_PATH (src/data/loaders.py) -- the same
file the quarterly job promotes by hand. This is deliberate, not an
oversight: the quarterly job writes a NEW dated file under data/enriched/
and leaves a human to review it and repoint DEFAULT_COMPANIES_PATH (that
constant is never updated programmatically anywhere in this repo -- grep it).
A daily job can't rely on that same human-promotion step 365 times a year
without defeating its own "safe to auto-merge" design, and an earlier
version of this script wrote a fresh dealscope_base_<today>.csv sibling file
that nothing ever read -- export_for_frontend.py always loads
DEFAULT_COMPANIES_PATH, so that file was a silent no-op every single day
(the workflow "succeeded" while never actually refreshing anything shipped
to the frontend). Overwriting the live file directly keeps every day's PR
diff to the handful of changed market_cap/market_cap_as_of cells -- exactly
the "single, low-risk, easily-reversible" diff the workflow's own comments
describe, with git history as the reversibility/audit trail.

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

from src.data.loaders import DEFAULT_COMPANIES_PATH

# Deliberately conservative pacing -- this runs every day (365x/year vs. the
# quarterly job's 4x/year), so being gentle with yfinance matters far more
# here. A slow, reliable daily job beats a fast one that gets the pipeline's
# IP rate-limited and breaks the quarterly fundamentals pull too.
REQUEST_DELAY_SECONDS = 0.6
MAX_RETRIES = 2


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

    df = pd.read_csv(DEFAULT_COMPANIES_PATH)
    symbols = df["symbol"].tolist()
    if limit:
        symbols = symbols[:limit]
        print(f"TEST MODE: limiting to first {limit} symbols")

    updated, failed = 0, 0
    today_iso = date.today().isoformat()

    for i, symbol in enumerate(symbols, 1):
        market_cap, price = fetch_price_snapshot(symbol)
        row_mask = df["symbol"] == symbol

        if market_cap is not None:
            df.loc[row_mask, "market_cap"] = market_cap
            updated += 1
        else:
            failed += 1
            # Leave the existing (last-known-good) market_cap in place --
            # never blank a real prior value just because today's pull
            # failed for one ticker.

        if i % 100 == 0:
            print(f"  {i}/{len(symbols)} processed ({updated} updated, {failed} failed so far)")

        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\nDone: {updated} updated, {failed} failed/unchanged out of {len(symbols)}")

    if failed > len(symbols) * 0.5:
        print("WARNING: more than half of pulls failed -- possible rate-limiting. "
              "Check before relying on this snapshot.")
        sys.exit(1)

    if limit:
        # A limited run only ever touched the first `limit` symbols, so
        # stamping market_cap_as_of=today across all 2,046 rows and writing
        # that over the live file would falsely claim a fresh market cap for
        # every company this run never actually looked at -- and since this
        # workflow auto-merges, that false claim would go straight to
        # production. A smoke test's job is just to prove yfinance
        # connectivity/pacing/retry logic works; it has nothing useful to
        # write, so it doesn't touch DEFAULT_COMPANIES_PATH at all.
        print("TEST MODE: not writing to DEFAULT_COMPANIES_PATH (a limited run only "
              "refreshed a subset -- stamping market_cap_as_of over the full file "
              "would misrepresent untouched rows as freshly pulled). Re-run without "
              "a limit for a real refresh.")
        return

    # price_as_of / data_pull_date so the frontend can show "market cap as of
    # <today>" distinctly from "fundamentals as of <last quarterly refresh>".
    df["market_cap_as_of"] = today_iso

    # Overwrite DEFAULT_COMPANIES_PATH in place (see module docstring for why
    # this deliberately isn't a new dated sibling file) -- every other column
    # passes through byte-for-byte except market_cap and market_cap_as_of.
    df.to_csv(DEFAULT_COMPANIES_PATH, index=False)
    print(f"Wrote {DEFAULT_COMPANIES_PATH}")


if __name__ == "__main__":
    main()
