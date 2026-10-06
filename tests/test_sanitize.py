"""Sanitizer: deterministic repair of impossible values, never inventing numbers.

Run: python3 tests/test_sanitize.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.data.sanitize import REPAIR_COLUMNS, sanitize

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


def row(symbol="AAA", **kw):
    base = {
        "symbol": symbol, "name": symbol + " Ltd",
        "revenue": 1_000_000_000.0, "ebitda": 200_000_000.0,
        "ebitda_margin_pct": 20.0, "revenue_growth_pct": 10.0,
        "total_debt": 50_000_000.0, "market_cap": 5_000_000_000.0,
        "insider_holding_pct": 55.0, "promoter_pledge_pct": 0.0,
        "current_ratio": 1.8, "quick_ratio": 1.1, "beta": 0.9,
    }
    base.update(kw)
    return base


def frame(*rows):
    return pd.DataFrame(list(rows))


def val(df, symbol, col):
    return df.loc[df["symbol"] == symbol, col].iloc[0]


print("=== Clean data is untouched ===")
df = frame(row("A"), row("B", beta=-1.2, ebitda_margin_pct=-40.0))
out, repairs = sanitize(df)
check("no repairs on valid data", repairs.empty)
check("values identical", out.equals(df))
check("repairs frame has the documented columns", list(repairs.columns) == REPAIR_COLUMNS)

print("=== Input is never mutated, rows never added or removed ===")
df = frame(row("A", insider_holding_pct=133.3), row("B"))
snapshot = df.copy(deep=True)
out, repairs = sanitize(df)
check("input untouched", df.equals(snapshot))
check("same row count and order", list(out["symbol"]) == ["A", "B"])

print("=== Promoter holding / pledge must be 0..100 ===")
df = frame(row("GLOBE", insider_holding_pct=133.324), row("P", promoter_pledge_pct=104.0),
           row("EDGE", insider_holding_pct=100.0, promoter_pledge_pct=0.0))
out, repairs = sanitize(df)
check("holding 133% with no live fallback -> null", pd.isna(val(out, "GLOBE", "insider_holding_pct")))
check("pledge 104% -> null", pd.isna(val(out, "P", "promoter_pledge_pct")))
check("exactly 100% is legal", val(out, "EDGE", "insider_holding_pct") == 100.0)
check("repair logged with before value", float(repairs[repairs.symbol == "GLOBE"].iloc[0]["before"]) == 133.324)
check("repair source is null", repairs[repairs.symbol == "GLOBE"].iloc[0]["source"] == "null")

print("=== Last-good live value is preferred over null ===")
live = frame(row("GLOBE", insider_holding_pct=61.2))
df = frame(row("GLOBE", insider_holding_pct=133.324))
out, repairs = sanitize(df, live=live)
check("falls back to live value", val(out, "GLOBE", "insider_holding_pct") == 61.2)
check("source recorded as live", repairs.iloc[0]["source"] == "live")
bad_live = frame(row("GLOBE", insider_holding_pct=140.0))
out, _ = sanitize(df, live=bad_live)
check("an invalid live value is never used as fallback", pd.isna(val(out, "GLOBE", "insider_holding_pct")))

print("=== Beta, current ratio, quick ratio ===")
df = frame(row("B1", beta=-20934.23), row("B2", beta=10.0), row("R1", current_ratio=2990.43),
           row("R2", quick_ratio=-0.5), row("R3", current_ratio=100.0))
out, _ = sanitize(df)
check("beta -20,934 -> null", pd.isna(val(out, "B1", "beta")))
check("beta 10 is the inclusive limit", val(out, "B2", "beta") == 10.0)
check("current ratio 2,990 -> null", pd.isna(val(out, "R1", "current_ratio")))
check("negative quick ratio -> null", pd.isna(val(out, "R2", "quick_ratio")))
check("current ratio 100 kept", val(out, "R3", "current_ratio") == 100.0)

print("=== Negative revenue repairs its dependent fields too ===")
df = frame(row("NEG", revenue=-105_422_000.0, ebitda=-171_291_744.0,
               ebitda_margin_pct=0.0, revenue_growth_pct=-30.0))
out, repairs = sanitize(df)
check("negative revenue -> null", pd.isna(val(out, "NEG", "revenue")))
check("derived margin nulled (cannot trust it)", pd.isna(val(out, "NEG", "ebitda_margin_pct")))
check("derived growth nulled", pd.isna(val(out, "NEG", "revenue_growth_pct")))
check("independent ebitda kept", val(out, "NEG", "ebitda") == -171_291_744.0)
live = frame(row("NEG", revenue=900_000_000.0, ebitda=100_000_000.0, ebitda_margin_pct=11.1, revenue_growth_pct=4.0))
out, _ = sanitize(df, live=live)
check("group reverts together to a consistent live snapshot",
      (val(out, "NEG", "revenue"), val(out, "NEG", "ebitda"), val(out, "NEG", "ebitda_margin_pct"))
      == (900_000_000.0, 100_000_000.0, 11.1))

print("=== Margin outside +/-300 ===")
df = frame(row("BOH", revenue=20_000.0, ebitda=-17_378_500.0, ebitda_margin_pct=-92980.0),
           row("OK", ebitda_margin_pct=-299.0))
out, _ = sanitize(df)
check("-92,980% -> null, not clamped (no invented number)", pd.isna(val(out, "BOH", "ebitda_margin_pct")))
check("-299% kept", val(out, "OK", "ebitda_margin_pct") == -299.0)

print("=== Zero margin with material ebitda is recomputed ===")
df = frame(row("Z1", revenue=1_000_000_000.0, ebitda=150_000_000.0, ebitda_margin_pct=0.0),
           row("Z2", revenue=np.nan, ebitda=150_000_000.0, ebitda_margin_pct=0.0),
           row("Z3", revenue=1_000_000_000.0, ebitda=50_000.0, ebitda_margin_pct=0.0),
           row("Z4", revenue=8_550_000.0, ebitda=-290_065_760.0, ebitda_margin_pct=0.0))
out, repairs = sanitize(df)
check("recomputed from revenue", abs(val(out, "Z1", "ebitda_margin_pct") - 15.0) < 1e-9)
check("source recorded as recomputed", repairs[repairs.symbol == "Z1"].iloc[0]["source"] == "recomputed")
check("no revenue -> null", pd.isna(val(out, "Z2", "ebitda_margin_pct")))
check("noise-level ebitda keeps legitimate 0%", val(out, "Z3", "ebitda_margin_pct") == 0.0)
check("recompute that lands outside +/-300 -> null", pd.isna(val(out, "Z4", "ebitda_margin_pct")))

print("=== Negative debt / market cap ===")
df = frame(row("D", total_debt=-5.0), row("M", market_cap=-1.0))
out, _ = sanitize(df)
check("negative debt -> null", pd.isna(val(out, "D", "total_debt")))
check("negative market cap -> null", pd.isna(val(out, "M", "market_cap")))

print("=== Robustness ===")
out, repairs = sanitize(pd.DataFrame(columns=["symbol"]))
check("empty frame ok", out.empty and repairs.empty)
df = frame(row("A", beta=np.nan, current_ratio=None))
out, repairs = sanitize(df)
check("NaN / None are not 'invalid'", repairs.empty)
df = frame(row("A")).drop(columns=["beta", "quick_ratio"])
out, repairs = sanitize(df)
check("missing columns are skipped, not crashed", repairs.empty and "beta" not in out.columns)
df = frame(row("A", insider_holding_pct=133.0, beta=-500.0, revenue=-1.0))
once, r1 = sanitize(df)
twice, r2 = sanitize(once)
check("idempotent: second pass repairs nothing", r2.empty)
check("idempotent: second pass changes nothing", once.equals(twice))
df = frame(row("A", insider_holding_pct="n/a"))
out, repairs = sanitize(df)
check("non-numeric junk in a numeric column is repaired, not a crash", pd.isna(val(out, "A", "insider_holding_pct")))

print(f"\n{checks - failures}/{checks} checks passed")
sys.exit(1 if failures else 0)
