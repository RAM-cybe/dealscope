"""Implied equity is never published as a negative number.

Run: python3 tests/test_valuation.py
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.logic.valuation import valuation_range

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


def frame(rows):
    return pd.DataFrame(rows)


print("=== Debt overhang floors implied equity at 0 ===")
# Two healthy peers set the multiple. A third name has huge debt so
# ebitda * multiple - debt is negative.
rows = [
    {"symbol": "PEER1", "sector_v2": "Telecom, Media & Entertainment", "market_cap": 100, "total_debt": 10, "ebitda": 20, "net_income": 10},
    {"symbol": "PEER2", "sector_v2": "Telecom, Media & Entertainment", "market_cap": 120, "total_debt": 10, "ebitda": 20, "net_income": 10},
    {"symbol": "PEER3", "sector_v2": "Telecom, Media & Entertainment", "market_cap": 110, "total_debt": 10, "ebitda": 20, "net_income": 10},
    {"symbol": "HEAVY", "sector_v2": "Telecom, Media & Entertainment", "market_cap": 50, "total_debt": 10_000, "ebitda": 20, "net_income": 5},
]
valued = valuation_range(frame(rows), bucket_col="sector_v2").set_index("symbol")
heavy = valued.loc["HEAVY"]
check("overhang low is not negative", heavy["ev_ebitda_low"] >= 0, f"got {heavy['ev_ebitda_low']}")
check("overhang high is not negative", heavy["ev_ebitda_high"] >= 0, f"got {heavy['ev_ebitda_high']}")
check("note names debt overhang", "debt overhang" in str(heavy["valuation_note"]), f"got {heavy['valuation_note']}")

print("\n=== Healthy names are untouched ===")
peer = valued.loc["PEER1"]
check("healthy EV range stays positive and not floored to zero", peer["ev_ebitda_low"] > 0)
check("healthy note is empty", str(peer["valuation_note"]) == "")

print("\n=== Live universe has no negative implied equity ===")
from src.data.loaders import load_companies
from src.logic.scoring import score_companies, METRICS

live = load_companies()
scored = score_companies(live, {m: 5 for m in METRICS}, bucket_col="sector_v2")
live_valued = valuation_range(scored, bucket_col="sector_v2")
neg = live_valued[
    (live_valued["ev_ebitda_low"] < 0)
    | (live_valued["ev_ebitda_high"] < 0)
    | (live_valued["pe_implied_low"] < 0)
    | (live_valued["pe_implied_high"] < 0)
]
check("no negative EV/EBITDA or P/E implied equity", len(neg) == 0, f"n={len(neg)}")
overhang_n = live_valued["valuation_note"].astype(str).str.contains("debt overhang").sum()
check("some live names are flagged as debt overhang", overhang_n > 0, f"n={overhang_n}")

print(f"\n{checks - failures}/{checks} checks passed")
if failures:
    sys.exit(1)
