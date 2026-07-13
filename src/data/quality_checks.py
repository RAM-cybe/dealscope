"""Automated data-quality checks for the company dataset (Phase 2, Module E).

A repeatable, reusable check -- meant to run after every future refresh, not
as a one-off manual query. Outputs a flagged-rows report; per this project's
core rule ("never fabricate or guess a data value"), nothing here is
auto-fixed. A human reviews every flag and decides what (if anything) to
change -- exactly the discipline that already caught the currency-
contamination bug (commit 4743a27) and the negative-revenue bug (commit
1da4104), both fixed by hand after a human reviewed the specific evidence.

Usage:
    python -m src.data.quality_checks [path_to_csv]
    (defaults to the live DEFAULT_COMPANIES_PATH if no path given)
"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------------
# Thresholds (each documented -- none of these are arbitrary)
# ----------------------------------------------------------------------------

# EBITDA margin / ROCE can legitimately be extreme when the denominator
# (revenue / capital employed) is very small relative to the numerator --
# already confirmed twice in this project's history (BOHRAIND -92,980% and
# SPARC +4,083.7% margin; SUPREMEINF +2,150.6% and KOHINOOR +811.3% ROCE).
# These thresholds are deliberately wide: they flag a value for a SECOND
# human look, they do not claim the value is wrong. A real, distressed or
# near-zero-denominator company can legitimately clear them.
EBITDA_MARGIN_ABS_LIMIT = 300.0  # percentage points
ROCE_ABS_LIMIT = 200.0  # percentage points

# ebitda_margin_pct vs. a fresh ebitda/revenue recomputation: flag if they
# disagree by more than this many percentage points. Catches a stored margin
# that no longer matches its own inputs (stale field, mismatched pull, etc).
MARGIN_RECOMPUTE_TOLERANCE = 5.0

# Per the roadmap, fundamentals refresh on a quarterly cadence. Flag data
# older than this many days as due (or overdue) for its next refresh --
# this project isn't on an automated refresh yet, so "stale" here just means
# "worth checking whether a re-pull is warranted," not "known wrong."
STALE_DATA_MAX_AGE_DAYS = 100

# ebitda_margin_pct stored at ~0 while ebitda is a real, materially non-zero
# value is mathematically impossible for any finite revenue -- confirmed
# 14/14 times a real error (2026-07-13, commit 38103f8), never a legitimate
# edge case. Uses an epsilon rather than exact equality to 0.0 because a bug
# can just as easily produce a near-zero-but-not-exactly-0.0 stored value
# (float rounding, a bad intermediate computation) that's equally
# inconsistent with a materially non-zero ebitda -- exact-equality would
# miss those the same way it missed nothing here but would elsewhere.
ZERO_MARGIN_EPSILON = 0.005  # percentage points -- rounds to "0.00%" at 2dp
# Floor below which ebitda is treated as noise-level rather than a genuine
# non-zero figure, so a company with real near-zero ebitda (legitimately
# producing a near-zero margin) isn't false-flagged. INR units, so this is
# Rs 1 lakh -- far below any populated ebitda value seen in this dataset.
EBITDA_MATERIALITY_FLOOR = 100_000


def _flag(flags, row, check, detail):
    flags.append({
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "check": check,
        "detail": detail,
    })


def check_range_violations(df):
    """Values that are mathematically impossible for a real company, or
    extreme enough to warrant a second human look (see thresholds above)."""
    flags = []
    for _, row in df.iterrows():
        revenue = row.get("revenue")
        if pd.notna(revenue) and revenue < 0:
            _flag(flags, row, "negative_revenue", f"revenue={revenue:,.0f} (revenue cannot be negative)")

        total_debt = row.get("total_debt")
        if pd.notna(total_debt) and total_debt < 0:
            _flag(flags, row, "negative_total_debt", f"total_debt={total_debt:,.0f} (debt cannot be negative)")

        market_cap = row.get("market_cap")
        if pd.notna(market_cap) and market_cap < 0:
            _flag(flags, row, "negative_market_cap", f"market_cap={market_cap:,.0f} (market cap cannot be negative)")

        for ratio_field in ("current_ratio", "quick_ratio"):
            ratio_val = row.get(ratio_field)
            if pd.notna(ratio_val) and ratio_val < 0:
                _flag(flags, row, f"negative_{ratio_field}", f"{ratio_field}={ratio_val:.4g} (a ratio of two positive quantities cannot be negative)")

        margin = row.get("ebitda_margin_pct")
        if pd.notna(margin) and abs(margin) > EBITDA_MARGIN_ABS_LIMIT:
            _flag(flags, row, "extreme_ebitda_margin", f"ebitda_margin_pct={margin:,.2f}% (outside +/-{EBITDA_MARGIN_ABS_LIMIT:.0f}%, needs a human look -- may be a real near-zero-revenue case, see BOHRAIND/SPARC precedent)")

        roce = row.get("return_on_capital_employed_pct")
        if pd.notna(roce) and abs(roce) > ROCE_ABS_LIMIT:
            _flag(flags, row, "extreme_roce", f"return_on_capital_employed_pct={roce:,.2f}% (outside +/-{ROCE_ABS_LIMIT:.0f}%, needs a human look -- may be a real small-capital-base case, see SUPREMEINF/KOHINOOR precedent)")

    return flags


def check_cross_field_consistency(df):
    """Fields that should agree with each other, or a population pattern
    that looks like a partial/failed pull rather than genuine absence."""
    flags = []
    for _, row in df.iterrows():
        ebitda = row.get("ebitda")
        revenue = row.get("revenue")
        stored_margin = row.get("ebitda_margin_pct")
        if pd.notna(ebitda) and pd.notna(revenue) and pd.notna(stored_margin) and revenue != 0:
            recomputed_margin = ebitda / revenue * 100
            diff = abs(recomputed_margin - stored_margin)
            if diff > MARGIN_RECOMPUTE_TOLERANCE:
                _flag(
                    flags, row, "margin_mismatch",
                    f"stored ebitda_margin_pct={stored_margin:,.2f}% but ebitda/revenue recomputes to "
                    f"{recomputed_margin:,.2f}% (ebitda={ebitda:,.0f}, revenue={revenue:,.0f}, "
                    f"diff={diff:,.2f} points > tolerance {MARGIN_RECOMPUTE_TOLERANCE:.0f})",
                )

        # Independent of the margin_mismatch check above: that one requires
        # revenue to also be present to recompute a comparison margin, which
        # is exactly what missed 3 of 14 real cases on 2026-07-13 (NEXTMEDIA,
        # TARAPUR, TNTELE all had revenue missing too). A margin near 0 paired
        # with materially non-zero ebitda is impossible regardless of whether
        # revenue happens to be populated, so check it unconditionally.
        if (
            pd.notna(stored_margin)
            and pd.notna(ebitda)
            and abs(stored_margin) < ZERO_MARGIN_EPSILON
            and abs(ebitda) > EBITDA_MATERIALITY_FLOOR
        ):
            _flag(
                flags, row, "zero_margin_nonzero_ebitda",
                f"ebitda_margin_pct={stored_margin:,.4f}% (~0) but ebitda={ebitda:,.0f} "
                f"is materially non-zero -- mathematically impossible for any finite revenue "
                f"(revenue={'missing' if pd.isna(revenue) else f'{revenue:,.0f}'})",
            )

        total_debt = row.get("total_debt")
        market_cap = row.get("market_cap")
        if pd.notna(total_debt) and pd.isna(market_cap):
            _flag(
                flags, row, "partial_pull_suspected",
                "total_debt is populated but market_cap is missing. Caveat, checked directly against "
                "this dataset rather than assumed: market_cap (95.9% populated) is actually *not* "
                "more reliably available than total_debt (97.4%) overall, and the reverse gap (market_cap "
                "present, total_debt missing) happens for 48 other companies -- so this is weaker "
                "evidence of a partial pull than it might look at first glance. Flagged as requested, "
                "but treat as a lower-confidence signal than the other checks in this report.",
            )

    return flags


def check_stale_date(df, as_of=None):
    """Flag rows whose as_of_date is older than one reasonable refresh cycle."""
    reference = as_of or datetime.now()
    flags = []
    dates = pd.to_datetime(df["as_of_date"], errors="coerce")
    for (_, row), date in zip(df.iterrows(), dates):
        if pd.isna(date):
            _flag(flags, row, "missing_as_of_date", "as_of_date could not be parsed")
            continue
        age_days = (reference - date).days
        if age_days > STALE_DATA_MAX_AGE_DAYS:
            _flag(
                flags, row, "stale_as_of_date",
                f"as_of_date={date.date()} is {age_days} days old (> {STALE_DATA_MAX_AGE_DAYS}-day threshold)",
            )

    return flags


def run_all_checks(df, as_of=None):
    """Run every check and return one combined flagged-rows DataFrame.

    Does not modify df or write anything back -- this is read-only reporting.
    A human reviews the output and decides what (if anything) to change.
    """
    all_flags = (
        check_range_violations(df)
        + check_cross_field_consistency(df)
        + check_stale_date(df, as_of=as_of)
    )
    if not all_flags:
        return pd.DataFrame(columns=["symbol", "name", "check", "detail"])
    return pd.DataFrame(all_flags)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.data.loaders import DEFAULT_COMPANIES_PATH, load_companies

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_COMPANIES_PATH
    print(f"Loading {path} ...")
    companies = load_companies(path)
    print(f"{len(companies)} rows loaded.\n")

    report = run_all_checks(companies)

    print(f"=== Data quality report: {len(report)} flag(s) across "
          f"{report['symbol'].nunique() if not report.empty else 0} companies ===\n")
    if report.empty:
        print("No issues flagged.")
    else:
        print(report["check"].value_counts().to_string())
        print()
        for check_name, group in report.groupby("check"):
            print(f"--- {check_name} ({len(group)}) ---")
            for _, r in group.iterrows():
                print(f"  {r['symbol']:15s} {r['name'][:45]:45s} {r['detail']}")
            print()

    out_dir = Path(__file__).resolve().parents[2] / "data" / "quality_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"flagged_rows_{datetime.now().strftime('%Y-%m-%d')}.csv"
    report.to_csv(out_path, index=False)
    print(f"Report written to {out_path}")
