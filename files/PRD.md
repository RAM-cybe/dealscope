# PRD — M&A Target Screening & Valuation Tool
*(working name — rename as you like)*

---

## 🔒 LOCKED SCOPE

- **Two features only:** (1) Target Screening — filter, score, and rank ~300–500 NSE-listed companies; (2) Indicative Valuation ("the offer") — a sector-multiple-based valuation range per company.
- Everything else in the real M&A process — due diligence, negotiation, legal approval, integration — is explicitly **out of scope** and will not be simulated in any form.
- Single-file Streamlit (Python) app, free hosting on Streamlit Community Cloud, data as two bundled CSVs, no login, no database, no live price feeds, no payments, no native mobile app.
- Desktop is the primary target; mobile browsers must not break, but are not a design priority.
- The AI-drafted tear sheet rationale (Gemini) **ships in Phase 1**, not deferred.
- Timeline is a soft estimate, not a hard deadline — quality takes priority over speed, but Phase 1 must still land as a complete, coherent, working v1 before any further polish is layered on.

---

## 1. Purpose Statement

A free web tool that lets a user filter and rank ~300–500 NSE-listed Indian companies by a self-weighted score, then view a one-page tear sheet for any ranked company showing its key financials, an indicative M&A valuation range, an AI-drafted rationale, and comparable 2025 Indian M&A deals in its sector.

## 2. Users and Context

- **Primary real-world audience:** recruiters and hiring managers at corporate development, corporate finance, or Big 4 deal advisory teams, viewing this as a portfolio/demo link — most likely on a laptop, for a few minutes, with zero instructions.
- **Secondary user:** Ram himself, using it to demonstrate and practice target-screening logic.
- **Usage pattern:** occasional/demo use, not a daily-use or monitoring tool.
- **Device:** desktop/laptop browser is the design target; mobile browsers must remain functional (no crashes, no cut-off controls) even if visually tighter.
- No account, setup, or technical knowledge required to use it — the public link loads directly into a working state.

## 3. Core Features (Phase 1 — max 5)

**(1) Filtering & Screening**
Fields and input types:
- Sector — multi-select dropdown (based on raw Screener industry labels)
- Revenue — numeric range slider (₹ crore)
- EBITDA Margin — numeric range slider (%)
- ROCE — numeric range slider (%)
- Total Debt — numeric range slider (₹ crore)
- Market Cap — numeric range slider (₹ crore)
- Promoter Pledge % — numeric ceiling slider (max acceptable %)

**(2) Weighted Live Scoring**
- 4 independent 0–10 weight sliders: Revenue Growth, EBITDA Margin, ROCE, Debt Level.
- Each company's raw metrics are converted to a sector-relative percentile (ranked against peers in the same EY sector bucket, not the whole dataset).
- Final Score = normalized weighted blend of the 4 percentiles, recalculated live on every slider move.
- Promoter Pledge % and Market Cap are filters only — they never factor into the Score.

**(3) Ranked Results Table**
- Default view on load: all companies, default equal weights, sorted by Score descending.
- Updates live as filters or weights change.

**(4) Company Tear Sheet**
Exact content, in order:
1. Company header — name, sector, market cap
2. Score badge + breakdown by the 4 weighted factors
3. Key financials table — revenue, EBITDA, margin, ROCE, debt, pledge %
4. Valuation range — sector median EV/EBITDA and P/E multiples applied to the company's own numbers, shown as a range (e.g. "₹1,000–1,200 crore"), purely mechanical with no subjective/risk adjustments
5. AI-drafted rationale — one paragraph via Gemini, ships in Phase 1
6. Comparable deals — up to 5 most recent 2025 deals in the same EY sector bucket

**(5) Sector-Matched Deal Comps**
- Powered by the build-time AI-generated SectorMapping file (see BLUEPRINT.md).
- Used for deal-history context only — never used to derive valuation multiples (those come solely from the company dataset itself).

## 4. Non-Functional Requirements

- Initial load renders the full ranked table within ~2–3 seconds on a typical broadband connection.
- Must handle 300–500 rows (scaling gracefully to ~1,000) without noticeable lag when filtering, reweighting, or re-sorting.
- Requires an active internet connection at all times — no offline mode (Streamlit Cloud hosted; live Gemini calls for rationale text).
- Desktop-first responsive layout; mobile browsers remain functional (no crashes, no unreachable buttons) even if visually cramped.
- No authentication and no app-level rate limiting; Gemini's own free-tier limits are handled via the graceful fallback defined in Error States below.

## 5. Data Schema

**Company CSV** (from Screener.in export — exact column names to be confirmed against Ram's real export and adjusted if they differ):

| Field | Type | Required? |
|---|---|---|
| Name | text | Required |
| Industry / Sector | text (raw Screener label) | Required |
| Sales / Revenue | numeric, ₹ crore | Required |
| EBITDA (or derived from Operating Profit) | numeric, ₹ crore | Required |
| OPM % / EBITDA Margin | numeric % | Required |
| ROCE % | numeric % | Required |
| Debt | numeric, ₹ crore | Required |
| Promoter Pledge % | numeric % | Optional (blank/0 if none reported) |
| Market Capitalization | numeric, ₹ crore | Required |

If a required column is entirely absent from the export, the app still runs — that metric is treated as unavailable for all companies (shown as "N/A", excluded from scoring) rather than crashing.

**Deals CSV** (extracted from the EY India M&A Report 2026, matching its own table structure):

| Field | Type | Required? |
|---|---|---|
| Month | text | Optional |
| Target | text | Required |
| Acquirer | text | Required |
| Sector | text | Required |
| Deal Value (US$m) | numeric or "NA" | Required (NA allowed, excluded from calculations, still shown) |
| Deal Type | text (e.g. "M&A – Domestic") | Required |
| Deal Stake % | numeric or "NA" | Optional |

## 6. Explicit Exclusions

No login or accounts. No database (all data in bundled CSVs, refreshed only by redeploying). No live price feeds (all financials static as of export date, clearly labeled with that date in the UI). No payments. No native mobile app — web browser only, desktop-first. No saved sessions or user-specific history. No due diligence, negotiation, legal, or integration workflow steps. No editing of underlying data through the UI.

## 7. Error States (exact messages)

| Failure | Message shown |
|---|---|
| Zero filter results | "No companies match these filters. Try widening your ranges." + [Reset Filters] button |
| Missing metric for a company | Cell shows "N/A"; company excluded only from that metric's score contribution |
| No deal comps for a sector | "No comparable 2025 Indian M&A deals found in this sector." |
| AI rationale fails/times out | "AI rationale unavailable right now — the rest of this tear sheet is unaffected." |
| Required CSV column missing entirely | Build/test-time warning only (data is bundled and tested before each deploy, not a live user-facing error) |

## 8. Acceptance Criteria

- [ ] App loads within ~3 seconds, showing all companies ranked by default score
- [ ] All 4 weight sliders adjust rankings live, no page reload
- [ ] All 7 filter fields work independently and in combination
- [ ] Zero-result filter state shows the friendly message + reset button, never a blank/broken screen
- [ ] Clicking any company opens its tear sheet with all 6 content sections present, in the defined order
- [ ] Tear sheet valuation range shows both EV/EBITDA and P/E-implied figures
- [ ] AI rationale generates successfully across a test sample of 10+ companies spanning different sectors
- [ ] AI rationale failure path tested and confirmed non-blocking
- [ ] Sector mapping correctly assigns at least 90% of companies to a non-empty EY bucket (manually spot-checked before shipping)
- [ ] Tested on desktop Chrome and one mobile browser with no crashes
- [ ] Publicly reachable on Streamlit Community Cloud with no login required

## 9. MoSCoW Cut

**Must have (Phase 1 — the complete v1):**
- Full ranked table, default view on load
- All 7 filters
- 4-slider live weighted scoring, sector-relative percentiles
- Full tear sheet: financials, valuation range, AI rationale, deal comps
- All graceful error/zero-result/missing-data handling defined above

**Should have (fast-follow, once Must Haves are solid):**
- Visual polish (styling, color-coded Score badges, icons)
- CSV export of the current filtered/ranked shortlist

**Could have (only if time genuinely allows):**
- Shareable filter presets via URL parameters
- A short "how this works" panel explaining the scoring/valuation methodology

**Won't have (explicitly out of this build):**
- Login, accounts, or saved sessions
- Native mobile app
- Live price feeds or real-time data refresh
- Payments
- Any due diligence, negotiation, legal, or integration features
