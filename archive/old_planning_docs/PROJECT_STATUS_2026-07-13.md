# DealScope — Full Project Status & Limitations (2026-07-13)

This is an independently verified snapshot, not a self-reported summary. Every claim below was checked against the actual repo, git history, and the raw data files themselves — not taken from any prior session's notes on faith, including the terminal transcript you pasted from the other Claude Code session.

---

## 1. What's actually live and working right now

The public app at **https://dealscope-zei8.onrender.com** is the real v1: two features (Target Screening, Indicative Valuation tear sheet) plus AI rationale, running against `companies_full_v2.csv` and `deals_full_v2.csv`, hosted on Render, repo public at `github.com/RAM-cybe/dealscope`. All 11 PRD acceptance criteria previously passed. This matches what your brief said — confirmed, not just repeated.

Two small things are stale relative to that state, both harmless, neither blocking anything:

- `CONTEXT.md` still says "Hosting: Streamlit Community Cloud" near the top (Tech Stack section) — a leftover from before the Render migration. Cosmetic doc drift, not a functional issue.
- The "Download CSV ↓" button (top-right of the ranked table) sits in a narrow column (`st.columns([4, 1])`, so 1/5 page width) with `use_container_width=True` and an 11px, uppercase, letter-spaced label — a very plausible wrap cause given the layout math, but not confirmed against a live screenshot this session since you redirected me to analysis first.

Neither was touched this session, per your instruction to focus on understanding before fixing.

---

## 2. The big discovery: a substantial, mostly-real Phase 2 data pull already exists — but has one live currency bug and isn't wired in yet

You confirmed you built `data/enriched/dealscope_base_2026-07-12.csv` (+ matching `.parquet`) in a separate Claude Code session yesterday, via a script called `enrich_dataset.py` that currently lives in your home folder, not in the repo. I independently re-verified it from scratch (not trusting the other session's self-report) by reading the raw CSV directly. Here's what's actually true about it.

**It's real and it's a genuine superset of the current schema.** 2,046 rows, same symbol set as `companies_full_v2.csv` exactly (zero symbols added or dropped), every column `app.py`'s `load_companies()` currently requires is present, plus 19 new ones: `total_assets`, `retained_earnings`, `working_capital`, `current_ratio`, `quick_ratio`, `debt_to_equity`, `return_on_assets`, `beta`, `peg_ratio`, `enterprise_value`, `total_cash`, `operating_cash_flow`, `free_cash_flow`, `price_to_book`, `trailing_pe`, `financial_currency`, `currency_flag`, `data_pull_date`, plus a `status` column that's `"ok"` for all 2,046 rows (so it would pass straight through the existing loader's filter unchanged). This is functionally Phase 2's Module D (field expansion) already executed.

**Population rates, independently recomputed from the raw file (not copied from the other session's printout, though they matched when I cross-checked):**

| Field | Populated | Rate |
|---|---|---|
| price_to_book | 2,034 / 2,046 | 99.4% |
| total_cash | 1,991 / 2,046 | 97.3% |
| enterprise_value | 1,988 / 2,046 | 97.2% |
| total_assets | 1,975 / 2,046 | 96.5% |
| operating_cash_flow | 1,925 / 2,046 | 94.1% |
| return_on_assets | 1,918 / 2,046 | 93.7% |
| working_capital | 1,897 / 2,046 | 92.7% |
| current_ratio | 1,895 / 2,046 | 92.6% |
| quick_ratio | 1,894 / 2,046 | 92.6% |
| debt_to_equity | 1,838 / 2,046 | 89.8% |
| beta | 1,793 / 2,046 | 87.6% |
| free_cash_flow | 1,772 / 2,046 | 86.6% |
| trailing_pe | 1,758 / 2,046 | 85.9% |
| **retained_earnings** | 453 / 2,046 | **22.1%** |
| **peg_ratio** | 81 / 2,046 | **4.0%** |

Most new fields are well-populated, in the same 85–99% range as the existing v1 fields. Two are not: `retained_earnings` at 22.1% and `peg_ratio` at 4.0%. `peg_ratio` being nearly absent is expected — PEG needs a forward growth estimate that most mid/small-cap Indian names simply don't have analyst coverage for, and it's a "nice to have" valuation-context field, not load-bearing for anything else. `retained_earnings` at 22.1% is a real problem, addressed below, because it's one of the five required inputs to the standard Altman Z-Score formula your Phase 3 plan depends on.

**The 16 previously-unresolved currency cases from the original v1 bug fix are now cleanly resolved — a genuine improvement, verified.** Back in the v1 currency fix (commit `4743a27`), 16 companies had `financialCurrency` unavailable from Yahoo at the time (rate-limited or genuinely missing) and were defensively blanked across all four financial fields, per the project's "can't confirm INR, so don't guess" rule. I pulled the exact 16 symbols from `_v2_currency_cache.csv` (`3PLAND, CPEDU, ELPROINTL, HBESD, ICDSLTD, JSWDULUX, KNACK, MAFATIND, MODTHREAD, NDGL, NIRAJISPAT, RAJPALAYAM, SHRIKRISH, TECILCHEM, VISL, VOGL`) and checked every one against the new pull: all 16 now report `financial_currency = INR` cleanly. The currency ambiguity is resolved for real — these are just very thinly-covered small-caps where Yahoo genuinely has no revenue/EBITDA/debt/net-income data at all (their financial fields are still blank in the new pull too), which is a coverage gap, not a currency problem. No red flag here.

**The live bug: the currency guard was not extended to the new balance-sheet and cash-flow fields, and Infosys is silently contaminated in exactly the fields the guard doesn't cover.** This is the one finding you need to act on before this file goes anywhere near the app. The new pull's `currency_flag` column correctly identifies the same two companies as before — `INFY` and `HCLTECH` — as `USD_REPORTED`, and correctly blanks their `revenue`, `ebitda`, `total_debt`, and `net_income` (the original four fields the v1 fix already protected). But the guard evidently stops there. I checked the magnitude of the new fields for both flagged companies against a same-scale INR peer (TCS, another large IT services company, `total_assets` = ₹1,82,372 crore):

- **HCLTECH's new fields check out.** `total_assets` = ₹1,16,258 crore — right order of magnitude for a company that size, consistent with genuine INR reporting.
- **INFY's new fields do not check out, and are still populated (not blanked).** `total_assets` = ₹1,644.6 crore — roughly 100x too small for a company of Infosys's actual scale, and almost exactly what you'd get if $16.4 billion (a plausible real total-assets figure for Infosys in USD) were left unlabeled and displayed as if it were raw rupees. Same pattern shows up in `retained_earnings` (₹1,345.9 crore, also implausibly small), `working_capital`, `total_cash`, `operating_cash_flow`, and `free_cash_flow` for INFY specifically. `market_cap` and `enterprise_value`, by contrast, are correctly INR-scaled for INFY (₹4,32,425 crore, a believable figure) — so this isn't a blanket "everything about INFY is wrong," it's specifically the fields sourced from Yahoo's financial-statement/balance-sheet payload that inherit the ADR-driven USD mislabeling, while price-derived fields (which come from the NSE quote, not the financial statements) stay correctly INR.

I also ran a broader scan across the full dataset (total_assets vs. market_cap ratio, flagging anything wildly out of a plausible range for companies with market cap over ₹100 crore) to check whether any other symbols have the same silent contamination without being caught by the `currency_flag` column. Two more names surfaced, but neither looks like a currency issue on inspection: `VAML` has a near-zero `total_assets` (₹0.019 crore against a ₹1,73,169 crore market cap) that's almost certainly a genuine Yahoo data gap/placeholder rather than a unit-mismatch, and `CUPID`'s ratio, while low, is within the range you'd expect for a genuinely asset-light company. Worth a manual glance during the eventual spot-audit (Module G), not urgent.

**Bottom line on this file: it is real, well-populated, and a legitimate advance on Phase 2 — but it is not safe to swap into the app as-is.** Before it becomes the new `companies_full_v2.csv`-equivalent, the currency guard in `enrich_dataset.py` needs to be widened from "blank these 4 fields for flagged symbols" to "blank every financial-statement-and-cash-flow-derived field for flagged symbols" (i.e. add `total_assets`, `retained_earnings`, `working_capital`, `total_cash`, `operating_cash_flow`, `free_cash_flow` to the blank list — leave `market_cap`, `enterprise_value`, `price_to_book`, `beta`, `trailing_pe` alone since those are price-derived and were shown to be correctly scaled). Re-run just the currency-flag logic (not the whole 2,046-company pull) to confirm the fix, then it's ready to actually replace the current data file.

**One more thing worth knowing before Phase 3 gets planned in detail: this pull does not include EBIT or total liabilities as distinct fields.** The standard Altman Z-Score formula needs EBIT specifically (not EBITDA, which this dataset has) and total liabilities (not just total debt) for two of its five terms. Neither is present as its own column here. That's not a blocker — both are standard `yfinance` fields (`ebit` is on the income statement, total liabilities is derivable from `total_assets` minus `total_equity`, or pulled directly) — but it means Module D isn't fully "done" for Altman Z-Score purposes yet; one more small field-addition pass is needed before Module H (the Z-Score itself) can actually be built.

**The generating script and two supporting files live outside the project folder.** `enrich_dataset.py`, `nse_list.csv`, and `Infosys_Clean_Data.xlsx` are all sitting in your Mac's home folder (`~`), per the terminal transcript, not inside `/Users/ram/Downloads/AI-assisted M&A target/`. Only the two output files (`dealscope_base_2026-07-12.csv` / `.parquet`) made it into the project's `data/enriched/` folder. Right now, if that home-folder copy of the script were lost, nobody — including a future Claude session — could regenerate this dataset or even see how the currency guard was implemented, since the repo has zero references to it. This should get copied into the project folder (e.g. `scripts/enrich_dataset.py`) as one of the very next small housekeeping steps, separate from and before the currency-guard fix above.

---

## 3. Full picture of known data limitations (existing + newly found)

| Limitation | Where | Severity |
|---|---|---|
| Currency contamination in new balance-sheet/cash-flow fields for INFY | `data/enriched/...csv`, new fields only | **Needs fixing before this file is used** — see §2 |
| `retained_earnings` only 22.1% populated | same file | Blocks a clean Altman Z-Score without a documented workaround or an alternate source |
| `EBIT` and `total_liabilities` not pulled as distinct fields | same file | Needed to actually build Altman Z-Score; one more small enrichment pass required |
| `peg_ratio` only 4.0% populated | same file | Expected and low-stakes — most Indian mid/small caps lack forward-estimate coverage |
| Generating script lives outside the repo, in `~` | your home folder | Should be moved into the project before it's forgotten or lost |
| 18 companies (2 confirmed + 16 originally-unresolved, now resolved) blanked in v1's core 4 fields | `companies_full_v2.csv` | Already disclosed in `CONTEXT.md`, unchanged, no new issue |
| `revenue` 98.9%, `ebitda` 91.3%, `net_income` 94.9%, `ROCE` 91.7%, `pledge` 95.2% population (v1 fields) | `companies_full_v2.csv` | Already disclosed, unchanged |
| Deal comps: 58% of deals missing `stake_pct`, 11% missing `deal_value_usdm`, `month` mostly NA outside the original EY 2025 set | `deals_full_v2.csv` | Already disclosed in `RESEARCH_SUMMARY.md`, structural limitation of the source reports, not a scraping gap |
| FII/DII institutional split confirmed infeasible via yfinance | n/a | Already correctly dropped from the plan, not re-attempted |
| No automated data-quality-rule pipeline (Module E) exists yet — this session's currency check was done by hand, once | n/a | Real gap — needs to become a repeatable script, not a one-off manual pass |
| No stratified manual spot-audit against real NSE/BSE filings has been done yet (Module G) | n/a | Not started |
| CONTEXT.md still says "Hosting: Streamlit Community Cloud" | `CONTEXT.md` | Cosmetic doc drift |
| Download CSV button possibly wraps oddly | `app.py` UI | Flagged, not confirmed against a live screenshot this session |

---

## 4. Where every phase of the roadmap actually stands

**Phase 0 — Cleanup.** Streamlit Cloud deletion and public-repo decision: done and confirmed. Two loose ends remain exactly as your brief said: the stale `CONTEXT.md` hosting line, and the unconfirmed CSV-button wrap. Automated test suite: still deferred, unchanged.

**Phase 1 — Lock the final feature list on paper.** Not started. Per the roadmap's own instruction, this should happen before any more backend code or the visual redesign — worth doing before diving further into Phase 2/3 work, even though there's now real data-layer momentum pulling attention that direction.

**Phase 2 — Data foundation.** Materially further along than the roadmap assumed, but not "done": the field-expansion half of Module D is functionally complete (pending the EBIT/total-liabilities gap and the currency-guard fix above). Module E (automated data-quality rules as a repeatable pipeline, not a one-off manual check like the one I just did) has not been built. Module F (GitHub Actions quarterly refresh + dated snapshots) has not been built — notably, this new file isn't even snapshotted with history; it would overwrite `companies_full_v2.csv` if swapped in naively, which the eventual refresh architecture is specifically supposed to prevent. Module G (30–50 company manual spot-audit against real filings) has not been done.

**Phase 3 — Smarter analysis.** Not started, correctly blocked on Phase 2 finishing — and now we know concretely what's still missing to unblock it (EBIT, total liabilities, a real fix for retained_earnings coverage or an accepted documented gap).

**Phases 4 through 8** (security/admin layer, term sheet generator, the one UI/UX redesign, final polish, final QA/launch) — all not started, all correctly sequenced after the above, nothing new to report.

---

## 5. What I'd suggest as the next concrete steps, in order

1. Fix the currency guard in `enrich_dataset.py` to cover the new balance-sheet/cash-flow fields, re-run the currency check (not the full pull), confirm INFY's new fields blank out correctly this time.
2. Move `enrich_dataset.py` (and `nse_list.csv` / `Infosys_Clean_Data.xlsx` if you still want them around) from your home folder into the project repo.
3. Add EBIT and total liabilities to the pull — small addition, unblocks Altman Z-Score later.
4. Only then treat `data/enriched/dealscope_base_2026-07-12.csv` as the real Module D deliverable, gate it the same way every other module has been gated (population table published, spot-checked), and decide whether it replaces `companies_full_v2.csv` now or waits for Module F's snapshot architecture first.
5. Separately and not urgently: fix the two Phase 0 loose ends (stale CONTEXT.md line, confirm/fix the CSV button).

None of this has been done yet — this document is the analysis you asked for, not a changelog of new work. Tell me which of the above to actually start on.
