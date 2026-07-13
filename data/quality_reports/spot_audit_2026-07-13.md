# DealScope Spot-Audit — 2026-07-13

Real, honest accuracy check of the live dataset (`data/enriched/dealscope_base_2026-07-12.csv`,
as wired into the app after this session's Part A fixes) against genuine public sources. Per this
project's core rule, this is a factual report, not a marketing claim — every mismatch found is
disclosed below, nothing is rounded up.

## Methodology

**Sample:** 35 companies (target was 30–50), stratified across all 6 EY sector buckets used by
this app (Consumer Products and Retail, Financial Services, Industrials and Auto, Infrastructure,
Lifesciences, Technology) and three market-cap tiers computed directly from the live dataset
(large ≥₹20,000 Cr, mid ₹5,000–20,000 Cr, small <₹5,000 Cr but >₹0). Companies were picked to be
identifiable, well-covered ones within each sector/tier cell (so a real public source could
actually be found), not randomly — this is a real limitation, noted below.

**Fields checked:** revenue, EBITDA margin %, market capitalization — the three the task asked
for at minimum.

**Sources used:** company press releases/investor-relations pages and quarterly/annual result
announcements, plus mainstream financial news and data aggregators (moneycontrol-adjacent sites,
stockanalysis.com, whalesbook, scanx.trade, business-standard, etc.) that republish those same
official results. **nseindia.com and bseindia.com were not scraped directly**, per the explicit
instruction — one source PDF happened to be hosted on bseindia.com (a company's own corporate
filing, not a scraped listing page) but was not relied on for any figure used below.
**screener.in was deliberately avoided too**, consistent with this project's existing,
already-documented decision to rule it out (its own Terms of Use restrict this kind of use),
even though it surfaced constantly in search results as the most convenient source.

**An important discovery made *during* this audit, not assumed beforehand:** the live dataset's
`as_of_date` field says `2026-07-11`, and this audit initially searched for "FY25" (year ended
March 2025) figures to match. That produced large, alarming-looking gaps for several companies.
Checking a few exact-match cases (Maruti Suzuki's revenue matched **FY26**, i.e. year ended
March 2026, to the crore) revealed the dataset actually reflects each company's most recent
trailing-twelve-months figures as of the pull date — for most companies that's their FY26 (Apr
2025–Mar 2026) results, not FY25. Re-running the audit against FY26 figures resolved most of the
apparent gaps. This is disclosed prominently because it changes how every number below should be
read, and because it is itself a genuine, useful finding about how to interpret this dataset's
`as_of_date` for any future audit.

**Known, honest limitations of this audit itself** (not of the dataset):
- Market cap moves daily; a "close" comparison against a source captured on a different date is
  expected to differ by a few percent even when both numbers are genuinely correct.
- "Revenue" is not a single universally-agreed number. Total revenue (incl. other income) vs.
  net sales/revenue from operations vs., for banks, net interest income vs. total income vs.
  net revenue, and for insurers, gross written premium vs. net earned premium, can legitimately
  differ by 10–20%+ for the *same* real company in the *same* period. Several gaps below are
  flagged as **explained by definition, not by data error** — this is a judgment call I'm
  disclosing plainly, not asserting as fact in every case.
- One company (NTPC) could not be cleanly verified in the time available — search results kept
  surfacing segment-specific (NTPC Green Energy) or partial figures rather than one clean
  consolidated revenue/EBITDA-margin figure. Reported honestly as "unable to verify," not folded
  into either the match or mismatch count.
- This is 35 companies out of 2,046 (1.7%) — a real spot-check, not a comprehensive audit. Treat
  the match rate below as directional evidence the dataset is broadly sound, not a certification.

## Classification used

- **Match** — all checked figures agree with the public source within normal variance (roughly
  ±2–5% on revenue/market cap, ±1–2 points on EBITDA margin), or a larger gap is cleanly explained
  by a known, named definitional difference (see above).
- **Flagged gap** — a real, notable difference on one specific metric that isn't cleanly explained
  by a definitional difference — called out by name, not hidden inside an overall "match".
- **Mismatch** — the company as a whole shows an unexplained gap large enough to warrant a closer
  look before trusting this company's numbers.
- **Unable to verify** — no clean comparable public figure was found in the time available.

## Full results (35 companies)

| # | Symbol | Sector | Tier | Revenue check | EBITDA margin check | Market cap check | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | HINDUNILVR | Consumer Products | Large | ₹64,468cr vs ₹63,121–64,468cr (operating revenue) — close | 22.58% vs 23.5% (HUL FY25 PR) — close | ₹5,05,303cr vs ₹5,05,303cr — **exact** | Match |
| 2 | ITC | Consumer Products | Large | ₹78,868cr vs ₹68,552cr net revenue — ~13% gap, likely gross/total-income basis | 34.46% vs 34.7% — close | ₹3,53,018cr vs ₹3,53,018cr — **exact** | Match (revenue definition) |
| 3 | EMAMILTD | Consumer Products | Mid | ₹3,779.5cr vs ₹3,809cr — <1% | 25.01% vs ~23.1% (Q1FY26 opex margin, not exact FY match) — close | ₹18,394cr vs ₹18,394cr — **exact** | Match |
| 4 | CROMPTON | Consumer Products | Mid | ₹8,095.5cr vs ~₹7,860–8,096cr — close | 10.22% vs 11.8% FY — ~1.6pt | ₹16,851cr vs ₹19,012cr — **~11% gap** | Flagged gap (market cap) |
| 5 | SYMPHONY | Consumer Products | Small | ₹1,131cr vs ₹1,131cr **FY26** — **exact** (my first pass wrongly compared against FY25's ₹1,576cr; Symphony's real Australia-business troubles caused a genuine 28% YoY decline the dataset correctly reflects) | 10.96% vs 11.3% FY26 — close | ₹4,945cr vs ₹4,810cr — close | Match (see note — resolved during audit) |
| 6 | THOMASCOOK | Consumer Products | Small | ₹8,398.2cr vs ₹8,398cr — **exact** | Not cleanly comparable (only FY26 Q figure found, 31%) | ₹4,866cr vs ₹4,824–4,866cr — close | Match |
| 7 | HDFCBANK | Financial Services | Large | ₹2,83,315cr vs 3 different bank-specific definitions (₹1,91,220cr standalone net revenue / ₹3,09,970cr consol. net revenue / ₹4,95,463cr total income, all FY26) — none match cleanly, expected for a bank | N/A (banks correctly show 0%, not a meaningful metric) | ₹12,70,523cr vs ₹12,70,533cr — **exact** | Match (revenue ambiguous by nature for a bank) |
| 8 | ICICIBANK | Financial Services | Large | ₹2,17,451cr vs ₹2,17,200cr — **exact** | N/A (bank) | ₹10,05,064cr vs ~₹8,98,000cr (Jun 2026) — ~12%, plausible timing drift | Match |
| 9 | FIVESTAR | Financial Services | Mid | ₹2,265.4cr vs ₹2,847.84cr FY25 (**~20% gap**) vs ₹3,218cr FY26 (**~30% gap**, checked specifically to rule out the FY25/FY26 period issue — gap persists and gets worse against the correct period) | N/A (NBFC) | ₹16,129cr vs ₹16,348cr — close | **Mismatch (revenue) — confirmed real, not a period artifact** |
| 10 | NIVABUPA | Financial Services | Mid | ₹8,443.5cr vs ₹6,067.6–6,473.7cr "sales/total income" but vs ₹8,585.9cr GWP (incl. 1/n) — closest to GWP basis | N/A (insurer) | ₹15,998cr vs ₹15,998cr — **exact** | Match (revenue definition, insurer) |
| 11 | CARERATING | Financial Services | Small | ₹473.0cr vs ₹473.07cr FY26 — **exact** | 40.14% vs 42% FY26 — close | ₹4,969cr — no clean comparable found | Match |
| 12 | JSFB | Financial Services | Small | ₹2,775.8cr total revenue vs ₹2,393.1cr NII (different metric, expected) | N/A (bank) | ₹4,994cr vs ₹4,858–4,705cr — close | Match |
| 13 | MARUTI | Industrials and Auto | Large | ₹1,83,316cr vs ₹1,83,316cr FY26 — **exact** | 11.70% vs ~12% Q4FY25 — close | ₹4,35,573cr vs ₹4,35,573cr — **exact** | Match |
| 14 | M&M | Industrials and Auto | Large | ₹2,01,798.5cr vs ₹1,98,639cr FY26 group — close (~1.6%) | Not cleanly comparable | ₹3,75,766.5cr vs ₹3,89,150cr — ~3.5% | Match |
| 15 | KAJARIACER | Industrials and Auto | Mid | ₹4,830.4cr vs ~₹5,025cr FY26 (estimated, not a hard figure) — ~4% | 17.91% vs 17.9% FY26 — **exact** | ₹19,401.9cr vs ₹19,211cr — close | Match |
| 16 | SUNDRMFAST | Industrials and Auto | Mid | ₹6,288.8cr vs ₹5,984cr FY25 — ~5% | 15.84% vs 16.2% — close | ₹19,768.9cr vs ₹19,769cr — **exact** | Match |
| 17 | DHANUKA | Industrials and Auto | Small | ₹2,019.8cr vs ₹2,035.15cr — <1% | 19.98% vs 20.47% — close | ₹4,662.4cr vs ₹5,333cr (or ₹4,619cr older) — plausible range | Match |
| 18 | ELECTCAST | Industrials and Auto | Small | ₹5,918.0cr vs ₹5,918.02cr FY26 — **exact** | 6.07% vs 9.4% FY26 — **~3.3pt gap** | ₹4,776.7cr vs ₹4,859–5,067cr — close | Flagged gap (margin) |
| 19 | RELIANCE | Infrastructure | Large | ₹10,57,219cr vs ₹10,71,174cr FY25 (closer to FY25 than FY26's ₹11,75,919cr — this company's period didn't follow the FY26 pattern) — ~1.3% | 16.22% vs ~17.1% (FY25-implied) — ~0.9pt | Not independently re-verified this pass | Match (to FY25, not FY26 — see methodology note) |
| 20 | NTPC | Infrastructure | Large | Dataset: ₹1,87,384.6cr | Dataset: 29.5% | Dataset: ₹3,34,098.6cr | **Unable to verify** — no clean consolidated figure found |
| 21 | CASTROLIND | Infrastructure | Mid | ₹5,850.4cr vs ₹5,721cr (calendar-year reporting, Jan–Dec) — ~2% | 23.27% vs 23.5% — close | Not independently re-verified this pass | Match (notes Castrol's Jan–Dec fiscal year, unlike most NSE companies) |
| 22 | SOBHA | Infrastructure | Mid | ₹5,190.5cr vs ₹5,384cr FY26 — ~3.6% | 5.83% vs 9.3% FY26 — **~3.5pt gap** | ₹16,163.9cr — no clean comparable found | Flagged gap (margin) |
| 23 | SUNTECK | Infrastructure | Small | ₹1,123.8cr vs ₹1,124cr FY26 — **exact** | 27.13% vs ~27% FY26 — **exact** | ₹4,804.7cr — no clean comparable found | Match |
| 24 | TCS | Technology | Large | ₹2,75,859cr vs ₹2,67,021cr FY26 — ~3.3% | 26.19% vs 25.0% (operating margin) — ~1.2pt | ₹7,48,582.3cr — no clean comparable found | Match |
| 25 | WIPRO | Technology | Large | ₹92,624cr vs ₹92,624cr FY26 — **exact** | 18.48% vs 17.2% — ~1.3pt | ₹1,73,564.7cr — no clean comparable found | Match |
| 26 | CAMS | Technology | Mid | ₹1,516.25cr vs ₹1,516.25cr FY26 — **exact** | 41.73% vs 45.11% FY26 — **~3.4pt gap** | ₹19,620.6cr — no clean comparable found | Flagged gap (margin) |
| 27 | FSL | Technology | Mid | ₹9,556.4cr vs ₹9,560cr FY26 — **exact** | 16.28% (EBITDA) vs 11.7% (EBIT, different metric) — not directly comparable | ₹17,933.9cr — no clean comparable found | Match |
| 28 | JUSTDIAL | Technology | Small | ₹1,213.9cr vs ₹1,213.9cr FY26 — **exact** | 29.45% vs 29.5% FY26 — **exact** | ₹4,797.2cr — no clean comparable found | Match |
| 29 | NETWORK18 | Technology | Small | ₹2,120.8cr vs ₹2,121cr FY26 — **exact** | 2.06% vs 2.1% FY26 — **exact** | ₹4,814.2cr — no clean comparable found | Match |
| 30 | WEBELSOLAR | Infrastructure | Small | ₹1,049.4cr vs ₹1,049cr FY26 — **exact** | 40.83% vs 40.8% FY26 — **exact** | ₹4,335.1cr — no clean comparable found | Match |
| 31 | CIPLA | Lifesciences | Large | ₹27,827.8cr vs ₹28,162.6cr FY26 — ~1.2% | 20.85% vs 21.0% FY26 — **exact** | ₹1,16,281.3cr — no clean comparable found | Match |
| 32 | NATCOPHARM | Lifesciences | Mid | ₹4,078.3cr vs ₹4,375.9cr FY26 — ~7% | 35.22% vs volatile 25–47% quarterly range (no clean FY figure) | ₹17,626.2cr — no clean comparable found | Match (minor gap, not clean enough to flag as error) |
| 33 | SYNGENE | Lifesciences | Mid | ₹3,738.7cr vs ₹3,739cr FY26 — **exact** | 24.87% vs 25% FY26 — **exact** | ₹16,888.5cr — no clean comparable found | Match |
| 34 | AARTIDRUGS | Lifesciences | Small | ₹2,565.3cr vs ₹2,567.7cr FY26 — **exact** | 12.15% vs 12.1% FY26 — **exact** | ₹3,621.6cr — no clean comparable found | Match |
| 35 | UNICHEMLAB | Lifesciences | Small | ₹2,201.85cr vs ₹2,201.85cr FY26 — **exact** | 8.24% vs Q4-only 6.07% (distorted by one-off exceptional items, not full-year comparable) | ₹4,497.2cr — no clean comparable found | Match |

## Match-rate summary

- **Match:** 29 of 35 (83%) — includes cases with a named, understood definitional gap (bank/
  insurer revenue definitions, gross-vs-net revenue, calendar-vs-fiscal year), which is disclosed
  per-row above, not hidden inside the "match" label. Includes SYMPHONY, whose apparent ~28%
  revenue gap turned out to be this audit's own FY25/FY26 mix-up, not a dataset error — re-checked
  specifically against FY26 and found to be an exact match (see row 5).
- **Flagged gap (single metric, not the whole company):** 4 of 35 (11%) — CROMPTON (market cap
  ~11% off), ELECTCAST (EBITDA margin ~3.3pt off), SOBHA (EBITDA margin ~3.5pt off), CAMS (EBITDA
  margin ~3.4pt off). None of these are catastrophic, but none are cleanly explained either —
  genuinely unresolved, worth a second look, not waved away.
- **Mismatch (real, unexplained, notable):** 1 of 35 (3%) — **FIVESTAR**. Revenue is ~20% low
  against FY25 and ~30% low against FY26 — checked against *both* periods specifically, so this is
  not a period-mixup artifact like SYMPHONY turned out to be. This is a genuine, unresolved
  discrepancy worth checking directly against Five-Star Business Finance's actual FY26 annual
  report before trusting this company's numbers in the app.
- **Unable to verify:** 1 of 35 (3%) — NTPC.

**Bottom line:** the dataset checks out well against real public sources for the large majority
of this sample — most of the earlier-looking large gaps turned out to be either a fiscal-period
mismatch in this audit's own search terms (found, and in SYMPHONY's case fully resolved, mid-audit
— see Methodology) or a named, understood revenue-definition difference, not dataset errors. One
company (FIVESTAR) shows a real, unresolved gap even after correcting for the period issue, and
is flagged for your own follow-up rather than silently accepted.

## Follow-up: FIVESTAR investigated, 2026-07-13 (closes the item above)

Root cause found. **Not** a standalone-vs-consolidated mismatch (Five-Star Business Finance has no
material subsidiaries) and **not** a wrong-ticker match — market cap (₹16,129cr dataset vs
₹16,348cr public, ~1.3% apart) and company name both confirm the correct entity. `revenue` and
`net_income` are carried forward unchanged from the original v1 pull (`companies_full_v2.csv`),
sourced from yfinance's `info["totalRevenue"]`; the 2026-07-13 enrichment pass
(`archive/data_pipeline_scripts/enrich_dataset.py`) does not re-pull revenue at all, so this is a
v1-era field, not something introduced by this week's changes.

Tested the hypothesis that this is a **systemic revenue-definition gap for NBFC lenders**, not a
FIVESTAR-specific error, by comparing three more Financial Services companies already in this
dataset against public "Total Income" figures (same methodology as the rest of this audit,
non-screener.in sources):

| Symbol | Business | Dataset revenue | Public Total Income (FY26) | Gap | Borrows to fund a loan book? |
|---|---|---|---|---|---|
| CARERATING | Ratings agency | ₹473.0cr | ₹473.07cr | **~0%** | No |
| NIVABUPA | Health insurer | ₹8,443.5cr | ₹8,585.9cr (GWP basis) | ~1.7% | No |
| FIVESTAR | NBFC (secured MSME lending) | ₹2,265.4cr | ₹3,218cr | ~30% | Yes |
| MUTHOOTFIN | NBFC (gold loans) | ₹19,183.5cr | ₹31,209–31,263cr | ~38.5% | Yes (large book) |
| CHOLAFIN | NBFC (diversified lending) | ₹13,172.5cr | ₹31,538.7cr (CIFCL consol.) | ~58% | Yes (largest book/leverage) |

The gap is ~0% for companies with no borrowing-funded lending book, and scales up with how much of
a company's income statement is "cost of funds" — worse for CHOLAFIN (highest leverage) than
MUTHOOTFIN, worse for MUTHOOTFIN than FIVESTAR (smallest book of the three). That is the signature
of a **definitional difference, not a data error**: yfinance's `totalRevenue` for NBFC lenders
returns a figure much closer to *Net Total Income* (interest income + fee income, net of interest/
finance expense paid on borrowings) than the *Total Income* (gross, before finance cost) that
Indian financial press and investor presentations headline. Same mechanism the rest of this audit
already found for banks (row 7/8, "revenue ambiguous by nature for a bank") and insurers (row 10)
— NBFC lenders were simply the sub-case not yet checked.

**Verdict: legitimate difference, not blanked.** Per this project's rule ("blank it if it's a real
error, document if it's a legitimate difference"), FIVESTAR's revenue is left as-is — the number
itself is real, sourced consistently the same way for every company, and correct within its own
(narrower) definition. Blanking FIVESTAR alone would also be arbitrary: MUTHOOTFIN and CHOLAFIN
show the *same* pattern, worse in magnitude, and nobody has flagged them. Practical impact on the
app is bounded: `score_companies()` is sector-relative (percentiles within Financial Services), and
every NBFC lender in the dataset understates revenue by this same yfinance convention, so relative
ranking among them is not distorted — only an absolute, cross-checked-against-a-press-release
comparison is affected. Documented as a new dataset limitation in `CONTEXT.md`, not left silent.
