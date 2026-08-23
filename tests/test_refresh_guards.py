"""Guards for daily circuit-breaker and snapshot price merge.

Run: python3 tests/test_refresh_guards.py
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from refresh_daily_prices import (
    FAILURE_RATE_LIMIT,
    IMPLAUSIBLE_MOVE_RATIO,
    circuit_breaker_tripped,
    classify_price_update,
    implausible_cap_move,
    is_positive_number,
)
from promote_snapshot import merge_live_prices
from src.data.paths import LIVE_MANIFEST_PATH, companies_csv_path, deals_csv_path, load_live_manifest

failures = 0
checks = 0


def check(name, cond, detail=""):
    global failures, checks
    checks += 1
    if not cond:
        failures += 1
        print(f"  FAIL  {name}{('  -- ' + detail) if detail else ''}")
    else:
        print(f"  ok    {name}")


print("=== Daily circuit breaker ===")
check("healthy pull publishes", not circuit_breaker_tripped(5, 100, updated=95))
check("exactly 10% still publishes", not circuit_breaker_tripped(10, 100, updated=90))
check("11% trips", circuit_breaker_tripped(11, 100, updated=89))
check("total outage trips", circuit_breaker_tripped(100, 100, updated=0))
check("zero attempted trips", circuit_breaker_tripped(0, 0, updated=0))
check("zero updated trips even if failed looks low", circuit_breaker_tripped(0, 10, updated=0))
check("limit constant is 10%", FAILURE_RATE_LIMIT == 0.10)
check("20x is the implausible-move line", IMPLAUSIBLE_MOVE_RATIO == 20.0)

print("\n=== Per-row price classifier (bad data never writes) ===")
check("healthy refresh is an update", classify_price_update(100, 102) == "update")
check("first-ever positive cap is an update", classify_price_update(float("nan"), 50) == "update")
check("missing fetch against a real cap is a fail", classify_price_update(100, None) == "fail")
check("zero cap against a real cap is a fail", classify_price_update(100, 0) == "fail")
check("negative cap is a fail", classify_price_update(100, -5) == "fail")
check("still-missing stays a skip", classify_price_update(float("nan"), None) == "skip")
check("zero previous is treated as no cap, skip if still missing", classify_price_update(0, None) == "skip")
check("21x jump is a fail, last good kept", classify_price_update(100, 2100) == "fail")
check("1/21x collapse is a fail", classify_price_update(2100, 100) == "fail")
check("19x jump still publishes (below the line)", classify_price_update(100, 1900) == "update")
check("is_positive_number rejects nan/0/neg", not is_positive_number(float("nan")) and not is_positive_number(0) and not is_positive_number(-1))
check("implausible_cap_move is 20x either way", implausible_cap_move(10, 201) and implausible_cap_move(201, 10))
check("normal move is not implausible", not implausible_cap_move(100, 110))

print("\n=== Promote keeps newer live prices ===")
snapshot = pd.DataFrame({
    "symbol": ["AAA", "BBB"],
    "revenue": [1, 2],
    "market_cap": [100, 200],
    "market_cap_as_of": ["2026-07-01", "2026-07-01"],
})
live = pd.DataFrame({
    "symbol": ["AAA", "BBB"],
    "market_cap": [150, 200],
    "market_cap_as_of": ["2026-08-21", "2026-07-01"],
})
merged = merge_live_prices(snapshot, live)
aaa = merged.loc[merged["symbol"] == "AAA"].iloc[0]
bbb = merged.loc[merged["symbol"] == "BBB"].iloc[0]
check("AAA keeps live cap", aaa["market_cap"] == 150)
check("AAA keeps live as-of", str(aaa["market_cap_as_of"]) == "2026-08-21")
check("BBB snapshot cap unchanged when dates tie/older", bbb["market_cap"] == 200)
check("fundamentals column survives", aaa["revenue"] == 1)

print("\n=== Live dataset pointer ===")
manifest = load_live_manifest()
check("live.json is readable", LIVE_MANIFEST_PATH.is_file())
check("live.json names companies", "companies" in manifest and "deals" in manifest)
check("companies CSV exists", companies_csv_path().is_file())
check("deals CSV exists", deals_csv_path().is_file())
check("companies path is under data/", str(manifest["companies"]).startswith("data/"))

print(f"\n{checks - failures}/{checks} checks passed")
if failures:
    sys.exit(1)
