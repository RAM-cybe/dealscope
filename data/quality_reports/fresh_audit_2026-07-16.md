# DealScope Data Audit — 2026-07-16 (fresh-eyes pass)

Ran against the live dataset `data/enriched/dealscope_base_2026-07-12.csv`
(2,046 companies). This pass re-runs the automated checker **and** probes for
error *classes* the checker still can't catch — the discipline that surfaced
the zero-margin bug by hand last time. Honest bottom line up front: **nothing
new that produces a wrong output was found.**

## 1. Automated quality checker — re-run

`python -m src.data.quality_checks` → **83 flags across 83 companies**, identical
in composition to the last run:

| check | count | status |
|---|---|---|
| `partial_pull_suspected` | 78 | already-documented lower-confidence signal (total_debt present, market_cap missing; the reverse gap happens for 48 others, so weak evidence) |
| `extreme_ebitda_margin` | 3 | BOHRAIND (−92,980%), SPARC (+4,084%), CREATIVEYE (−417%) — all previously confirmed real near-zero-revenue cases, left untouched |
| `extreme_roce` | 2 | KOHINOOR (811%), SUPREMEINF (2,151%) — previously confirmed real small-capital-base cases |
| `zero_margin_nonzero_ebitda` | 0 | the class that needed manual discovery last round now catches automatically; all 14 prior cases stay fixed |

No new automated flags.

## 2. Fresh-eyes probes for new error classes

Wrote a one-off analysis testing invariants the checker does **not** encode:

| probe | result | verdict |
|---|---|---|
| Duplicate `symbol`s | 0 | clean |
| `quick_ratio > current_ratio` (impossible: quick excludes inventory, so quick ≤ current always) | **0 of 1,894** with both present | data respects the invariant — no error class here |
| `debt_to_equity < 0` (would imply negative book equity) | 0 | clean |
| `net_income > revenue` | 20 | see below — legitimate, spot-checked |
| `ebitda_margin_pct` in ±100–300% (below the extreme threshold, so unflagged) | 12 | all near-zero-revenue companies (rev ₹0.6–42cr) — same understood mechanism as BOHRAIND/SPARC, just under threshold; real, not errors |
| `enterprise_value < 0` | 18 | net-cash companies (cash > mcap + debt); `enterprise_value` is a filter-only field, never used by scoring or valuation, so no output impact |

### The `net_income > revenue` set (20 companies) — spot-checked

Most are holding / investment companies (BAJAJHLDNG, BFINVEST, GFLLIMITED,
ALEMBICLTD) where investment/dividend income dwarfs operating revenue — expected,
not an error. One genuinely stood out and was verified against public sources:

- **KIRIINDUS (Kiri Industries)** — revenue ₹839.6cr, operating EBITDA **−₹221cr**,
  but net income **+₹5,566.5cr** (2.2× its ₹2,527cr market cap). That pattern
  (negative operations, huge positive bottom line) signals a one-time
  non-operating gain. Public verification: Kiri reported an FY26 consolidated
  net profit of **₹5,566.94cr** (up ~2,003% YoY) driven by a **₹5,854cr
  exceptional gain from the DyStar dispute settlement** (received US$689m on
  31 Dec 2025). The dataset's ₹5,566.5cr matches the reported figure to the
  crore. **Real, not a data error.**

  *Honest methodology note (not a data fix):* the P/E-implied valuation applies
  sector-peer multiples to this reported net income, so KIRIINDUS's implied
  range reflects the one-time gain. That's a known limitation of mechanical,
  unnormalised multiple valuation — not a data error, and normalising it out
  would mean inventing an "adjusted" figure, which this project's no-fabrication
  rule forbids. The underlying number is correct and disclosed as-is.

## 3. Population rates (live dataset, re-measured)

revenue 98.5% · ebitda 91.3% · ebitda_margin_pct 97.1% · total_debt 97.4% ·
net_income 94.9% · market_cap 95.9% · return_on_capital_employed_pct 91.7% ·
promoter_pledge_pct 95.2% · revenue_growth_pct 96.4%. Consistent with the
figures documented in CONTEXT.md; no material drift.

## Bottom line

The checker's 83 flags are all previously triaged (real edge cases + the
lower-confidence partial-pull signal), zero new. The fresh-eyes probes found
no new class of error that reaches an app output: the one mathematically-strong
new invariant tested (quick ≤ current) holds for every row, and the only
eye-catching anomaly (KIRIINDUS) verified as a real, correctly-captured
one-time gain. The `quick_ratio ≤ current_ratio` invariant is worth adding to
the automated checker as a cheap future guard, but there's nothing to fix in
the current data.
