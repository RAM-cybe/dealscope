"""Sector-relative weighted scoring (PRD section 3, feature 2).

COMPOSITION-ORDER CONTRACT (do not violate this in Module 4 or anywhere else):
score_companies() must always be called on the full, unfiltered company
universe -- never on output that has already passed through
filter_companies(). Percentile ranks are computed against a company's real
peer group (bucket_col); if that peer group has been narrowed by an active
filter, a company's score would drift every time the user adjusts a filter,
even though nothing about the company itself changed. That contradicts
BLUEPRINT's definition of Score as sector-relative against the company's
real peer group. The correct pipeline order is: score first (once, on the
full universe), then filter_companies() purely for display. filter_companies()
must never feed back into score_companies().

Factor 4 (leverage_ratio) is Net Debt / EBITDA, inverted (lower leverage
ranks higher). D/E is the fallback when EBITDA is missing or <= 0. Financial
Services is excluded from Factor 4 entirely -- a bank's deposits and
borrowings are its operating model, not distress -- and the remaining three
factors are reweighted for that company. Missing values are never treated
as zero.
"""

import pandas as pd

LEVERAGE_METRIC = "leverage_ratio"
LEGACY_LEVERAGE_WEIGHT_KEY = "total_debt"
ND_EBITDA_KIND = "nd_ebitda"
DE_KIND = "de"
LEVERAGE_KIND_COL = "_leverage_kind"
FINANCIAL_SERVICES_LABEL = "Financial Services"

METRICS = [
    "revenue_growth_pct",
    "ebitda_margin_pct",
    "return_on_capital_employed_pct",
    LEVERAGE_METRIC,
]
INVERTED_METRICS = {LEVERAGE_METRIC}  # lower leverage -> higher percentile
PERCENTILE_COLUMNS = {m: f"pctl_{m}" for m in METRICS}
UNCLASSIFIED_LABEL = "Unclassified"

# A score built from too few populated metrics is misleadingly precise -- a
# single metric that happens to rank #1 in a small sector peer group can
# produce a "perfect" 100 even though the other 3 factors are unknown. Below
# this many populated metrics, the score itself becomes a genuine gap (NaN),
# same "never fabricate" rule applied everywhere else in this project.
MIN_POPULATED_METRICS = 2


def _financial_services_mask(df, bucket_col):
    """True for rows whose peer-group label is Financial Services."""
    if bucket_col not in df.columns:
        return pd.Series(False, index=df.index)
    return df[bucket_col].astype("string").str.strip().eq(FINANCIAL_SERVICES_LABEL)


def compute_leverage_ratio(df, bucket_col="ey_bucket"):
    """Build the Factor 4 input series and a kind tag per company.

    Returns (leverage_ratio, kind) aligned to df.index.

    kind is:
      - "nd_ebitda" when EBITDA is present and > 0 and total_debt is present
        (Net Debt / EBITDA when cash is known; Gross Debt / EBITDA when cash
        is a genuine gap -- never invent cash = 0)
      - "de" when ND/EBITDA cannot be formed and D/E is present and >= 0
      - NA for Financial Services (excluded) and for real data gaps

    The two kinds are ranked in separate percentile pools inside
    score_companies() so a D/E of 0.5 is never compared as if it were a
    Net Debt / EBITDA of 0.5.
    """
    debt = pd.to_numeric(df["total_debt"], errors="coerce") if "total_debt" in df.columns else pd.Series(float("nan"), index=df.index)
    cash = pd.to_numeric(df["total_cash"], errors="coerce") if "total_cash" in df.columns else pd.Series(float("nan"), index=df.index)
    ebitda = pd.to_numeric(df["ebitda"], errors="coerce") if "ebitda" in df.columns else pd.Series(float("nan"), index=df.index)
    de = pd.to_numeric(df["debt_to_equity"], errors="coerce") if "debt_to_equity" in df.columns else pd.Series(float("nan"), index=df.index)

    fs = _financial_services_mask(df, bucket_col)

    # Net debt when cash is known. If cash is missing, fall back to gross
    # debt inside the same ratio family -- that is "we don't have cash",
    # not "cash is zero".
    net_debt = debt - cash
    debt_for_ratio = net_debt.where(cash.notna(), debt)

    usable_ebitda = ebitda.notna() & (ebitda > 0)
    use_nd = (~fs) & usable_ebitda & debt_for_ratio.notna()
    nd_ratio = (debt_for_ratio / ebitda).replace([float("inf"), float("-inf")], float("nan"))
    use_nd = use_nd & nd_ratio.notna()

    # D/E fallback when EBITDA is missing or <= 0, or debt is missing so
    # ND/EBITDA cannot be formed. D/E < 0 is negative equity -- not "low
    # leverage" -- so it stays a gap rather than an inverted top rank.
    use_de = (~fs) & (~use_nd) & de.notna() & (de >= 0)

    leverage = pd.Series(float("nan"), index=df.index, dtype="float64")
    kind = pd.Series(pd.NA, index=df.index, dtype="string")
    leverage = leverage.mask(use_nd, nd_ratio)
    leverage = leverage.mask(use_de, de)
    kind = kind.mask(use_nd, ND_EBITDA_KIND)
    kind = kind.mask(use_de, DE_KIND)
    return leverage, kind


def _resolved_weights(weights):
    """Map slider values onto METRICS. Accept the legacy total_debt key."""
    raw = dict(weights or {})
    if LEVERAGE_METRIC not in raw and LEGACY_LEVERAGE_WEIGHT_KEY in raw:
        raw[LEVERAGE_METRIC] = raw[LEGACY_LEVERAGE_WEIGHT_KEY]
    resolved = {m: float(raw.get(m, 0)) for m in METRICS}
    if sum(resolved.values()) == 0:
        resolved = {m: 1.0 for m in METRICS}
    return resolved


def score_companies(df, weights, bucket_col="ey_bucket"):
    """Compute a sector-relative 0-100 score for every company in df.

    See the module docstring for the composition-order contract: call this
    on the full unfiltered universe, then filter the result for display.

    weights: dict with any of the 4 METRICS keys, each a 0-10 slider value.
    The legacy key "total_debt" is accepted as an alias for leverage_ratio.
    Missing keys default to 0. If every weight is 0 (or weights is empty),
    falls back to equal weighting across the 4 metrics instead of dividing
    by zero.

    bucket_col: the column defining the peer group. Defaults to the legacy
    6-bucket ey_bucket; the app passes "sector_v2" (13-sector taxonomy).

    For each metric, a company's percentile is computed within its own
    sector bucket only (sector-relative, per PRD) via a groupby rank.
    leverage_ratio is inverted: lower leverage ranks higher. Net Debt /
    EBITDA and D/E fallback rows are ranked in separate pools so the units
    never mix. Financial Services rows have Factor 4 dropped (percentile
    NaN); the remaining present factors are reweighted for that company
    only -- other companies are unaffected.

    A company missing a given metric has that metric dropped from its own
    score only -- the remaining metrics are reweighted for that company.

    A company with fewer than MIN_POPULATED_METRICS (2) populated metrics
    gets score = NaN rather than a reweighted blend of just 1 (or 0) real
    inputs -- see MIN_POPULATED_METRICS's module-level docstring for why.

    Returns a copy of df with leverage_ratio, pctl_<metric> for each of
    the 4 metrics (0-100, leverage already inverted) and score (0-100). A
    company missing all 4 metrics, or all but one, gets score = NaN.
    """
    df = df.copy()

    leverage, kind = compute_leverage_ratio(df, bucket_col=bucket_col)
    df[LEVERAGE_METRIC] = leverage
    df[LEVERAGE_KIND_COL] = kind

    resolved_weights = _resolved_weights(weights)

    for metric in METRICS:
        ascending = metric not in INVERTED_METRICS
        if metric == LEVERAGE_METRIC:
            df[PERCENTILE_COLUMNS[metric]] = (
                df.groupby([bucket_col, LEVERAGE_KIND_COL], dropna=True)[metric]
                .rank(pct=True, ascending=ascending)
                * 100
            )
        else:
            df[PERCENTILE_COLUMNS[metric]] = (
                df.groupby(bucket_col)[metric].rank(pct=True, ascending=ascending) * 100
            )

    df = df.drop(columns=[LEVERAGE_KIND_COL])

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

    # Unclassified is not a real peer group. Ranking 80+ unrelated names
    # against each other produces fake 90–100 scores for companies that
    # simply happen to be the least-bad row in a junk bucket. Drop the
    # score and every factor percentile rather than publish that.
    unclassified = df[bucket_col].isna() | (
        df[bucket_col].astype(str).str.strip() == UNCLASSIFIED_LABEL
    )
    for metric in METRICS:
        df.loc[unclassified, PERCENTILE_COLUMNS[metric]] = float("nan")
    df.loc[unclassified, "score"] = float("nan")

    return df


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.data.loaders import load_companies
    from src.logic.filtering import filter_companies

    companies = load_companies()

    equal_weights = {m: 5 for m in METRICS}
    scored = score_companies(companies, equal_weights, bucket_col="sector_v2")

    sample_buckets = ["Technology & IT Services", "Healthcare & Lifesciences", "Financial Services"]
    print("=== score_companies manual-verification sample ===")
    for bucket in sample_buckets:
        peers = scored[scored["sector_v2"] == bucket]
        if bucket == FINANCIAL_SERVICES_LABEL:
            pick = peers.dropna(subset=["revenue_growth_pct", "ebitda_margin_pct", "return_on_capital_employed_pct"]).iloc[0]
            print(f"\n--- {pick['name']} ({pick['symbol']}), bucket={bucket}, peers n={len(peers)} ---")
            print(
                f"  Factor 4 excluded for Financial Services: "
                f"pctl_{LEVERAGE_METRIC}={pick[PERCENTILE_COLUMNS[LEVERAGE_METRIC]]} "
                f"(must be NaN)"
            )
            continue
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
        present = [m for m in METRICS if pd.notna(pick[PERCENTILE_COLUMNS[m]])]
        manual_score = sum(
            pick[PERCENTILE_COLUMNS[m]] * equal_weights[m] for m in present
        ) / sum(equal_weights[m] for m in present)
        print(f"  manual weighted blend = {manual_score:.4f}   engine score = {pick['score']:.4f}")

    print("\n=== composition-order proof: score on full universe, filter after ===")
    tech_company = scored[scored["sector_v2"] == "Technology & IT Services"].iloc[0]
    score_before_filter = tech_company["score"]

    filtered = filter_companies(
        scored,
        {"sectors": ["Technology & IT Services"], "sector_col": "sector_v2"},
    )
    row_after_filter = filtered.loc[filtered["symbol"] == tech_company["symbol"]].iloc[0]
    score_after_filter = row_after_filter["score"]

    print(
        f"  {tech_company['name']}: score computed on full universe={score_before_filter:.4f}, "
        f"same row's score after filtering to Technology-only={score_after_filter:.4f} (must match: "
        f"{'OK' if score_before_filter == score_after_filter else 'MISMATCH -- contract violated'})"
    )
    print(f"  full universe rows={len(scored)}, filtered-to-Technology rows={len(filtered)}")

    fs = scored[scored["sector_v2"] == FINANCIAL_SERVICES_LABEL]
    print(
        f"\n=== Financial Services Factor 4 exclusion: "
        f"{int(fs[PERCENTILE_COLUMNS[LEVERAGE_METRIC]].isna().all())} "
        f"(1 = every FS row has NaN Factor 4, n={len(fs)}) ==="
    )
