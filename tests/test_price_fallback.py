"""NSE -> BSE fallback for the daily price pull (the "stuck 52" fix).

Run: python3 tests/test_price_fallback.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from refresh_daily_prices import fetch_price_snapshot

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


def factory(table, calls):
    """table: {'ABC.NS': (market_cap, price) | Exception}"""
    def make(symbol):
        calls.append(symbol)
        entry = table.get(symbol, (None, None))
        if isinstance(entry, Exception):
            raise entry
        return SimpleNamespace(fast_info=SimpleNamespace(market_cap=entry[0], last_price=entry[1]))
    return make


no_sleep = lambda _s: None  # noqa: E731

print("=== NSE works: BSE is never queried ===")
calls = []
r = fetch_price_snapshot("ABC", ticker_factory=factory({"ABC.NS": (1e9, 50.0)}, calls), sleep=no_sleep)
check("returns NSE values", r == (1e9, 50.0), str(r))
check("BSE not touched", calls == ["ABC.NS"], str(calls))

print("=== NSE has no market cap: BSE supplies it ===")
calls = []
r = fetch_price_snapshot("ABC", ticker_factory=factory({"ABC.NS": (None, 50.0), "ABC.BO": (2e9, 51.0)}, calls), sleep=no_sleep)
check("BSE market cap used", r[0] == 2e9, str(r))
check("NSE price preferred", r[1] == 50.0, str(r))
check("both exchanges queried in order", calls[0] == "ABC.NS" and "ABC.BO" in calls, str(calls))

print("=== NSE completely empty: BSE supplies both ===")
r = fetch_price_snapshot("ABC", ticker_factory=factory({"ABC.BO": (2e9, 51.0)}, []), sleep=no_sleep)
check("BSE values used", r == (2e9, 51.0), str(r))

print("=== Neither has a cap ===")
r = fetch_price_snapshot("ABC", ticker_factory=factory({"ABC.NS": (None, 50.0)}, []), sleep=no_sleep)
check("price-only result keeps the price, cap is None", r == (None, 50.0), str(r))
r = fetch_price_snapshot("ABC", ticker_factory=factory({}, []), sleep=no_sleep)
check("dead ticker -> (None, None)", r == (None, None), str(r))

print("=== Errors never escape ===")
r = fetch_price_snapshot("ABC", ticker_factory=factory({"ABC.NS": RuntimeError("boom"), "ABC.BO": (3e9, 9.0)}, []), sleep=no_sleep)
check("NSE exception falls through to BSE", r == (3e9, 9.0), str(r))
r = fetch_price_snapshot("ABC", ticker_factory=factory({"ABC.NS": KeyError("x"), "ABC.BO": KeyError("y")}, []), sleep=no_sleep)
check("both raising -> (None, None), no crash", r == (None, None), str(r))

print("=== A transient NSE error is retried before falling back ===")
state = {"n": 0}
def flaky(symbol):
    if symbol == "ABC.NS":
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("blip")
        return SimpleNamespace(fast_info=SimpleNamespace(market_cap=7e9, last_price=70.0))
    raise AssertionError("BSE should not be needed")
r = fetch_price_snapshot("ABC", ticker_factory=flaky, sleep=no_sleep)
check("retry succeeds on NSE", r == (7e9, 70.0), str(r))

print(f"\n{checks - failures}/{checks} checks passed")
sys.exit(1 if failures else 0)
