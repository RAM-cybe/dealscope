"""Sector-relative weighted scoring (PRD section 3, feature 2).

COMPOSITION-ORDER CONTRACT (do not violate this in Module 4 or anywhere else):
score_companies() must always be called on the full, unfiltered company
universe -- never on output that has already passed through
filter_companies(). Percentile ranks are computed against a company's real
ey_bucket peer group; if that peer group has been narrowed by an active
filter, a company's score would drift every time the user adjusts a filter,
even though nothing about the company itself changed. That contradicts
BLUEPRINT's definition of Score as sector-relative against the company's
real peer group. The correct pipeline order is: score first (once, on the
full universe), then filter_companies() purely for display. filter_companies()
must never feed back into score_companies().
"""

import pandas as pd

METRICS = [
    "revenue_growth_pct",
    "ebitda_margin_pct",
    "return_on_capital_employed_pct",
    "total_debt",
]
INVERTED_METRICS = {"total_debt"}  # lower debt -> higher percentile
PERCENTILE_COLUMNS = {m: f"pctl_{m}" for m in METRICS}

# A score built from too few populated metrics is misleadingly precise -- a
# single metric that happens to rank #1 in a small sector peer group can
# produce a "perfect" 100 even though the other 3 factors are unknown. Below
# this many populated metrics, the score itself becomes a genuine gap (NaN),
# same "never fabricate" rule applied everywhere else in this project.
MIN_POPULATED_METRICS = 2


def score_companies(df, weights):
    """Compute a sector-relative 0-100 score for every company in df.

    See the module docstring for the composition-order contract: call this
    on the full unfiltered universe, then filter the result for display.

    weights: dict with any of the 4 METRICS keys, each a 0-10 slider value.
    Missing keys default to 0. If every weight is 0 (or weights is empty),
    falls back to equal weighting across the 4 metrics instead of dividing
    by zero.

    For each metric, a company's percentile is computed within its own
    ey_bucket only (sector-relative, per PRD) via a groupby rank. total_debt
    is inverted: lower debt ranks higher. A company missing a given metric
    has that metric dropped from its own score only -- the remaining metrics
    are reweighted for that company; other companies are unaffected.

    A company with fewer than MIN_POPULATED_METRICS (2) populated metrics
    gets score = NaN rather than a reweighted blend of just 1 (or 0) real
    inputs -- see MIN_POPULATED_METRICS's module-level docstring for why.

    Returns a copy of df with 5 new columns: pctl_<metric> for each of the 4
    metrics (0-100, debt already inverted) and score (0-100). A company
    missing all 4 metrics, or all but one, gets score = NaN.
    """
    df = df.copy()

    resolved_weights = {m: float((weights or {}).get(m, 0)) for m in METRICS}
    if sum(resolved_weights.values()) == 0:
        resolved_weights = {m: 1.0 for m in METRICS}

    for metric in METRICS:
        ascending = metric not in INVERTED_METRICS
        df[PERCENTILE_COLUMNS[metric]] = (
            df.groupby("ey_bucket")[metric].rank(pct=True, ascending=ascending) * 100
        )

    weighted_sum = pd.Series(0.0, index=df.index)
    weight_total = pd.Series(0.0, index=df.index)
    for metric in METRICS:
        pct = df[PERCENTILE_COLUMNS[metric]]
        present = pct.notna()
        weighted_sum += pct.fillna(0) * resolved_weights[metric] * present
        weight_total += resolved_weights[metric] * present

    df["score"] = weighted_sum / weight_total.mask(weight_total == 0)

    populated_count = sum(df[PERCENTILE_COLUMNS[m]].notna() for m in METRICS)
    df.loc[populated_count < MIN_POPULATED_METRICS, "score"] = float("nan")

    return df


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.data.loaders import load_companies
    from src.logic.filtering import filter_companies

    companies = load_companies()

    equal_weights = {m: 5 for m in METRICS}
    scored = score_companies(companies, equal_weights)

    sample_buckets = ["Technology", "Lifesciences", "Financial Services"]
    print("=== score_companies manual-verification sample ===")
    for bucket in sample_buckets:
        peers = scored[scored["ey_bucket"] == bucket]
        pick = peers.dropna(subset=METRICS).iloc[0]
        print(f"\n--- {pick['name']} ({pick['symbol']}), bucket={bucket}, peers n={len(peers)} ---")
        for metric in METRICS:
            raw = pick[metric]
            worse_count = (
                (peers[metric] > raw).sum()
                if metric in INVERTED_METRICS
                else (peers[metric] < raw).sum()
            )
            valid_count = peers[metric].notna().sum()
            manual_pct = (worse_count + 1) / valid_count * 100  # rank-style estimate
            print(
                f"  {metric:35s} raw={raw:>12.4f}  "
                f"engine_pctl={pick[PERCENTILE_COLUMNS[metric]]:6.2f}  "
                f"manual_check~={manual_pct:6.2f} (n={valid_count})"
            )
        manual_score = sum(
            pick[PERCENTILE_COLUMNS[m]] * equal_weights[m] for m in METRICS
        ) / sum(equal_weights[m] for m in METRICS)
        print(f"  manual weighted blend = {manual_score:.4f}   engine score = {pick['score']:.4f}")

    print("\n=== composition-order proof: score on full universe, filter after ===")
    tech_company = scored[scored["ey_bucket"] == "Technology"].iloc[0]
    score_before_filter = tech_company["score"]

    filtered = filter_companies(scored, {"sectors": ["Technology"]})
    row_after_filter = filtered.loc[filtered["symbol"] == tech_company["symbol"]].iloc[0]
    score_after_filter = row_after_filter["score"]

    print(
        f"  {tech_company['name']}: score computed on full universe={score_before_filter:.4f}, "
        f"same row's score after filtering to Technology-only={score_after_filter:.4f} (must match: "
        f"{'OK' if score_before_filter == score_after_filter else 'MISMATCH -- contract violated'})"
    )
    print(f"  full universe rows={len(scored)}, filtered-to-Technology rows={len(filtered)}")
