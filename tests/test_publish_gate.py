"""Publish gate: a candidate dataset only goes live if every check passes.

Run: python3 tests/test_publish_gate.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.data.publish_gate import evaluate_gate
from src.data.sanitize import REPAIR_COLUMNS

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


def make_live(n=400, seed=7):
    rng = np.random.default_rng(seed)
    rev = rng.lognormal(22, 1.2, n)
    margin = rng.normal(11, 8, n)
    return pd.DataFrame({
        "symbol": [f"SYM{i:04d}" for i in range(n)],
        "name": [f"Company {i}" for i in range(n)],
        "sector": rng.choice(["A", "B", "C"], n),
        "revenue": rev,
        "ebitda": rev * margin / 100,
        "ebitda_margin_pct": margin,
        "revenue_growth_pct": rng.normal(12, 10, n),
        "return_on_capital_employed_pct": rng.normal(12, 8, n),
        "trailing_pe": rng.lognormal(3.2, 0.5, n),
        "total_debt": rev * rng.uniform(0, 0.6, n),
        "market_cap": rev * rng.uniform(0.5, 4, n),
        "net_income": rev * rng.uniform(0.01, 0.12, n),
        "as_of_date": "2026-07-11",
    })


def no_repairs():
    return pd.DataFrame(columns=REPAIR_COLUMNS)


def codes(result):
    return {f.split(":")[0] for f in result.failures}


live = make_live()

print("=== A healthy quarterly update passes ===")
cand = live.copy()
cand["revenue"] = cand["revenue"] * 1.05
cand["ebitda"] = cand["ebitda"] * 1.05
cand["revenue_growth_pct"] = cand["revenue_growth_pct"] + 3
cand["as_of_date"] = "2026-10-01"
res = evaluate_gate(cand, live, no_repairs())
check("passes", res.passed, str(res.failures))
check("no failures listed", res.failures == [])
check("metrics are reported", "row_count" in res.metrics and "repaired_row_share" in res.metrics)

print("=== Structural failures ===")
res = evaluate_gate(live.iloc[:200].copy(), live, no_repairs())
check("half the rows missing is blocked", not res.passed and "ticker_loss" in codes(res))
res = evaluate_gate(live.iloc[: int(len(live) * 0.995)].copy(), live, no_repairs())
check("losing <1% of tickers is tolerated", "ticker_loss" not in codes(res))
res = evaluate_gate(live.drop(columns=["ebitda"]), live, no_repairs())
check("a dropped column is blocked", "schema" in codes(res))
dup = pd.concat([live, live.iloc[:3]])
res = evaluate_gate(dup, live, no_repairs())
check("duplicate tickers are blocked", "duplicate_symbol" in codes(res))
blank = live.copy(); blank.loc[0, "symbol"] = None
res = evaluate_gate(blank, live, no_repairs())
check("blank ticker is blocked", "duplicate_symbol" in codes(res) or "blank_symbol" in codes(res))
res = evaluate_gate(live.iloc[0:0].copy(), live, no_repairs())
check("empty candidate is blocked", not res.passed)

print("=== Coverage (NaN flood) ===")
flood = live.copy()
flood.loc[flood.sample(frac=0.30, random_state=1).index, "revenue"] = np.nan
res = evaluate_gate(flood, live, no_repairs())
check("30% of revenue wiped is blocked", "coverage" in codes(res))
small = live.copy()
small.loc[small.sample(frac=0.03, random_state=1).index, "revenue"] = np.nan
res = evaluate_gate(small, live, no_repairs())
check("a 3-point coverage dip is tolerated", "coverage" not in codes(res))

print("=== Distribution drift ===")
drift = live.copy(); drift["ebitda_margin_pct"] = drift["ebitda_margin_pct"] + 20
res = evaluate_gate(drift, live, no_repairs())
check("median margin +20 pts is blocked", "drift" in codes(res))
drift = live.copy(); drift["revenue"] = drift["revenue"] * 1000
res = evaluate_gate(drift, live, no_repairs())
check("revenue x1000 (unit bug) is blocked", "drift" in codes(res))
drift = live.copy(); drift["trailing_pe"] = drift["trailing_pe"] * 3
res = evaluate_gate(drift, live, no_repairs())
check("P/E x3 is blocked", "drift" in codes(res))

print("=== Repairs and critical flags ===")
many = pd.DataFrame({"symbol": live["symbol"].iloc[:60], "field": "beta", "before": 99.0,
                     "after": np.nan, "reason": "x", "source": "null"})
res = evaluate_gate(live.copy(), live, many)
check("15% of rows needing repair is blocked", "repair_share" in codes(res))
few = many.iloc[:8]
res = evaluate_gate(live.copy(), live, few)
check("2% of rows repaired is tolerated", "repair_share" not in codes(res))
crit = live.copy(); crit.loc[3, "revenue"] = -5.0
res = evaluate_gate(crit, live, no_repairs())
check("a critical flag surviving sanitation blocks", "critical_flags" in codes(res))

print("=== Freshness ===")
old = live.copy(); old["as_of_date"] = "2026-01-01"
res = evaluate_gate(old, live, no_repairs())
check("candidate older than live is blocked", "stale_candidate" in codes(res))

print("=== Never raises ===")
for label, bad in [("all-NaN", live.assign(revenue=np.nan, ebitda=np.nan)),
                   ("strings", live.assign(revenue="abc")),
                   ("single row", live.iloc[:1])]:
    try:
        r = evaluate_gate(bad, live, no_repairs())
        check(f"{label}: returns a result instead of raising", r.passed is False)
    except Exception as exc:  # noqa: BLE001
        check(f"{label}: returns a result instead of raising", False, repr(exc))

print(f"\n{checks - failures}/{checks} checks passed")
sys.exit(1 if failures else 0)
