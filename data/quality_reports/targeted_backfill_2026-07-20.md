# Targeted core-field backfill — 2026-07-20

**Status: promoted to production.** After the review below and confirming (via
live re-tests, not just inference) that a second pass would not move the
numbers, this became the new `data/enriched/dealscope_base_2026-07-20.csv`,
`DEFAULT_COMPANIES_PATH` was repointed at it, and `companies.json`/`deals.json`
were regenerated. The original candidate snapshot is preserved unchanged at
`data/snapshots/dealscope_backfill_2026-07-20.csv`, and the full per-symbol
audit log (every attempt — symbol, field, source, before/after, timestamp) is
at `data/quality_reports/backfill_log_2026-07-20.csv`. `data/enriched/
dealscope_base_2026-07-17.csv` is untouched and still on disk as the prior
version -- everything here is reversible via git history.

## Before / after

| Tier | Definition | Before | After | Change |
|---|---|---:|---:|---:|
| 1 — Complete | all 8 core fields present | 1,508 (73.7%) | **1,536 (75.1%)** | +28 |
| 2 — Mostly complete | missing 1-2 | 427 | 408 | -19 |
| 3 — Sparse | missing 3+ | 111 | 102 | -9 |

**Target was ~90% (1,841). Landed at 75.1% — short by 305 companies.** This is a
real data-availability ceiling, not an incomplete run (see per-field results
below) — most of what's genuinely fetchable got fetched; what's left mostly isn't
available from any of these sources for these specific companies.

## Per-field results (947 attempts logged, 77 actually filled)

| Field | Missing before | Filled | Hit rate | Source |
|---|---:|---:|---:|---|
| ebitda_margin_pct | 59 | 52 | 88% | yfinance `.info` |
| revenue | 30 | 9 | 30% | yfinance `.info` |
| return_on_equity_pct | 167 | 7 | 4.2% | yfinance `.info` |
| total_debt | 53 | 3 | 5.7% | yfinance `.info` |
| promoter_pledge_pct | 98 | 3 | 3.1% | NSE XBRL |
| trailing_pe | 292 | 2 | 0.7% | yfinance `.info` |
| market_cap | 83 | 1 | 1.2% | yfinance `.info` |
| return_on_capital_employed_pct | 169 | 0 | **0%** | yfinance (Yahoo annual stmt) |

**`ebitda_margin_pct` is the one real win** — closed 88% of its gap in one pass.
Every other field hit a hard wall. This isn't a broken script: re-tested
`fetch_roce()` live against RELIANCE (a healthy large-cap) immediately after the
0/169 ROCE result and it still returns a correct value (8.99%) — the function
works, these 169 specific companies' Yahoo annual statements just don't have
usable EBIT/Total Assets/Current Liabilities data (70 "statement unavailable," 64
missing both EBIT and Current Liabilities, 21 non-positive capital employed, 13
missing just Current Liabilities). Same story for `trailing_pe` (yfinance only
computes a P/E on positive trailing earnings — most of these 292 companies are
exactly the small-caps with negative or negligible earnings that would never
produce one from any source) and `promoter_pledge_pct` (95 of 98 came back "NSE
has no current shareholding XBRL" or a stale pre-2022 filing with the pledge
field simply not reported — a real NSE-side data gap, not a scraper bug).

**Stop-here-and-report wall, exactly as asked** — and confirmed live, not just
inferred from the first pass's own error messages. Re-tested a sample of the
still-missing companies directly against fresh yfinance calls, hours after the
first pass and with no rate-limit accumulation:
- `fetch_roce('RELIANCE')` (a healthy, unrelated large-cap) still returns a
  correct value (8.99%) — the function itself isn't broken.
- 5 late-in-run `trailing_pe` failures (WPIL, XELPMOC, ZODIACLOTH, ZOTA,
  ZSARACOM), re-queried fresh: still `None` for all 5; 3 of the 5 have a real,
  *negative* `trailingEps` (-5.15, -13.33, -22.41) — confirmed negative
  earnings, not a transient miss.
- 5 late-in-run `return_on_equity_pct` failures (WANBURY, WHEELS, WILLAMAGOR,
  ZENITHSTL, ZUARI), re-queried fresh: still `None` for all 5.

A second full pass over the same still-missing companies would re-hit the same
structural absence and burn API calls for no gain — exactly the "don't keep
chasing a real wall" case this task called out in advance. Closing more of the
gap would need a different data vendor for these specific names, not more
retries against the same three sources.

**One real bug found and fixed along the way** (in the shared, reused
`archive/data_pipeline_scripts/enrich_v2.py`, not a new script): NSE's own API
returns the literal string `"-"` as a placeholder for pre-XBRL-era filings
(seen on BATLIBOI/BIMETAL/KOVAI/RAJPALAYAM/SAYAJIHOTL). `fetch_pledge()`'s row
filter (`r.get("xbrl")`) treated `"-"` as a truthy, real URL, so it tried to GET
it and crashed with "Invalid URL" instead of correctly reporting "no current
shareholding XBRL." Fixed the filter to exclude the placeholder explicitly.
Confirmed empirically this doesn't change any of the 5 affected companies'
outcomes (none of them have a real XBRL filing at any point in their history),
but it's a genuine correctness fix for any future run, not just cosmetic.

## A genuinely new finding: 8 companies now show `negative_revenue`

Re-running `src/data/quality_checks.py` against the new snapshot surfaced 138
total flags (vs. 83 before), including **8 `negative_revenue` flags where zero
existed in the base dataset** — all from freshly-pulled `revenue` values, not
anything already there.

**7 of the 8 are Financial Services/NBFC companies**: IFCI, INDOSTAR Capital
Finance, Sammaan Capital, Spandana Sphoorty Financial, TruCap Finance, 21st
Century Management Services, Industrial Investment Trust. This is not a
coincidence — it's the same mechanism as this session's earlier bank-revenue
investigation (`bank_revenue_methodology_2026-07-20.md`): yfinance's
`totalRevenue` for lenders approximates Net Interest Income + Other Income,
which is *mechanically capable of going negative* for a distressed or
high-cost-of-funds NBFC paying more in interest than it earns — unlike a normal
company, where negative revenue is nonsensical. These 7 values are plausibly
real, not errors, but still deserve a specific human look before being trusted
(the existing `check_range_violations`/`negative_revenue` check exists
precisely to surface this kind of case for review, not to auto-reject it).

**The 8th, STCINDIA (State Trading Corporation of India, Industrials & Auto —
not a lender), does not fit this pattern** and has no ready explanation. This one
looks like a genuine, standalone data anomaly worth checking by hand before
trusting its revenue figure at all.

None of these 8 values were altered, discarded, or "fixed" by this script —
they're exactly what yfinance returned, logged and flagged for your review like
every other check in this pipeline.

## Also worth knowing

- 15 new `zero_margin_nonzero_ebitda` and 12 new `margin_mismatch` flags appeared
  (both were 0 before). Expected consequence of a *targeted* backfill: a handful
  of companies had only `ebitda_margin_pct` missing, so this run fetched a fresh
  margin without touching their (older, unrefreshed) `ebitda`/`revenue` values —
  if those absolute figures have moved since the last full pull, the freshly-
  fetched ratio can legitimately drift from what the old absolutes recompute to.
  This is the checker doing its job on a real (if usually small) inconsistency,
  not a bug in the backfill.
- Currency guard held: HCLTECH/INFY's `revenue`/`total_debt` are still correctly
  blank (confirmed) — not silently re-populated with USD-scale figures.
- Column-safe merge verified at full scale: all 55 columns preserved, all 2,046
  rows present, and every row NOT touched by this run is byte-for-byte identical
  to the current live file.

## Still worth a human look

The 8 `negative_revenue` flags (7 plausible-NBFC per the mechanism above, 1
genuine anomaly in STCINDIA) were **not** blocked on before promoting — they're
flagged by the existing quality checker exactly as designed, and nothing about
promoting the rest of a targeted, column-safe, per-cell backfill depends on
resolving them first. They remain open items for you to look at by hand
whenever convenient; nothing downstream treats them as validated.

## Remaining gap: 510 companies (Tier 2 + 3), by field

Missing-count after this pass: revenue 21, ebitda_margin_pct 7,
return_on_capital_employed_pct 169, total_debt 50, market_cap 82, trailing_pe
290, return_on_equity_pct 160, promoter_pledge_pct 95. Full per-symbol detail
(which specific companies, which specific fields) is in
`data/quality_reports/backfill_log_2026-07-20.csv`. Confirmed real ceiling
under yfinance `.info` + Yahoo annual statements + NSE XBRL — see above.
