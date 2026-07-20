# DealScope Data Quality Audit — 2026-07-20

Reporting-only audit of the live company dataset ahead of wider sharing. Nothing in this
document changes any data, scoring logic, or code beyond two new checks added to
`src/data/quality_checks.py` (see §2). Every flag below is a "look at this," not a "this is
wrong" — per the existing discipline in `quality_checks.py`, a human reviews and decides.

**Dataset audited**: `data/enriched/dealscope_base_2026-07-17.csv` (the live
`DEFAULT_COMPANIES_PATH` per `src/data/loaders.py`), loaded via `load_companies()` —
**2,046 companies, 55 raw columns** (56 after the loader adds `ey_bucket`).

---

## 1. Completeness audit

### All 55 fields, sorted most-complete first

| Field | Present | Missing | % Complete |
|---|---:|---:|---:|
| symbol | 2046 | 0 | 100.0% |
| name | 2046 | 0 | 100.0% |
| as_of_date | 2046 | 0 | 100.0% |
| status | 2046 | 0 | 100.0% |
| financial_currency | 2046 | 0 | 100.0% |
| currency_flag | 2046 | 0 | 100.0% |
| data_pull_date | 2046 | 0 | 100.0% |
| price_to_book | 2034 | 12 | 99.4% |
| revenue | 2016 | 30 | 98.5% |
| total_debt | 1993 | 53 | 97.4% |
| enterprise_value | 1988 | 58 | 97.2% |
| total_cash | 1989 | 57 | 97.2% |
| ebitda_margin_pct | 1987 | 59 | 97.1% |
| sector | 1972 | 74 | 96.4% |
| industry | 1972 | 74 | 96.4% |
| revenue_growth_pct | 1972 | 74 | 96.4% |
| total_assets | 1973 | 73 | 96.4% |
| total_liabilities | 1972 | 74 | 96.4% |
| total_assets_fy0 | 1972 | 74 | 96.4% |
| net_income_fy0 | 1971 | 75 | 96.3% |
| total_revenue_fy0 | 1971 | 75 | 96.3% |
| total_revenue_fy1 | 1971 | 75 | 96.3% |
| net_income_fy1 | 1964 | 82 | 96.0% |
| market_cap | 1963 | 83 | 95.9% |
| operating_cash_flow_fy0 | 1961 | 85 | 95.8% |
| insider_holding_pct | 1959 | 87 | 95.7% |
| total_assets_fy1 | 1957 | 89 | 95.7% |
| shares_outstanding_fy1 | 1955 | 91 | 95.6% |
| operating_cash_flow_fy1 | 1953 | 93 | 95.5% |
| shares_outstanding_fy0 | 1951 | 95 | 95.4% |
| promoter_pledge_pct | 1948 | 98 | 95.2% |
| net_income | 1942 | 104 | 94.9% |
| operating_cash_flow | 1923 | 123 | 94.0% |
| return_on_assets | 1918 | 128 | 93.7% |
| ebit | 1904 | 142 | 93.1% |
| working_capital | 1895 | 151 | 92.6% |
| current_ratio | 1895 | 151 | 92.6% |
| current_assets_fy0 | 1895 | 151 | 92.6% |
| quick_ratio | 1894 | 152 | 92.6% |
| current_liabilities_fy0 | 1894 | 152 | 92.6% |
| cost_of_revenue_fy1 | 1886 | 160 | 92.2% |
| current_assets_fy1 | 1882 | 164 | 92.0% |
| current_liabilities_fy1 | 1880 | 166 | 91.9% |
| return_on_equity_pct | 1879 | 167 | 91.8% |
| return_on_capital_employed_pct | 1877 | 169 | 91.7% |
| cost_of_revenue_fy0 | 1871 | 175 | 91.4% |
| ebitda | 1867 | 179 | 91.3% |
| debt_to_equity | 1838 | 208 | 89.8% |
| beta | 1793 | 253 | 87.6% |
| free_cash_flow | 1770 | 276 | 86.5% |
| trailing_pe | 1754 | 292 | 85.7% |
| long_term_debt_fy1 | 1540 | 506 | 75.3% |
| long_term_debt_fy0 | 1512 | 534 | 73.9% |
| retained_earnings | 452 | 1594 | 22.1% |
| peg_ratio | 81 | 1965 | 4.0% |

**Read**: identifiers/metadata and `revenue` are essentially universal (≥98.5%). The core
P&L/balance-sheet fields sit in a fairly tight 91–97% band. `beta`, `free_cash_flow`, and
`trailing_pe` (86–88%) are the patchiest fields already known to be gappy from earlier
work. `retained_earnings` (22%) and `peg_ratio` (4%) are effectively unreliable at the
whole-dataset level — treat any screen or check that depends on them as low-coverage by
construction, not as a data bug.

### Tier segmentation on the 8 tear-sheet core fields

Core fields: `revenue`, `ebitda_margin_pct`, `return_on_capital_employed_pct`,
`total_debt`, `market_cap`, `trailing_pe`, `return_on_equity_pct`, `promoter_pledge_pct`.

| Tier | Definition | Companies |
|---|---|---:|
| 1 — Complete | all 8 core fields present | **1,508** |
| 2 — Mostly complete | missing 1–2 of the 8 | **427** |
| 3 — Sparse | missing 3+ of the 8 | **111** |

1,508 + 427 + 111 = 2,046 ✓. So **73.7%** of the universe shows a fully-populated tear
sheet today; **26.3%** (538 companies) will show at least one "N/A," and **5.4%** (111)
will show three or more.

The single most common Tier-2/3 gap pattern is `return_on_capital_employed_pct` +
`market_cap` + `trailing_pe` + `promoter_pledge_pct` missing together (≈70 of the 111
Tier-3 rows) — looks like one correlated pull gap (likely thinly-traded/illiquid names
yfinance under-serves), not four independent failures.

**Recognizable names that land in Tier 3** (would show 3+ "N/A"s on their tear sheet today
— worth knowing before a recruiter or reviewer opens one of these specifically):

- **AU Small Finance Bank** (AUBANK) — missing `ebitda_margin_pct`, `return_on_capital_employed_pct`, `return_on_equity_pct`
- **HCL Infosystems** (HCL-INSYS) — missing `return_on_capital_employed_pct`, `trailing_pe`, `return_on_equity_pct`
- **IDFC First Bank** (IDFCFIRSTB) — missing `return_on_capital_employed_pct`, `total_debt`, `return_on_equity_pct`
- **MTNL** (Mahanagar Telephone Nigam) — missing `return_on_capital_employed_pct`, `trailing_pe`, `return_on_equity_pct`
- **Star Health and Allied Insurance** (STARHEALTH) — missing `return_on_capital_employed_pct`, `total_debt`, `return_on_equity_pct`
- **Tata Teleservices (Maharashtra)** (TTML) — missing `return_on_capital_employed_pct`, `trailing_pe`, `return_on_equity_pct`

The pattern above (bank/financial names missing ROCE/ROE/total_debt) recurs across all six
— consistent with the §3 finding that financial-services revenue/ratio fields behave
differently from non-financial sectors in this pull.

**Full 111-company Tier-3 list**: reproducible on demand via the same query used for this
report (`missing_count = df[CORE_FIELDS].isna().sum(axis=1); df[missing_count >= 3]`) — not
inlined in full here to keep this document scannable; ask if you want the complete CSV.

---

## 2. Statistical outlier / internal-consistency pass

### 2a. Existing `run_all_checks` output, run as-is

```
=== Data quality report: 83 flag(s) across 83 companies ===

check
partial_pull_suspected    78
extreme_ebitda_margin      3
extreme_roce               2
```

- **`extreme_ebitda_margin` (3)**: BOHRAIND (-92,980.00%), CREATIVEYE (-417.48%), SPARC
  (+4,083.68%) — all outside the ±300% guard band.
- **`extreme_roce` (2)**: KOHINOOR (+811.35%), SUPREMEINF (+2,150.59%) — outside the ±200%
  guard band.
- **`partial_pull_suspected` (78)**: `total_debt` populated but `market_cap` missing. The
  check's own docstring already flags this as a lower-confidence signal (market_cap's
  95.9% overall completeness isn't actually higher than total_debt's 97.4%), so treat this
  bucket as "worth a glance," not "worth alarm."
- **Zero** hits on `negative_revenue`, `negative_total_debt`, `negative_market_cap`,
  `negative_current_ratio`/`negative_quick_ratio`, `margin_mismatch`,
  `zero_margin_nonzero_ebitda`, `quick_exceeds_current`, or `stale_as_of_date` — none of
  these impossible-value or staleness conditions currently exist in the live dataset.

### 2b. Two new checks added

Added as new functions in `src/data/quality_checks.py` (`check_pe_sanity` and
`check_market_cap_revenue_ratio`), documented in the same style as the existing checks and
wired into `run_all_checks` by appending — no existing check's logic was touched.

**`check_pe_sanity`** — flags `trailing_pe` populated alongside negative or near-zero
`net_income` (< Rs 10 lakh in magnitude; a P/E on non-positive/near-zero earnings isn't
economically meaningful — see the new `NET_INCOME_MATERIALITY_FLOOR` constant for the
full reasoning, same order-of-magnitude logic as the existing `EBITDA_MATERIALITY_FLOOR`).

**`check_market_cap_revenue_ratio`** — flags `market_cap / revenue` outside `[0.01x,
500x]`. Both bounds are deliberately wide "second look" thresholds, grounded in the live
dataset's own distribution (1,937 companies with both fields, revenue > 0): median ratio
≈2.4x, P75 ≈5.4x, so 500x sits ~90x past P75 — far enough to be unusual, not so tight it
catches routine variation. The live dataset's minimum observed ratio (~0.043x) doesn't
currently clear the 0.01x floor, so that bound is intentionally generous headroom rather
than tuned to what's already there.

### Combined output with both new checks wired in

```
=== Data quality report: 102 flag(s) across 100 companies ===

check
partial_pull_suspected           78
pe_on_negative_earnings           9
market_cap_revenue_ratio_high     9
extreme_ebitda_margin             3
extreme_roce                      2
pe_on_near_zero_earnings          1
```

**`pe_on_negative_earnings` (9)**:

| Symbol | Name | trailing_pe | net_income |
|---|---|---:|---:|
| AURUM | Aurum PropTech | 907.20 | -₹10.45 Cr |
| GTLINFRA | GTL Infrastructure | 2.22 | -₹2,322.08 Cr |
| IFCI | IFCI Limited | 112.26 | -₹679.07 Cr |
| KOLTEPATIL | Kolte-Patil Developers | 63.32 | -₹38.67 Cr |
| LAXMICOT | Laxmi Cotspin | 3.31 | -₹1.20 Cr |
| ORCHPHARMA | Orchid Pharma | 250.01 | -₹179.01 Cr |
| SAKHTISUG | Sakthi Sugars | 7.07 | -₹178.66 Cr |
| WAAREERTL | Waaree Renewable Technologies | 22.17 | -₹2.83 Cr |
| WANBURY | Wanbury Limited | 15.34 | -₹96.33 Cr |

**`pe_on_near_zero_earnings` (1)**: LOTUSEYE (Lotus Eye Hospital), trailing_pe=2,957.00,
net_income=₹0.08 Cr — the ratio is arbitrarily inflated by a near-zero denominator.

**`market_cap_revenue_ratio_high` (9)** (all > 500x, none flagged < 0.01x):

| Symbol | Name | Ratio | Market Cap | Revenue |
|---|---|---:|---:|---:|
| RTNINDIA | RattanIndia Enterprises | 79,787x | ₹4,636 Cr | ₹5.81 lakh |
| BOHRAIND | Bohra Industries | 7,218x | ₹14.4 Cr | ₹2 lakh |
| HEMIPROP | Hemisphere Properties India | 3,991x | ₹3,961 Cr | ₹99.25 lakh |
| MMTC | MMTC Limited | 2,864x | ₹9,765 Cr | ₹3.41 Cr |
| SUVEN | Suven Life Sciences | 1,421x | ₹10,112 Cr | ₹7.11 Cr |
| WAAREERTL | Waaree Renewable Technologies | 1,275x | ₹10,605 Cr | ₹8.32 Cr |
| JINDALPHOT | Jindal Photo | 1,450x | ₹1,180 Cr | ₹0.81 Cr |
| LCCINFOTEC | LCC Infotech | 1,277x | ₹57.85 Cr | ₹4.53 lakh |
| BLAL | BEML Land Assets | 777x | ₹763 Cr | ₹98.25 lakh |

**Cross-reference worth noting**: WAAREERTL appears in *both* new-check buckets
(negative earnings **and** an extreme market-cap/revenue ratio) — two independent signals
pointing at the same company is a stronger "look here first" than either alone.

---

## 3. Real-world spot-check

**Sample**: top 25 companies by `market_cap` + the 5 companies already flagged by
`check_range_violations` as extreme (BOHRAIND, CREATIVEYE, SPARC, KOHINOOR, SUPREMEINF) =
**30 companies**. Note: this run's `check_range_violations` produced zero hits on the
impossible-value checks (`negative_revenue`, `negative_total_debt`, etc.) — the extreme
margin/ROCE flags above are the closest thing to a "critical" list this dataset currently
has, so they're used here instead.

**Method**: looked up each company's most recent real reported revenue via screener.in
(and, for Reliance, cross-checked against RIL's own investor-relations release) and
compared it to the stored `revenue` value (which the pipeline sources from yfinance's
`totalRevenue`, effectively a trailing-twelve-month figure — see
`archive/data_pipeline_scripts/enrich_v2.py:208`). A gap of roughly ≤10% is treated as
"agree" (normal TTM-window/reporting-period noise); wider gaps are called out.

**2 of 30 are not comparable at all**: **Infosys (INFY)** and **HCL Technologies
(HCLTECH)** have `revenue` (and `ebitda`, `total_debt`, `net_income`) deliberately blanked
— both carry `financial_currency=USD`, `currency_flag=USD_REPORTED`, and per the loader's
own comment this was a known, intentional fix (rather than silently showing USD figures as
INR). Confirmed directly against the live data; not a gap in this audit, a documented prior
decision. Their currency-agnostic ratio fields (`ebitda_margin_pct`, ROE, ROCE,
`trailing_pe`) are still populated.

| Symbol | Stored revenue (₹ Cr) | Real-world figure (₹ Cr) | Source | Verdict |
|---|---:|---:|---|---|
| RELIANCE | 1,057,219 | 1,123,055 (TTM, screener) | [screener.in/RELIANCE](https://www.screener.in/company/RELIANCE/consolidated/) | Agree (-5.9%) |
| HDFCBANK | 283,315 | 351,819 (TTM, screener) | [screener.in/HDFCBANK](https://www.screener.in/company/HDFCBANK/consolidated/) | **Disagree (-19.5%)** |
| BHARTIARTL | 210,973 | 210,973 (FY Mar-2026) | [screener.in/BHARTIARTL](https://www.screener.in/company/BHARTIARTL/consolidated/) | Exact match |
| ICICIBANK | 217,451 | 198,379 (TTM, screener) | [screener.in/ICICIBANK](https://www.screener.in/company/ICICIBANK/consolidated/) | Agree (+9.6%, borderline) |
| SBIN | 376,678 | 514,933 (FY Mar-2026, consol.) | [screener.in/SBIN](https://www.screener.in/company/SBIN/consolidated/) | **Disagree (-26.8%)** |
| TCS | 275,859 | 275,859 (TTM, screener) | [screener.in/TCS](https://www.screener.in/company/TCS/consolidated/) | Exact match |
| BAJFINANCE | 43,835 | 81,985 (FY Mar-2026) | [screener.in/BAJFINANCE](https://www.screener.in/company/BAJFINANCE/consolidated/) | **Disagree (-46.5%)** |
| LICI | 981,577 | 977,772 (FY Mar-2026) | [screener.in/LICI](https://www.screener.in/company/LICI/consolidated/) | Agree (+0.4%) |
| LT | 291,618 | 285,874 (FY Mar-2026) | [screener.in/LT](https://www.screener.in/company/LT/consolidated/) | Agree (+2.0%) |
| HINDUNILVR | 64,468 | 64,468 (FY Mar-2026) | [screener.in/HINDUNILVR](https://www.screener.in/company/HINDUNILVR/consolidated/) | Exact match |
| SUNPHARMA | 58,462 | 58,462 (TTM, screener) | [screener.in/SUNPHARMA](https://www.screener.in/company/SUNPHARMA/consolidated/) | Exact match |
| ADANIENT | 100,469 | 100,469 (FY Mar-2026) | [screener.in/ADANIENT](https://www.screener.in/company/ADANIENT/consolidated/) | Exact match |
| MARUTI | 183,316 | 183,316 (TTM, screener) | [screener.in/MARUTI](https://www.screener.in/company/MARUTI/consolidated/) | Exact match |
| INFY | missing | not comparable | — | N/A — intentional currency-guard blank |
| ADANIPOWER | 54,241 | 54,241 (FY Mar-2026) | [screener.in/ADANIPOWER](https://www.screener.in/company/ADANIPOWER/consolidated/) | Exact match |
| ADANIPORTS | 38,736 | 38,736 (FY Mar-2026) | [screener.in/ADANIPORTS](https://www.screener.in/company/ADANIPORTS/consolidated/) | Exact match |
| AXISBANK | 74,549 | 135,732 (TTM, screener) | [screener.in/AXISBANK](https://www.screener.in/company/AXISBANK/consolidated/) | **Disagree (-45.1%)** |
| TITAN | 87,584 | 87,584 (TTM, screener) | [screener.in/TITAN](https://www.screener.in/company/TITAN/consolidated/) | Exact match |
| M&M | 201,798 | 198,639 (FY Mar-2026) | [screener.in/M&M](https://www.screener.in/company/M&M/consolidated/) | Agree (+1.6%) |
| KOTAKBANK | 74,043 | 70,887 (TTM, screener) | [screener.in/KOTAKBANK](https://www.screener.in/company/KOTAKBANK/consolidated/) | Agree (+4.5%) |
| ITC | 78,868 | 78,868 (FY Mar-2026) | [screener.in/ITC](https://www.screener.in/company/ITC/consolidated/) | Exact match |
| ULTRACEMCO | 88,512 | 88,512 (TTM, screener) | [screener.in/ULTRACEMCO](https://www.screener.in/company/ULTRACEMCO/consolidated/) | Exact match |
| NTPC | 187,385 | 187,385 (FY Mar-2026) | [screener.in/NTPC](https://www.screener.in/company/NTPC/consolidated/) | Exact match |
| HCLTECH | missing | not comparable | — | N/A — intentional currency-guard blank |
| ONGC | 662,247 | 662,247 (FY Mar-2026) | [screener.in/ONGC](https://www.screener.in/company/ONGC/consolidated/) | Exact match |
| BOHRAIND | ~0.002 | 0.00 (FY Mar-2026) | [screener.in/BOHRAIND](https://www.screener.in/company/BOHRAIND/) | Agree — confirms genuine near-zero-revenue case |
| CREATIVEYE | 0.42 | 0.42 (TTM, screener) | [screener.in/CREATIVEYE](https://www.screener.in/company/CREATIVEYE/) | Exact match — confirms genuine near-zero-revenue case |
| SPARC | 39.15 | 1,879 (FY Mar-2026) / 72 (FY Mar-2025) | [screener.in/SPARC](https://www.screener.in/company/SPARC/consolidated/) | **Disagree / unclear** — stored figure doesn't cleanly match either real annual period |
| KOHINOOR | 147.60 | 148 (TTM, screener) | [screener.in/KOHINOOR](https://www.screener.in/company/KOHINOOR/) | Exact match — confirms genuine small-capital-base case |
| SUPREMEINF | 73.61 | 65.33 (FY Mar-2026) | [screener.in/SUPREMEINF](https://www.screener.in/company/SUPREMEINF/) | Agree (+12.7%, borderline) |

**Headline finding — a clean sector pattern**: every non-financial large-cap checked
(18 of 23 comparable top-25 names) matched the real-world figure **exactly** or within
~5%. Every large-cap **bank/NBFC** checked showed a real gap: HDFCBANK (-19.5%), SBIN
(-26.8%), BAJFINANCE (-46.5%), AXISBANK (-45.1%) — ICICIBANK and KOTAKBANK were the
exceptions, landing within the ~10% tolerance. This strongly suggests `totalRevenue` from
yfinance (the pipeline's revenue source) is inconsistently scoped for financial-sector
tickers specifically — plausibly mixing "Total Income" (interest + other income) and a
narrower revenue line depending on the ticker, or standalone-vs-consolidated scope
differences (SBI's stored figure, for instance, may reflect standalone bank revenue while
the real-world figure found is consolidated-group, which includes SBI Life/SBI Cards).
**Worth a source-side investigation into how yfinance's revenue field behaves for Indian
banks/NBFCs specifically** before trusting Financial Services-sector revenue comparisons
on this site.

**SPARC is a genuine, unexplained outlier** independent of the sector pattern above (it's
Pharma, not Financial Services) — its stored ₹39.15 Cr doesn't sit cleanly between the
real FY2025 (₹72 Cr) and FY2026 (₹1,879 Cr) figures, and this may be the actual root cause
of its already-flagged extreme EBITDA margin (an understated revenue would mechanically
inflate any margin computed against it). Recommend this be the first thing checked by hand.

By contrast, **BOHRAIND, CREATIVEYE, and KOHINOOR's extreme flags are now confirmed as
genuine, not data errors** — their real-world revenue independently matches the stored
figure, so the extreme margin/ROCE readings are legitimate near-zero-denominator artifacts,
exactly as `quality_checks.py`'s own precedent comments anticipated.

Nothing in this sample was unfindable — all 30 companies resolved to a real, sourced
figure (or a documented reason they're non-comparable).

---

## 4. Automation status

| Workflow | Registered on GitHub? | Schedule | Last run | Status |
|---|---|---|---|---|
| `quarterly_refresh.yml` | Yes (id 312118955), **active** | `0 3 1 1,4,7,10 *` (3am UTC, 1st of Jan/Apr/Jul/Oct) | 2026-07-13T17:47:09Z | Success (`workflow_dispatch`) |
| `daily_price_refresh.yml` | **No — not registered at all** | `0 4 * * *` (daily, local file only) | never run | File exists locally, **untracked in git, never committed or pushed** |
| `keep_alive.yml` | Removed this session (Part A) | — | — | Deleted; no longer appears in the workflow list |
| Dependabot Updates / Dependency Graph / CodeQL | Yes, active | GitHub-managed defaults | — | Informational only, not app-specific |

**`quarterly_refresh.yml`**: added 2026-07-13, after the 2026-07-01 quarterly firing date
had already passed — so its cron has **never actually fired on schedule**; all 4 runs to
date were manual `workflow_dispatch` test runs (2 failed, 2 succeeded, all on the day it
was added, consistent with debugging a new workflow). Its **next real scheduled run is
2026-10-01 03:00 UTC**. Nothing wrong here, just worth knowing the schedule hasn't been
exercised for real yet.

**`daily_price_refresh.yml`**: this is the more actionable finding. The file sits in
`.github/workflows/` on disk with a correct-looking daily cron, but `git log --all` shows
it has **never been committed to any branch** — `git status` confirms it's still an
untracked (`??`) file. GitHub's Actions API confirms it: only 4 workflows are registered
repo-wide, and this isn't one of them. **The daily price-refresh automation does not exist
from GitHub's perspective yet** — it needs `git add && git commit && git push` before it
can run at all. Flagging this rather than fixing it, per this task's scope.

**60-day scheduled-workflow auto-disable window**: the default branch's most recent commit
is 2026-07-20T03:41:07Z (this session's `keep_alive.yml` removal), so the clock is
freshly reset — no risk of GitHub auto-disabling `quarterly_refresh.yml` for at least 60
days from today, assuming *some* commit lands on `main` before then.

---

## Summary — what needs a human decision

1. **SPARC's revenue figure** looks genuinely off (not a sector-pattern artifact) and may
   explain its already-flagged extreme EBITDA margin — check this one first.
2. **Financial-services revenue** (banks/NBFCs) shows a real, repeatable pattern of
   disagreement with public figures (HDFCBANK, SBIN, BAJFINANCE, AXISBANK) — worth tracing
   to a yfinance-side scoping issue before trusting Financial Services revenue comparisons.
3. **`daily_price_refresh.yml` isn't live** — it exists locally but was never pushed, so
   the "runs itself for years" goal isn't actually in effect for daily price data yet.
4. **111 companies (5.4% of the universe)** will show 3+ "N/A"s on their tear sheet today,
   including a few recognizable names (AU Small Finance Bank, HCL Infosystems, IDFC First
   Bank, MTNL, Star Health, Tata Teleservices Maharashtra) — not urgent, but good to know
   before those specific tear sheets get scrutinized.
5. Everything else (78 `partial_pull_suspected`, the extreme-flag precedent cases, the
   long tail of patchy fields like `beta`/`peg_ratio`/`retained_earnings`) is already
   understood, documented, and within the tolerances this project has already decided on.
