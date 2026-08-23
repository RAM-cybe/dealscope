"""Factor 4 is Net Debt / EBITDA (inverted), with D/E fallback.

Financial Services is excluded from Factor 4; the other three factors are
reweighted. Missing values are never treated as zero. Scores are computed
on the full universe, then filtered.

Run: python3 tests/test_scoring.py
"""

import math
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.logic.filtering import filter_companies
from src.logic.scoring import (
    DE_KIND,
    FINANCIAL_SERVICES_LABEL,
    LEVERAGE_METRIC,
    METRICS,
    MIN_POPULATED_METRICS,
    ND_EBITDA_KIND,
    PERCENTILE_COLUMNS,
    UNCLASSIFIED_LABEL,
    compute_leverage_ratio,
    score_companies,
)

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


def is_nan(value):
    return value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value)


def row(symbol, sector, **fields):
    base = {
        "symbol": symbol,
        "name": symbol,
        "sector_v2": sector,
        "revenue_growth_pct": 10.0,
        "ebitda_margin_pct": 20.0,
        "return_on_capital_employed_pct": 15.0,
        "total_debt": float("nan"),
        "total_cash": float("nan"),
        "ebitda": float("nan"),
        "debt_to_equity": float("nan"),
        "as_of_date": "2026-07-11",
        "market_cap_as_of": "2026-08-23",
    }
    base.update(fields)
    return base


def frame(rows):
    return pd.DataFrame(rows)


EQUAL_WEIGHTS = {m: 5 for m in METRICS}
BUCKET = "sector_v2"
PCTL4 = PERCENTILE_COLUMNS[LEVERAGE_METRIC]


def score(rows, weights=None):
    return score_companies(frame(rows), weights or EQUAL_WEIGHTS, bucket_col=BUCKET)


print("=== Net Debt / EBITDA ranking (inverted) ===")
nd = score(
    [
        row("LOW", "Industrials & Capital Goods", total_debt=100, total_cash=0, ebitda=100),
        row("HIGH", "Industrials & Capital Goods", total_debt=500, total_cash=0, ebitda=100),
        row("MID", "Industrials & Capital Goods", total_debt=300, total_cash=0, ebitda=100),
    ]
)
low, high, mid = (nd.set_index("symbol").loc[s] for s in ("LOW", "HIGH", "MID"))
check("LOW ND/EBITDA is 1.0", abs(low[LEVERAGE_METRIC] - 1.0) < 1e-9, f"got {low[LEVERAGE_METRIC]}")
check("HIGH ND/EBITDA is 5.0", abs(high[LEVERAGE_METRIC] - 5.0) < 1e-9, f"got {high[LEVERAGE_METRIC]}")
check("lower leverage ranks above higher", low[PCTL4] > mid[PCTL4] > high[PCTL4],
      f"LOW={low[PCTL4]} MID={mid[PCTL4]} HIGH={high[PCTL4]}")

print("\n=== Net cash ranks above net debt ===")
cash = score(
    [
        row("CASH", "Chemicals", total_debt=10, total_cash=100, ebitda=50),
        row("DEBT", "Chemicals", total_debt=100, total_cash=10, ebitda=50),
    ]
)
cash_row, debt_row = (cash.set_index("symbol").loc[s] for s in ("CASH", "DEBT"))
check("net cash ratio is negative", cash_row[LEVERAGE_METRIC] < 0, f"got {cash_row[LEVERAGE_METRIC]}")
check("net cash ranks higher than net debt", cash_row[PCTL4] > debt_row[PCTL4],
      f"CASH={cash_row[PCTL4]} DEBT={debt_row[PCTL4]}")

print("\n=== Missing cash uses gross debt / EBITDA, not invented cash=0 as a fact ===")
gross = score(
    [
        row("GROSS", "Chemicals", total_debt=200, ebitda=50),
        row("NET", "Chemicals", total_debt=200, total_cash=50, ebitda=50),
    ]
)
gross_row, net_row = (gross.set_index("symbol").loc[s] for s in ("GROSS", "NET"))
_, kinds = compute_leverage_ratio(frame([
    row("GROSS", "Chemicals", total_debt=200, ebitda=50),
    row("NET", "Chemicals", total_debt=200, total_cash=50, ebitda=50),
]), bucket_col=BUCKET)
check("missing-cash company still scored on the ND/EBITDA family", kinds.iloc[0] == ND_EBITDA_KIND, f"got {kinds.iloc[0]}")
check("gross/EBITDA = 4.0 when cash is missing", abs(gross_row[LEVERAGE_METRIC] - 4.0) < 1e-9,
      f"got {gross_row[LEVERAGE_METRIC]}")
check("known cash produces net/EBITDA = 3.0", abs(net_row[LEVERAGE_METRIC] - 3.0) < 1e-9,
      f"got {net_row[LEVERAGE_METRIC]}")
check("gross looks more leveraged than net, so ranks lower", gross_row[PCTL4] < net_row[PCTL4])

print("\n=== Missing debt is not treated as zero ===")
gap = score(
    [
        row("NODEBT", "Chemicals", ebitda=50, total_cash=10),
        row("HASDEBT", "Chemicals", total_debt=100, total_cash=0, ebitda=50),
    ]
)
nodebt = gap.set_index("symbol").loc["NODEBT"]
check("missing debt does not invent ND/EBITDA = 0", is_nan(nodebt[LEVERAGE_METRIC]),
      f"got {nodebt[LEVERAGE_METRIC]}")
check("missing debt leaves Factor 4 blank", is_nan(nodebt[PCTL4]), f"got {nodebt[PCTL4]}")

print("\n=== D/E fallback when EBITDA is missing, zero, or negative ===")
fallback_rows = [
    row("MISS", "Consumer Staples & Agri", ebitda=float("nan"), debt_to_equity=10, total_debt=999, total_cash=0),
    row("ZERO", "Consumer Staples & Agri", ebitda=0, debt_to_equity=20, total_debt=999, total_cash=0),
    row("NEG", "Consumer Staples & Agri", ebitda=-40, debt_to_equity=80, total_debt=999, total_cash=0),
    row("PRIMARY", "Consumer Staples & Agri", total_debt=100, total_cash=0, ebitda=50, debt_to_equity=1),
]
fb = score(fallback_rows)
lev, kinds = compute_leverage_ratio(frame(fallback_rows), bucket_col=BUCKET)
by_sym = pd.DataFrame({"lev": lev.values, "kind": kinds.values}, index=[r["symbol"] for r in fallback_rows])
check("missing EBITDA uses D/E", by_sym.loc["MISS", "kind"] == DE_KIND)
check("zero EBITDA uses D/E", by_sym.loc["ZERO", "kind"] == DE_KIND)
check("negative EBITDA uses D/E", by_sym.loc["NEG", "kind"] == DE_KIND)
check("usable EBITDA stays on ND/EBITDA even if D/E exists", by_sym.loc["PRIMARY", "kind"] == ND_EBITDA_KIND)
check("D/E fallback value is the D/E figure, not absolute debt", abs(by_sym.loc["MISS", "lev"] - 10) < 1e-9,
      f"got {by_sym.loc['MISS', 'lev']}")
fb_ix = fb.set_index("symbol")
check("lower D/E ranks above higher D/E in the fallback pool",
      fb_ix.loc["MISS", PCTL4] > fb_ix.loc["ZERO", PCTL4] > fb_ix.loc["NEG", PCTL4],
      f"MISS={fb_ix.loc['MISS', PCTL4]} ZERO={fb_ix.loc['ZERO', PCTL4]} NEG={fb_ix.loc['NEG', PCTL4]}")

print("\n=== ND/EBITDA and D/E are ranked in separate pools ===")
mixed_rows = [
    row("ND_LOW", "Energy & Utilities", total_debt=100, total_cash=0, ebitda=100),   # ratio 1
    row("ND_HIGH", "Energy & Utilities", total_debt=800, total_cash=0, ebitda=100),  # ratio 8
    row("DE_LOW", "Energy & Utilities", ebitda=0, debt_to_equity=5),
    row("DE_HIGH", "Energy & Utilities", ebitda=0, debt_to_equity=90),
]
mixed = score(mixed_rows).set_index("symbol")
check("ND_LOW ranks above ND_HIGH", mixed.loc["ND_LOW", PCTL4] > mixed.loc["ND_HIGH", PCTL4])
check("DE_LOW ranks above DE_HIGH", mixed.loc["DE_LOW", PCTL4] > mixed.loc["DE_HIGH", PCTL4])
# If the pools were mixed, DE_LOW (raw 5) would sit between ND_LOW (1) and
# ND_HIGH (8). Separate pools let DE_LOW still be the best of its own family.
check("D/E of 5 is not punished for sitting next to ND/EBITDA of 1",
      mixed.loc["DE_LOW", PCTL4] >= mixed.loc["ND_LOW", PCTL4])

print("\n=== Financial Services is excluded from Factor 4 ===")
fs_rows = [
    row("BANK", FINANCIAL_SERVICES_LABEL, total_debt=10, total_cash=0, ebitda=100, debt_to_equity=1),
    row("NBFC", FINANCIAL_SERVICES_LABEL, total_debt=50, total_cash=0, ebitda=100, debt_to_equity=2),
    row("IND_LOW", "Industrials & Capital Goods", total_debt=100, total_cash=0, ebitda=100),
    row("IND_HIGH", "Industrials & Capital Goods", total_debt=400, total_cash=0, ebitda=100),
]
fs = score(fs_rows).set_index("symbol")
check("bank Factor 4 is blank", is_nan(fs.loc["BANK", PCTL4]))
check("NBFC Factor 4 is blank", is_nan(fs.loc["NBFC", PCTL4]))
check("bank leverage_ratio itself is blank", is_nan(fs.loc["BANK", LEVERAGE_METRIC]))
check("FS names do not enter the industrials leverage pool",
      fs.loc["IND_LOW", PCTL4] > fs.loc["IND_HIGH", PCTL4])

print("\n=== Remaining three factors are reweighted when Factor 4 is excluded ===")
# Two FS companies, identical growth/ROCE, different margins, no Factor 4.
# Equal weights of 5. Score must equal the 3-factor blend, not a 4-factor
# blend that treated missing leverage as zero.
reweight_rows = [
    row("FS_A", FINANCIAL_SERVICES_LABEL, revenue_growth_pct=10, ebitda_margin_pct=40, return_on_capital_employed_pct=15,
        total_debt=1, total_cash=0, ebitda=100),
    row("FS_B", FINANCIAL_SERVICES_LABEL, revenue_growth_pct=10, ebitda_margin_pct=10, return_on_capital_employed_pct=15,
        total_debt=1, total_cash=0, ebitda=100),
]
rw = score(reweight_rows).set_index("symbol")
for symbol in ("FS_A", "FS_B"):
    r = rw.loc[symbol]
    present = [m for m in METRICS if not is_nan(r[PERCENTILE_COLUMNS[m]])]
    check(f"{symbol} has exactly 3 populated factors", len(present) == 3, f"got {present}")
    expected = sum(r[PERCENTILE_COLUMNS[m]] * 5 for m in present) / (5 * len(present))
    check(f"{symbol} score is the 3-factor reweight, not a 4-factor blend with a zero",
          abs(r["score"] - expected) < 1e-9, f"score={r['score']} expected={expected}")
    four_factor_if_zero = (
        r[PERCENTILE_COLUMNS["revenue_growth_pct"]] * 5
        + r[PERCENTILE_COLUMNS["ebitda_margin_pct"]] * 5
        + r[PERCENTILE_COLUMNS["return_on_capital_employed_pct"]] * 5
        + 0 * 5
    ) / 20
    check(f"{symbol} is not the (wrong) blend that treated Factor 4 as zero",
          abs(r["score"] - four_factor_if_zero) > 1e-6)

print("\n=== Legacy total_debt weight key still applies to leverage ===")
legacy = score(
    [
        row("A", "Real Estate", total_debt=50, total_cash=0, ebitda=50),
        row("B", "Real Estate", total_debt=250, total_cash=0, ebitda=50),
    ],
    weights={
        "revenue_growth_pct": 0,
        "ebitda_margin_pct": 0,
        "return_on_capital_employed_pct": 0,
        "total_debt": 10,
    },
).set_index("symbol")
check("legacy total_debt weight key drives Factor 4",
      legacy.loc["A", "score"] > legacy.loc["B", "score"])

print("\n=== Sparse scores stay blank; Unclassified is never scored ===")
sparse = score(
    [
        row("ONE", "Telecom, Media & Entertainment", revenue_growth_pct=10,
            ebitda_margin_pct=float("nan"), return_on_capital_employed_pct=float("nan")),
        row("UNCL", UNCLASSIFIED_LABEL,
            revenue_growth_pct=50, ebitda_margin_pct=50, return_on_capital_employed_pct=50,
            total_debt=10, total_cash=0, ebitda=100),
    ]
).set_index("symbol")
check("one populated metric is not a score", is_nan(sparse.loc["ONE", "score"]))
check("Unclassified score is blank", is_nan(sparse.loc["UNCL", "score"]))
check("Unclassified Factor 4 is blank", is_nan(sparse.loc["UNCL", PCTL4]))
check(f"MIN_POPULATED_METRICS is still {MIN_POPULATED_METRICS}", MIN_POPULATED_METRICS == 2)

print("\n=== Composition-order contract: filter after scoring does not change scores ===")
universe = score(
    [
        row("T1", "Technology & IT Services", revenue_growth_pct=30, total_debt=80, total_cash=0, ebitda=40),
        row("T2", "Technology & IT Services", revenue_growth_pct=5, total_debt=400, total_cash=0, ebitda=40),
        row("C1", "Chemicals", revenue_growth_pct=12, total_debt=90, total_cash=0, ebitda=30),
    ]
)
before = universe.set_index("symbol")["score"].copy()
filtered = filter_companies(
    universe,
    {"sectors": ["Technology & IT Services"], "sector_col": BUCKET},
)
after = filtered.set_index("symbol")["score"]
check("filter keeps only the named sector", set(after.index) == {"T1", "T2"})
check("T1 score is unchanged after filter", before["T1"] == after["T1"],
      f"before={before['T1']} after={after['T1']}")
check("T2 score is unchanged after filter", before["T2"] == after["T2"])

print("\n=== Live universe smoke (dates untouched, FS excluded) ===")
from src.data.loaders import load_companies

live = load_companies()
as_of_before = live["as_of_date"].copy()
mcap_before = live["market_cap_as_of"].copy() if "market_cap_as_of" in live.columns else None
live_scored = score_companies(live, EQUAL_WEIGHTS, bucket_col="sector_v2")
fs_live = live_scored[live_scored["sector_v2"] == FINANCIAL_SERVICES_LABEL]
non_fs = live_scored[live_scored["sector_v2"] != FINANCIAL_SERVICES_LABEL]
check("live FS universe is non-empty", len(fs_live) > 0, f"n={len(fs_live)}")
check("every live FS row has blank Factor 4", bool(fs_live[PCTL4].isna().all()),
      f"populated={int(fs_live[PCTL4].notna().sum())} / {len(fs_live)}")
check("some non-FS rows have a Factor 4 percentile", int(non_fs[PCTL4].notna().sum()) > 0)
check("as_of_date is untouched by scoring", live_scored["as_of_date"].equals(as_of_before))
if mcap_before is not None:
    check("market_cap_as_of is untouched by scoring", live_scored["market_cap_as_of"].equals(mcap_before))
# Kinds on the live file: both families should exist outside FS.
live_lev, live_kind = compute_leverage_ratio(live, bucket_col="sector_v2")
check("live file has ND/EBITDA rows", int((live_kind == ND_EBITDA_KIND).sum()) > 0,
      f"n={(live_kind == ND_EBITDA_KIND).sum()}")
check("live file has D/E fallback rows", int((live_kind == DE_KIND).sum()) > 0,
      f"n={(live_kind == DE_KIND).sum()}")

print(f"\n{checks - failures}/{checks} checks passed")
if failures:
    sys.exit(1)
