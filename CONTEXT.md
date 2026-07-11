# NSE M&A Target Screening & Valuation Tool — Project Context Anchor

**One-sentence purpose:** A free, public web tool that lets recruiters and hiring managers at corp dev / corporate finance / Big 4 deal advisory teams filter, weight-score, and value ~2,046 real NSE-listed Indian companies as M&A targets — built by Ram (B.Com + ACCA student, graduating 2027) to demonstrate deal-screening and valuation skills for job applications.

Repo: https://github.com/RAM-cybe/nse-ma-target-screener (public)

---

## Tech Stack (locked)

- Python 3.10
- Streamlit (single-file app, `app.py` at repo root — not yet written)
- pandas for all data handling
- Bundled CSVs as the only data source — no database, no live feeds
- Gemini API (free tier) for the tear sheet's AI rationale text only
- Hosting: Streamlit Community Cloud (free), deployed from the GitHub repo above
- Version control: git, one commit per module gate passed

---

## Build Status

### Built and verified (independently re-checked against real data, not just self-reported)

| Module | What it does | Files | Commit |
|---|---|---|---|
| 1 — Data layer | Loads and validates both CSVs, classifies every company into one of EY's 6 sector buckets (+ Unclassified) | `src/data/schema.py`, `sector_mapping.py`, `loaders.py` | `0dd6aad` |
| 2 — Business logic | 7-field filtering (NaN always passes a filter, never hides a company for missing data), sector-relative percentile weighted scoring (4 sliders, debt inverted, missing metrics reweight automatically) | `src/logic/filtering.py`, `scoring.py` | `2f7a096` |
| Data fix — net_income | Added Net Income column via yfinance for P/E valuation | `companies_full_v2.csv`, `schema.py` | `8bafe41` |
| Data fix — currency bug | Found and fixed: Yahoo reports some companies' financial-statement fields (revenue/EBITDA/debt/net income — not market cap) in USD instead of INR when `financialCurrency != INR`. 18 companies affected (2 confirmed, e.g. Infosys and HCL Tech; 16 unconfirmed/blanked defensively). Fixed by blanking those fields for affected companies rather than guessing an FX conversion. | `companies_full_v2.csv` | `4743a27` |
| 3 — Valuation range | Sector-relative EV/EBITDA and P/E-implied valuation ranges (25th/75th percentile peer multiples, min 3 qualifying peers, null with a reason when data is insufficient) | `src/logic/valuation.py` | `feb446d` |
| Infrastructure | Public GitHub repo, `.gitignore` (excludes secrets, raw PDFs, superseded data files, one-time scripts), Gemini API key handling (`src/config.py`: tries Streamlit Secrets first, falls back to local `.env`) | `.gitignore`, `src/config.py` | included above |
| 4 — UI | `app.py`: sidebar (7 filters + 4 weight sliders), ranked table (`st.dataframe`, virtualized for 2,046 rows), tear sheet (all 6 PRD sections), query-param state restore, stubbed `get_ai_rationale()` (always None, PRD fallback text rendered, `# TODO: Module 5` marker). Built against the approved mockup ("MA Screener - Design Options.dc.html"). Full PRD acceptance criteria run (see below) plus edge-case and security checks. | `app.py`, `.streamlit/config.toml`, `requirements.txt` | see commit hash in next session's log |

**Row-click diagnosis (resolved)**: root cause found via a minimal isolated reproduction and Streamlit 1.35.0 source inspection — `st.dataframe` row selection requires clicking a narrow, hover-revealed checkbox column to the left of the data cells; clicking the data cells themselves (company name, rank, etc.) only sets cell-navigation focus, a different concept from Streamlit's selection state. `app.py`'s `event.selection.get("rows")` usage is correct and matches the documented API exactly. Confirmed working end-to-end via a real local Chrome browser (not a sandboxed tool) in the isolated repro; precisely automating a click on that narrow target within the real app's tighter column layout was not achieved within this session's tooling, so final end-to-end confirmation needs one manual click from a real user.

**Bug found and fixed this session**: the "Reset all filters" button (both the sidebar version and the zero-results-state version) cleared query-param keys using stale short aliases (`roce`, `debt`, `mcap`) left over from an earlier fix that renamed the actual keys to full field names (`return_on_capital_employed_pct`, `total_debt`, `market_cap`). Reset silently failed to clear 3 of 5 range filters. Fixed by introducing one shared `FILTER_QP_KEYS` constant so the write side (`sync_query_params`) and both reset call sites can't drift apart again. Verified fixed via direct reproduction (set the 3 affected filters, click Reset, confirm the URL clears all of them).

**PRD acceptance criteria (section 8), run in a real local Chrome browser this session:**

| # | Criterion | Result |
|---|---|---|
| 1 | Loads within ~3s, all companies ranked by default score | PASS — data pipeline measured at ~0.13s compute, cached via `st.cache_data` |
| 2 | 4 weight sliders adjust rankings live, no page reload | PASS — confirmed via real slider interaction, full re-rank observed |
| 3 | All 7 filters work independently and combined | PASS — confirmed via real interaction + URL round-trip |
| 4 | Zero-result state: message + Reset button | PASS — exact PRD wording; Reset bug found and fixed (see above) |
| 5 | Row click opens tear sheet, 6 sections in order | Content/order verified PASS (3 companies checked); click mechanism diagnosed correct but not automation-confirmed end-to-end — see row-click note above |
| 6 | Valuation range shows both EV/EBITDA and P/E (or reason) | PASS — TCS (both present), HCLTECH (both correctly null with specific reasons) |
| 7 | AI rationale across 10+ companies, multiple sectors | NOT YET — Module 5 scope, not built this phase by design |
| 8 | AI rationale failure path non-blocking | PASS — currently exercised 100% of the time (stub), confirmed non-blocking on 3 tear sheets |
| 9 | Sector mapping ≥90% non-Unclassified | PASS — 96.38% companies, 99.45% deals |
| 10 | Desktop Chrome + mobile, no crashes | PASS — both viewport sizes confirmed, table and tear sheet render without crashing on mobile (375×812) |
| 11 | Publicly reachable on Streamlit Community Cloud | NOT YET — not deployed, out of this session's scope |

Edge cases tested: zero-result filter combination (real data, not synthetic), extreme negative bounds (revenue/margin/ROCE all have real negative data), a company with heavily currency-fix-blanked data (HCLTECH), and the zero-deal-comps code path (verified by inspection — no real `ey_bucket` currently has zero deals to demonstrate live, all 7 buckets have 4+ deals).

**Composition-order contract (critical, enforced in every module's docstring):** `score_companies()` and `valuation_range()` must always run on the full, unfiltered company universe first — sector-relative percentiles and peer multiples would drift if computed on an already-filtered subset. `filter_companies()` runs last, purely for display, and never feeds back into scoring or valuation.

### Not started

- Module 5: wire the real Gemini API call into the rationale stub, final integration QA
- Full QA pass against every PRD acceptance criterion (section 8) and edge-case testing
- Deploy to Streamlit Community Cloud
- Launch: resume bullet, LinkedIn post, Big 4 outreach

---

## Locked Decisions (do not silently violate these)

- Scope is exactly PRD section 3's two features (Target Screening + Indicative Valuation tear sheet) plus the AI rationale, which ships in Phase 1 per the PRD's own lock — nothing else, no scope additions without explicitly reopening and re-approving the PRD.
- No login, no database, no live price feeds, no payments — bundled CSVs only, refreshed by redeploying.
- No fabricated/estimated data anywhere. A genuine gap is shown as blank/"N/A", never guessed. This rule has already caught two real data bugs (currency contamination, missing net income) — it is the single most important discipline on this project and is not up for relaxing.
- Missing data is never a reason to hide a company from filters or scoring — see the NaN-handling rule in `filtering.py` and `scoring.py`.
- One module per Claude Code session, gate-verified (independently, not just self-reported) and committed before the next module starts.
- Real-time/automated data refresh is explicitly deferred past v1 launch — no free, reliable API exists for bulk Indian company fundamentals at this depth; a manual or lightweight-cron quarterly refresh (using the scripts already built) is the realistic plan, revisited after the app ships.

---

## Known Data Limitations (disclosed honestly, not hidden)

| Field | Population rate | Note |
|---|---|---|
| revenue | 98.92% (2,024 / 2,046) | |
| ebitda | 91.25% (1,867 / 2,046) | |
| total_debt | 97.41% (1,993 / 2,046) | Some genuinely debt-free companies (e.g. TCS) show blank, not zero — that's correct, not a bug |
| net_income | 94.92% (1,942 / 2,046) | Added after v1 data collection; some symbols blanked due to the currency bug fix |
| return_on_capital_employed_pct (ROCE) | 91.74% (1,877 / 2,046) | Blank for companies where Yahoo's balance sheet doesn't expose Current Liabilities (mostly banks/financials) |
| promoter_pledge_pct | 95.21% (1,948 / 2,046) | Blank = not disclosed, not necessarily zero |

Universe: 2,046 NSE-listed companies (from a starting list of 2,047; one permanent yfinance failure). 727 M&A deals (2006–2025) from EY, Grant Thornton, KPMG, PwC, Deloitte, Bain, Dhruva, Nishith Desai, and Roedl reports — 99.4% sector-classified, only 4 genuinely Unclassified.

Sector distribution (companies): Industrials and Auto 956, Consumer Products and Retail 299, Financial Services 220, Technology 193, Infrastructure 157, Lifesciences 147, Unclassified 74.

---

## v1.1 Backlog (post-launch only — do not pull into the locked v1 scope)

Sourced from a multi-AI research pass, filtered for what's genuinely free, low-risk, and actually consistent with this project's discipline (verified, not taken at face value — see notes):

- GitHub Actions weekly automated data refresh (verified: public repos get unlimited free Actions minutes in 2026). Directly fulfills the refresh plan already noted above.
- A short methodology/limitations page — how sector-relative scoring works, data population rates, known gaps. Near-zero cost, high credibility value.
- "Interview/practice mode" — an optional toggle that hides the company name and asks the user to reason from the metrics first. Cheap, differentiated, ties directly to the project's actual purpose.
- Rejected/deferred: multi-provider LLM fallback chain (see the corrected quota note below — even at the real, much tighter quota, per-company caching already solves the practical problem; adding a second provider is still out of scope per the locked stack), Parquet migration (unnecessary at 2,046 rows, conflicts with the PRD's "bundled CSVs" wording), streamlit-AgGrid, Hugging Face Spaces mirror deploy, screener.in scraping (source's own ToS restricts this), DCF-lite, deal-comp transaction multiples, embeddings-based "similar companies," news feed.

**Correction (Module 5 build session): the "1,500 requests/day" Gemini free-tier figure above was wrong.** Real API testing during Module 5 hit `429 RESOURCE_EXHAUSTED` after ~16-17 calls in one session, across three different models (`gemini-3.5-flash`, `gemini-2.0-flash`, `gemini-2.0-flash-lite`) — the actual free-tier daily quota is on the order of 20 requests/day per model, not 1,500. The earlier figure was apparently stale or mis-scoped research, stated as "verified" when it wasn't actually checked against a live account. This makes per-company disk caching (already built, keyed by symbol + as_of_date) load-bearing, not just a nice-to-have: once the daily quota is hit, every *new* company click correctly falls back to the PRD's exact "AI rationale unavailable" text until quota resets, which is graceful and expected, not a bug.

## Today's Focus

Module 4 (Streamlit UI) is built: pipeline in the correct composition order (score + value on full universe, then filter for display) wrapped in `st.cache_data`, sidebar with all 7 filters and 4 weight sliders, ranked table with row-click to a tear sheet, tear sheet with all 6 PRD-specified sections in order, exact PRD error-state messages, and a stubbed AI rationale function so Module 5 only has to wire in the real Gemini call. Also includes two items already anticipated in PRD section 9's MoSCoW list (Should/Could have), promoted into this build because they're zero-cost and zero scope-risk: CSV export of the current filtered/ranked table, and shareable URL query params for the current filter/weight state. No PRD edit was needed for either — they were already written into the locked scope, just not yet built. See the Build Status table's Module 4 note on what was and wasn't independently click-tested.

A multi-AI research pass on "how to make this better" was reviewed and mostly rejected as premature (see "v1.1 Backlog" above) — the one verified, genuinely free, zero-risk idea (GitHub Actions weekly data refresh) was already the agreed post-launch plan before the research, just now confirmed technically real.

Module 5 caches each company's AI rationale after first generation (keyed by symbol + as_of_date) — this is now known to matter more than originally assumed; see the corrected quota note in the v1.1 Backlog section above (real quota is ~20 requests/day/model, not 1,500).

Final QA (task before deploy) follows the full protocol already defined in this project's build discipline: every PRD acceptance criterion run and marked PASS/FAIL, deliberate edge-case testing (malformed/empty/extreme inputs), a security check that no API key is exposed anywhere in the repo or client-side code, and a "stranger test" — a fresh session explains the codebase back using only CONTEXT.md, to confirm the documentation is actually sufficient.

---

## Full PRD (locked scope — paste this in full at the start of every future session)

# PRD — M&A Target Screening & Valuation Tool

## LOCKED SCOPE

- Two features only: (1) Target Screening — filter, score, and rank ~300–500 NSE-listed companies (in practice, the real dataset covers all 2,046); (2) Indicative Valuation ("the offer") — a sector-multiple-based valuation range per company.
- Everything else in the real M&A process — due diligence, negotiation, legal approval, integration — is explicitly out of scope and will not be simulated in any form.
- Single-file Streamlit (Python) app, free hosting on Streamlit Community Cloud, data as two bundled CSVs, no login, no database, no live price feeds, no payments, no native mobile app.
- Desktop is the primary target; mobile browsers must not break, but are not a design priority.
- The AI-drafted tear sheet rationale (Gemini) ships in Phase 1, not deferred.
- Timeline is a soft estimate, not a hard deadline — quality takes priority over speed, but Phase 1 must still land as a complete, coherent, working v1 before any further polish is layered on.

## 1. Purpose Statement

A free web tool that lets a user filter and rank NSE-listed Indian companies by a self-weighted score, then view a one-page tear sheet for any ranked company showing its key financials, an indicative M&A valuation range, an AI-drafted rationale, and comparable Indian M&A deals in its sector.

## 2. Users and Context

- Primary real-world audience: recruiters and hiring managers at corporate development, corporate finance, or Big 4 deal advisory teams, viewing this as a portfolio/demo link — most likely on a laptop, for a few minutes, with zero instructions.
- Secondary user: Ram himself, using it to demonstrate and practice target-screening logic.
- Usage pattern: occasional/demo use, not a daily-use or monitoring tool.
- Device: desktop/laptop browser is the design target; mobile browsers must remain functional (no crashes, no cut-off controls) even if visually tighter.
- No account, setup, or technical knowledge required to use it — the public link loads directly into a working state.

## 3. Core Features (Phase 1 — max 5)

**(1) Filtering & Screening** — Sector (multi-select, EY 6 buckets + Unclassified), Revenue (range), EBITDA Margin % (range), ROCE % (range), Total Debt (range), Market Cap (range), Promoter Pledge % (ceiling).

**(2) Weighted Live Scoring** — 4 independent 0–10 weight sliders: Revenue Growth, EBITDA Margin, ROCE, Debt Level. Each company's raw metrics are converted to a sector-relative percentile (ranked against peers in the same EY sector bucket, not the whole dataset). Final Score = normalized weighted blend of the 4 percentiles, recalculated live on every slider move. Promoter Pledge % and Market Cap are filters only — never factor into the Score.

**(3) Ranked Results Table** — Default view on load: all companies, default equal weights, sorted by Score descending. Updates live as filters or weights change.

**(4) Company Tear Sheet** — In order: (1) Company header — name, sector, market cap; (2) Score badge + breakdown by the 4 weighted factors; (3) Key financials table; (4) Valuation range — sector median EV/EBITDA and P/E multiples applied to the company's own numbers, shown as a range, purely mechanical with no subjective/risk adjustments; (5) AI-drafted rationale — one paragraph via Gemini, ships in Phase 1; (6) Comparable deals — up to 5 most recent deals in the same EY sector bucket.

**(5) Sector-Matched Deal Comps** — Powered by the build-time sector classification. Used for deal-history context only — never used to derive valuation multiples.

## 4. Non-Functional Requirements

- Initial load renders the full ranked table within ~2–3 seconds on a typical broadband connection.
- Must handle the full dataset without noticeable lag when filtering, reweighting, or re-sorting.
- Requires an active internet connection at all times — no offline mode.
- Desktop-first responsive layout; mobile browsers remain functional even if visually cramped.
- No authentication and no app-level rate limiting; Gemini's own free-tier limits are handled via graceful fallback.

## 5. Data Schema

**Company CSV** (`companies_full_v2.csv`, real column names): symbol, name, sector, industry, revenue, ebitda, ebitda_margin_pct, total_debt, market_cap, insider_holding_pct, revenue_growth_pct, return_on_equity_pct, status, return_on_capital_employed_pct, promoter_pledge_pct, as_of_date, net_income.

If a required column is entirely absent, the app still runs — that metric is treated as unavailable for all companies (shown as "N/A", excluded from scoring) rather than crashing.

**Deals CSV** (`deals_full_v2.csv`, real column names): month, target, acquirer, sector_raw, deal_value_usdm, deal_type, stake_pct, ey_bucket, source_report, report_year.

## 6. Explicit Exclusions

No login or accounts. No database. No live price feeds (all financials static as of `as_of_date`, clearly labeled in the UI). No payments. No native mobile app. No saved sessions or user-specific history. No due diligence, negotiation, legal, or integration workflow steps. No editing of underlying data through the UI.

## 7. Error States (exact messages)

| Failure | Message shown |
|---|---|
| Zero filter results | "No companies match these filters. Try widening your ranges." + [Reset Filters] button |
| Missing metric for a company | Cell shows "N/A"; company excluded only from that metric's score contribution |
| No deal comps for a sector | "No comparable 2025 Indian M&A deals found in this sector." |
| AI rationale fails/times out | "AI rationale unavailable right now — the rest of this tear sheet is unaffected." |
| Required CSV column missing entirely | Build/test-time warning only |

## 8. Acceptance Criteria

- [ ] App loads within ~3 seconds, showing all companies ranked by default score
- [ ] All 4 weight sliders adjust rankings live, no page reload
- [ ] All 7 filter fields work independently and in combination
- [ ] Zero-result filter state shows the friendly message + reset button, never a blank/broken screen
- [ ] Clicking any company opens its tear sheet with all 6 content sections present, in the defined order
- [ ] Tear sheet valuation range shows both EV/EBITDA and P/E-implied figures (or a clear reason when one/both can't be computed)
- [ ] AI rationale generates successfully across a test sample of 10+ companies spanning different sectors
- [ ] AI rationale failure path tested and confirmed non-blocking
- [ ] Sector mapping correctly assigns at least 90% of companies to a non-empty EY bucket (actual: 99.4% on deals, ~96%+ on companies)
- [ ] Tested on desktop Chrome and one mobile browser with no crashes
- [ ] Publicly reachable on Streamlit Community Cloud with no login required

## 9. MoSCoW Cut

**Must have (Phase 1):** Full ranked table, all 7 filters, 4-slider live weighted scoring, full tear sheet, all graceful error handling.

**Should have (fast-follow):** Visual polish, CSV export of the current filtered/ranked shortlist.

**Could have (only if time allows):** Shareable filter presets via URL parameters, a short "how this works" panel.

**Won't have:** Login/accounts/saved sessions, native mobile app, live price feeds, payments, any due diligence/negotiation/legal/integration features.
