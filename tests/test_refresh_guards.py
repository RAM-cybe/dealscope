"""Guards for daily circuit-breaker and snapshot price merge.

Run: python3 tests/test_refresh_guards.py
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from refresh_daily_prices import FAILURE_RATE_LIMIT, circuit_breaker_tripped
from promote_snapshot import merge_live_prices

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
check("healthy pull publishes", not circuit_breaker_tripped(5, 100))
check("exactly 10% still publishes", not circuit_breaker_tripped(10, 100))
check("11% trips", circuit_breaker_tripped(11, 100))
check("total outage trips", circuit_breaker_tripped(100, 100))
check("zero attempted trips", circuit_breaker_tripped(0, 0))
check("limit constant is 10%", FAILURE_RATE_LIMIT == 0.10)

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

print(f"\n{checks - failures}/{checks} checks passed")
if failures:
    sys.exit(1)
