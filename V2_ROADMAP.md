# NSE M&A Target Screener — v2 Roadmap (research phase, nothing built yet)

Status: **Planning only.** No code, data, or CSV changes have been made. This document
captures everything agreed across this session's research + clarifying-question rounds,
so it can be reviewed, revised, and then executed module-by-module, one command at a time —
same discipline as v1 (CONTEXT.md).

---

## 1. Data layer expansion

**New fields to add** (all pulled the same way as current data — yfinance `.info`,
same tech stack, no new source):

| Group | Fields | Why |
|---|---|---|
| Liquidity & leverage | current ratio, interest coverage ratio, net debt/EBITDA | Real screens use net debt/EBITDA <3x as the standard leverage ceiling — more precise than raw total debt alone |
| Cash flow quality | free cash flow, FCF yield, operating cash flow | Catches companies with good EBITDA margin but weak cash conversion |
| Valuation context | PEG ratio, EV/Revenue, price/book | Extra multiples for the tear sheet and valuation module beyond EV/EBITDA and P/E |
| Ownership/risk depth | FII/DII institutional holding %, beta | Who else holds the stock, and its volatility |
| Distress/quality models | Altman Z-Score, Piotroski F-Score (see §5) | Standard, transparent, formula-based — not black-box |

New fields become **filters first**; the existing 4-factor weighted score is left untouched
this round (revisit once the new fields are proven populated well).

## 2. Data quality — the honest ceiling

- No free bulk API exists for primary-source XBRL filings at 2,046-company scale (checked
  NSE and BSE directly — individual filings exist, no bulk endpoint). A full primary-source
  audit of the whole universe is not a real free option.
- What's real and worth doing instead:
  1. The field expansion above.
  2. **Automated sanity-check rules** built into the refresh pipeline — range checks
     (e.g. margin >100%, negative revenue where impossible), cross-field consistency checks,
     stale `as_of_date` flags. Systematizes the same discipline that already caught the
     currency bug and missing net_income.
  3. **Stratified manual spot-audit** — 30–50 companies across sectors/market-cap bands,
     checked by hand against their actual NSE/BSE filings. Methodology and match rate
     published openly (feeds the provenance panel, §4).

## 3. Refresh architecture

- **Fundamentals**: full quarterly batch refresh via GitHub Actions (confirmed free,
  unlimited minutes on public repos). Matches real disclosure cycles — fundamentals don't
  move week to week, so this isn't a compromise.
- **Price / market cap**: refreshed on a lighter, more frequent cadence between quarters.
- **Fast-follow, not this phase**: per-company refresh triggered off each company's actual
  results date (yfinance exposes earnings-date data) — more precise, more moving parts.
  Ship the simpler all-companies quarterly batch first.
- **History**: every quarterly run writes a **dated snapshot**, not an overwrite. This is
  what makes trend-based flags (§5, §6) real instead of guessed.
- Operational note: GitHub Actions auto-disables scheduled workflows after 60 days of
  repo inactivity — needs a periodic commit or manual reactivation.

## 4. News & filings — three sourced buckets

| Bucket | Source | Status |
|---|---|---|
| Official corporate filings | NSE + BSE's own official RSS feeds (`nseindia.com/static/rss-feed`, `bseindia.com/rss-feed.html`) | Confirmed free, sanctioned |
| General / sector / government news | Google News RSS by query (`news.google.com/rss/search?q=...`) | Free, no auth, capped ~100 items/query, skews a few days old |
| Analyst ratings/research notes | — | **No free legal bulk source exists** (Trendlyne, Refinitiv etc. are paid). Dropped, not faked. |

Hard rule carried over from v1: **no scraping of nseindia.com's own pages** — their Terms
of Use explicitly forbid automated collection regardless of what robots.txt allows. RSS
feeds only, same category discipline that already ruled out screener.in.

Every news/filing item shown must carry its real source and a link out.

## 5. Qualitative signal — the honest replacement for "news judgment"

Instead of AI sentiment scoring (which would be exactly the fabricated-qualitative-score
problem v1 correctly ruled out), use **SEBI's own Regulation 30 disclosure taxonomy**:
every NSE/BSE filing is legally required to carry an official category (order wins, credit
rating actions, litigation, auditor resignation, related-party transactions, insolvency,
fraud, regulatory action). Tag filings by that real, legally-defined category. Same signal
value as "judge it from the news," zero invented judgment, more defensible than sentiment.

**Famous evaluation models — feasibility:**

| Model | What it measures | Feasibility |
|---|---|---|
| **Altman Z-Score** | Bankruptcy/distress risk | Buildable — needs 3 new fields (total assets, retained earnings, working capital) added to the pull. Formula is standard and transparent, no hidden assumptions. |
| **Piotroski F-Score** | 9-point fundamental strength score | Highly complementary — mostly derivable from fields already in scope (ROA, cash flow vs net income, leverage change, current ratio change, margin change, asset turnover change). Needs prior-period comparison, which the new quarterly snapshot history (§3) unlocks. |
| **Beneish M-Score** | Earnings-manipulation/fraud risk | Most "impressive" to a Big 4 audience (real post-scandal relevance in India), but heaviest data lift — needs accrual and receivables-growth fields not currently in scope. **Stretch goal, feasibility unconfirmed** until checked field-by-field against yfinance coverage. |

Every qualitative flag on the term sheet (§6) must trace to one of: a real number, a
real trend (from snapshot history), or a real filing category — never an invented score.

*Note: "Code 33" wasn't a model I could match to anything standard — flag it back to me
(e.g. Beneish M-Score? Ohlson O-Score? something else?) and I'll fold it in.*

## 6. Term sheet — new tear-sheet output

- Formats: **PDF and Excel**, both.
- One standardized skeleton for every company (price range, structure, escrow %,
  indemnity cap, CCI/SEBI/RBI conditions precedent — all generic, market-standard,
  clearly labeled illustrative/non-binding), auto-filled per company with:
  - Its own mechanical valuation range (existing v1 output)
  - Real derived flags: promoter pledge level/trend, insider holding trend, debt/margin
    trend, Reg 30 filing-category flags, sector M&A intensity from the 727-deal dataset,
    Altman Z / Piotroski F scores once built
- Never invents a company-specific legal term (escrow %, indemnity cap) — those stay
  generic/market-standard across all companies, same document skeleton.

## 7. Bonus features (this build cycle)

- **Data provenance/audit panel** — refresh dates, spot-audit results (§2.3), known gaps,
  per company, in-app. Highest credibility-per-effort of everything discussed.
- **Side-by-side company compare** — 2–3 companies, one view.
- **Sector dashboard** — visual deal intensity + multiples per EY sector bucket, from the
  existing 727-deal dataset.
- **Practice/interview mode** (from v1.1 backlog) — hides the company name, user screens
  from metrics alone. More valuable now with richer data.
- Methodology/limitations page (carried over from v1.1 backlog, now more load-bearing
  given the added depth).

## 8. Build order — open

Not yet fixed. Natural dependency chain: data fields + history snapshots unlock everything
downstream (trend flags, Piotroski, provenance panel), so they're the logical foundation —
but final sequencing is a separate command, not decided in this document.

---

**Nothing in this document has been implemented.** Next step is your call: approve/edit
this plan, then name the first module to build.
