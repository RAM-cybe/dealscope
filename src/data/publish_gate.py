"""Machine replacement for the human review of a candidate dataset.

evaluate_gate() compares a candidate (already sanitized) against the live
dataset and answers one question: is it safe to publish without a person
looking at it? Any failure means "publish nothing" -- the site keeps serving
the last good data and the caller opens a tracking issue.

It never raises: an internal error is itself a failure (fail closed).

CLI (used by the workflows):
    python -m src.data.publish_gate <candidate.csv> [--live live.csv]
        [--repairs repairs.csv] [--summary summary.md]
Exit 0 = safe to publish, 1 = blocked. Also writes `passed=true|false` to
$GITHUB_OUTPUT when set.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.quality_checks import CRITICAL_CHECKS, run_all_checks

MAX_TICKER_LOSS_SHARE = 0.01
MAX_COVERAGE_DROP = 0.05          # absolute share of rows, per core field
MAX_REPAIRED_ROW_SHARE = 0.05
MAX_PCT_MEDIAN_SHIFT = 8.0        # percentage points
RATIO_BAND = (0.70, 1.40)         # candidate median / live median
MAX_PE_RELATIVE_SHIFT = 0.35

COVERAGE_FIELDS = [
    "revenue", "ebitda", "ebitda_margin_pct", "revenue_growth_pct",
    "return_on_capital_employed_pct", "trailing_pe", "total_debt",
    "market_cap", "net_income",
]
PCT_DRIFT_FIELDS = ["revenue_growth_pct", "ebitda_margin_pct", "return_on_capital_employed_pct"]
RATIO_DRIFT_FIELDS = ["revenue", "ebitda", "net_income", "total_debt"]


@dataclass
class GateResult:
    passed: bool
    failures: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def markdown(self):
        lines = [f"**Publish gate: {'PASS' if self.passed else 'BLOCKED'}**", ""]
        lines += [f"- BLOCKED {f}" for f in self.failures]
        lines += [f"- warning {w}" for w in self.warnings]
        lines += ["", "| metric | value |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in self.metrics.items()]
        return "\n".join(lines) + "\n"


def _num(df, col):
    return pd.to_numeric(df[col], errors="coerce") if col in df.columns else pd.Series(dtype=float)


def _median(df, col):
    s = _num(df, col).dropna()
    return float(s.median()) if len(s) else float("nan")


def _coverage(df, col):
    return float(_num(df, col).notna().mean()) if len(df) and col in df.columns else 0.0


def _symbols(df):
    return df["symbol"] if "symbol" in df.columns else pd.Series(dtype=object)


def _check_structure(cand, live, res):
    res.metrics["row_count"] = len(cand)
    res.metrics["live_row_count"] = len(live)
    missing = sorted(set(live.columns) - set(cand.columns))
    if missing:
        res.failures.append(f"schema: candidate is missing columns {missing[:8]}")
    syms = _symbols(cand)
    if len(cand) == 0:
        res.failures.append("ticker_loss: candidate has no rows")
        return
    blank = syms.isna() | (syms.astype(str).str.strip() == "")
    if blank.any():
        res.failures.append(f"blank_symbol: {int(blank.sum())} row(s) without a ticker")
    dups = syms[syms.duplicated() & ~blank]
    if len(dups):
        res.failures.append(f"duplicate_symbol: {sorted(set(dups))[:5]}")
    lost = set(_symbols(live).dropna()) - set(syms.dropna())
    share = len(lost) / max(len(live), 1)
    res.metrics["ticker_loss_share"] = round(share, 4)
    if share > MAX_TICKER_LOSS_SHARE:
        res.failures.append(f"ticker_loss: {len(lost)} of {len(live)} live tickers missing ({share:.1%})")


def _check_coverage(cand, live, res):
    for col in COVERAGE_FIELDS:
        if col not in live.columns:
            continue
        before, after = _coverage(live, col), _coverage(cand, col)
        res.metrics[f"coverage_{col}"] = f"{before:.3f}->{after:.3f}"
        if before - after > MAX_COVERAGE_DROP:
            res.failures.append(f"coverage: {col} populated {before:.1%} -> {after:.1%}")


def _check_drift(cand, live, res):
    for col in PCT_DRIFT_FIELDS:
        a, b = _median(live, col), _median(cand, col)
        if np.isnan(a) or np.isnan(b):
            continue
        res.metrics[f"median_{col}"] = f"{a:.2f}->{b:.2f}"
        if abs(b - a) > MAX_PCT_MEDIAN_SHIFT:
            res.failures.append(f"drift: median {col} moved {a:.2f} -> {b:.2f}")
    for col in RATIO_DRIFT_FIELDS:
        a, b = _median(live, col), _median(cand, col)
        if np.isnan(a) or np.isnan(b) or a <= 0:
            continue
        res.metrics[f"median_{col}"] = f"{a:.4g}->{b:.4g}"
        if not (RATIO_BAND[0] <= b / a <= RATIO_BAND[1]):
            res.failures.append(f"drift: median {col} changed x{b / a:.2f}")
    a, b = _median(live, "trailing_pe"), _median(cand, "trailing_pe")
    if not (np.isnan(a) or np.isnan(b)) and a > 0:
        res.metrics["median_trailing_pe"] = f"{a:.2f}->{b:.2f}"
        if abs(b / a - 1) > MAX_PE_RELATIVE_SHIFT:
            res.failures.append(f"drift: median trailing_pe moved {a:.2f} -> {b:.2f}")


def _check_repairs(cand, repairs, res):
    touched = repairs["symbol"].nunique() if repairs is not None and len(repairs) else 0
    share = touched / max(len(cand), 1)
    res.metrics["repaired_row_share"] = round(share, 4)
    if share > MAX_REPAIRED_ROW_SHARE:
        res.failures.append(f"repair_share: {touched} rows ({share:.1%}) needed repair; feed looks broken")


def _check_critical(cand, res):
    report = run_all_checks(cand)
    crit = report[report["check"].isin(CRITICAL_CHECKS)] if not report.empty else report
    res.metrics["critical_flags"] = len(crit)
    if len(crit):
        sample = ", ".join(f"{r.symbol}:{r.check}" for r in crit.head(5).itertuples())
        res.failures.append(f"critical_flags: {len(crit)} impossible value(s) survived repair ({sample})")


def _check_freshness(cand, live, res):
    if "as_of_date" not in cand.columns or "as_of_date" not in live.columns:
        return
    new_max, old_max = str(cand["as_of_date"].dropna().max()), str(live["as_of_date"].dropna().max())
    res.metrics["as_of_max"] = f"{old_max}->{new_max}"
    if new_max < old_max:
        res.failures.append(f"stale_candidate: newest as_of_date {new_max} is older than live {old_max}")


def evaluate_gate(candidate, live, repairs=None):
    res = GateResult(passed=False)
    steps = [
        ("structure", lambda: _check_structure(candidate, live, res)),
        ("coverage", lambda: _check_coverage(candidate, live, res)),
        ("drift", lambda: _check_drift(candidate, live, res)),
        ("repairs", lambda: _check_repairs(candidate, repairs, res)),
        ("critical", lambda: _check_critical(candidate, res)),
        ("freshness", lambda: _check_freshness(candidate, live, res)),
    ]
    for name, step in steps:
        try:
            step()
        except Exception as exc:  # noqa: BLE001 - fail closed on anything unexpected
            res.failures.append(f"internal: {name} check crashed: {exc!r}")
    res.passed = not res.failures
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("--live")
    ap.add_argument("--repairs")
    ap.add_argument("--summary")
    args = ap.parse_args(argv)

    from src.data.paths import companies_csv_path

    cand = pd.read_csv(args.candidate)
    live = pd.read_csv(args.live or companies_csv_path())
    repairs = pd.read_csv(args.repairs) if args.repairs and Path(args.repairs).exists() else None
    res = evaluate_gate(cand, live, repairs)

    text = res.markdown()
    print(text)
    if args.summary:
        Path(args.summary).write_text(text)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"passed={'true' if res.passed else 'false'}\n")
    return 0 if res.passed else 1


if __name__ == "__main__":
    sys.exit(main())
