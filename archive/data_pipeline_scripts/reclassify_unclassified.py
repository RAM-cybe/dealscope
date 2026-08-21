"""One-off re-classification pass for the 89 companies with null sector/industry
in data/enriched/dealscope_base_2026-07-21.csv.

Investigation finding (see claude_code_prompt_backend_batch3_prep.md Task 1):
all 89 have BOTH sector and industry null -- yfinance's .info endpoint never
returned sector/industry data for these tickers at all (thinly-traded,
delisted-adjacent, or holding-company tickers). This is a genuine data-source
gap, not a mapping bug in classify_sector()/classify_sector_v2().

Retries each ticker's yfinance .info fetch (2 retries, exponential backoff --
this is a 89-ticker one-off, not a recurring batch job, so no run-lock is
needed, unlike batch_generate_rationale.py). Whatever sector/industry comes
back (if anything) is run through the SAME classify_sector()/classify_sector_v2()
functions load_companies() uses for the other 2,292 companies, so results are
consistent with the rest of the universe -- not a one-off mapping.

Never fabricates: a ticker that still returns null industry after retries
stays null and is written to data/unclassifiable_permanent.csv as a disclosed,
confirmed gap.

Run from the repo root:
    python3 reclassify_unclassified.py

Writes:
    data/reclassify_unclassified_result.csv   one row per of the 89 tickers,
        old/new sector, industry, ey_bucket, sector_v2, and outcome
    data/unclassifiable_permanent.csv         tickers still null after retries
"""

import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from src.data.sector_mapping import classify_sector
from src.data.sector_taxonomy_v2 import classify_sector_v2

BASE_CSV = REPO_ROOT / "data" / "enriched" / "dealscope_base_2026-07-21.csv"
RESULT_PATH = REPO_ROOT / "data" / "reclassify_unclassified_result.csv"
PERMANENT_GAP_PATH = REPO_ROOT / "data" / "unclassifiable_permanent.csv"

MAX_ATTEMPTS = 3  # 1 initial + 2 retries, per Task 1 spec


def fetch_sector_industry(symbol):
    """Retry-with-backoff .info fetch for sector/industry only. Returns
    (sector, industry, error) -- error is None on success (even if Yahoo
    itself has no sector/industry for this ticker, which is a real answer,
    not a fetch failure)."""
    ticker = yf.Ticker(f"{symbol}.NS")
    last_err = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            info = ticker.info
            return info.get("sector"), info.get("industry"), None
        except Exception as exc:
            last_err = str(exc).replace("\n", " ")[:180]
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(3 * (attempt + 1))  # 3s, 6s backoff
    return None, None, last_err


def main():
    df = pd.read_csv(BASE_CSV)
    targets = df[df["industry"].isna()].copy()
    print(f"Loaded {len(df)} companies, {len(targets)} with null industry to re-attempt")

    results = []
    reclassified = 0
    permanent_gaps = 0

    for i, row in enumerate(targets.itertuples(), 1):
        symbol = row.symbol
        print(f"  [{i}/{len(targets)}] {symbol} ...", end=" ", flush=True)
        sector, industry, err = fetch_sector_industry(symbol)

        if industry:
            new_ey_bucket = classify_sector(sector, industry)
            new_sector_v2 = classify_sector_v2(symbol, industry)
            idx = df.index[df["symbol"] == symbol][0]
            df.at[idx, "sector"] = sector
            df.at[idx, "industry"] = industry
            reclassified += 1
            outcome = "reclassified"
            print(f"ok -- sector={sector!r} industry={industry!r} -> ey_bucket={new_ey_bucket!r} sector_v2={new_sector_v2!r}")
            results.append({
                "symbol": symbol, "name": row.name, "outcome": outcome,
                "sector": sector, "industry": industry,
                "ey_bucket": new_ey_bucket, "sector_v2": new_sector_v2, "detail": "",
            })
        else:
            permanent_gaps += 1
            detail = err or "yfinance returned no sector/industry (empty .info fields)"
            outcome = "permanent_gap"
            print(f"still null -- {detail}")
            results.append({
                "symbol": symbol, "name": row.name, "outcome": outcome,
                "sector": None, "industry": None,
                "ey_bucket": "Unclassified", "sector_v2": "Unclassified", "detail": detail,
            })

        time.sleep(1.0)

    results_df = pd.DataFrame(results)
    results_df.to_csv(RESULT_PATH, index=False)
    print(f"\nWrote per-ticker result -> {RESULT_PATH}")

    gaps_df = results_df[results_df["outcome"] == "permanent_gap"][["symbol", "name", "detail"]].rename(
        columns={"symbol": "ticker", "detail": "reason"}
    )
    gaps_df.to_csv(PERMANENT_GAP_PATH, index=False)
    print(f"Wrote {len(gaps_df)} confirmed permanent gaps -> {PERMANENT_GAP_PATH}")

    # Save the updated base CSV under a new dated filename, following this
    # project's established versioning convention (see loaders.py history) --
    # never silently overwrite a prior snapshot in place.
    out_path = REPO_ROOT / "data" / "enriched" / "dealscope_base_2026-07-22.csv"
    df.to_csv(out_path, index=False)
    print(f"\nWrote updated base CSV ({reclassified} reclassified, {permanent_gaps} still gaps) -> {out_path}")

    print(f"\n=== Summary ===")
    print(f"Reclassified: {reclassified} / {len(targets)}")
    print(f"Confirmed permanent gaps: {permanent_gaps} / {len(targets)}")


if __name__ == "__main__":
    main()
