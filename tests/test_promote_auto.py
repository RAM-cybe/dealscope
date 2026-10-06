"""Automatic promotion: sanitize + gate decide, not a person.

Run: python3 tests/test_promote_auto.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from promote_snapshot import prepare_candidate

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


SNAP = REPO_ROOT / "data" / "snapshots" / "dealscope_2026-10-01.csv"
LIVE = REPO_ROOT / "data" / "enriched" / "dealscope_base_2026-07-22.csv"
snap = pd.read_csv(SNAP)
live = pd.read_csv(LIVE)

print("=== Golden: the real 2026-10-01 snapshot (56 critical flags) ===")
cleaned, repairs, gate = prepare_candidate(snap, live)
check("promoted automatically", gate.passed, str(gate.failures))
check("zero critical flags remain", gate.metrics.get("critical_flags") == 0)
check("every row kept", len(cleaned) == len(snap))
check("repair report is non-empty and logged per cell", len(repairs) > 0)
check("repaired rows under the 5% limit", gate.metrics["repaired_row_share"] < 0.05)
check("no holding above 100%", cleaned["insider_holding_pct"].max() <= 100)
check("no |beta| above 10", cleaned["beta"].abs().max() <= 10)
check("input snapshot untouched", snap.equals(pd.read_csv(SNAP)))

print("=== Live prices newer than the snapshot are kept ===")
live_newer = live.copy()
live_newer["market_cap_as_of"] = "2026-12-31"
live_newer["market_cap"] = live_newer["market_cap"] * 2
cleaned2, _, _ = prepare_candidate(snap, live_newer)
both = cleaned2.dropna(subset=["market_cap"]).merge(
    live_newer[["symbol", "market_cap"]], on="symbol", suffixes=("", "_live"))
check("newer live market caps win over snapshot caps",
      (both["market_cap"] == both["market_cap_live"]).mean() > 0.95)

print("=== A broken snapshot is blocked, not published ===")
half = snap.iloc[: len(snap) // 2].copy()
_, _, g = prepare_candidate(half, live)
check("half the universe -> blocked", not g.passed)
wiped = snap.copy()
wiped["revenue"] = np.nan
wiped["ebitda"] = np.nan
_, _, g = prepare_candidate(wiped, live)
check("wiped revenue/ebitda -> blocked", not g.passed)
garbage = snap.copy()
garbage["beta"] = 500.0
garbage["current_ratio"] = -3.0
garbage["insider_holding_pct"] = 250.0
_, rep, g = prepare_candidate(garbage, live)
check("garbage in many columns -> blocked (feed is broken, not just a few rows)",
      not g.passed and "repair_share" in {f.split(":")[0] for f in g.failures})

print(f"\n{checks - failures}/{checks} checks passed")
sys.exit(1 if failures else 0)
