# DealScope — Technical Requirements Document (TRD)

Standalone technical reference, extracted from `CONTEXT.md`'s prose. `CONTEXT.md`
remains the living source of truth and the change-log; this file is the stable
"what's locked and why" reference. Last updated 2026-07-16.

---

## 1. Product in one line

A free, public, login-free web tool that lets corp-dev / corporate-finance /
Big-4 deal-advisory users **filter, weight-score, and get an indicative M&A
valuation** on ~2,046 real NSE-listed Indian companies, plus an AI-drafted
rationale and sector-matched comparable deals per company.

## 2. Tech stack (locked)

| Layer | Choice | Why locked |
|---|---|---|
| Language | Python 3.10 (prod) / 3.11 (local dev) | matches Render's runtime; simple, pandas-native |
| App | Single-file Streamlit app (`app.py`) + `src/` logic package | fast to build, deploys as one process, no separate frontend |
| UI framework | **Streamlit 1.54.0** (pinned) | current; the 1.35→1.54 bump cleared all 16 known CVEs |
| Data handling | pandas 2.2.2 | all transforms are simple column ops |
| Data source | **Bundled CSVs only** — `data/enriched/dealscope_base_2026-07-12.csv` (companies), `deals_full_v2.csv` (deals) | no DB, no live feed; refreshed by redeploy or the quarterly GitHub Actions pipeline |
| AI rationale | 3-provider fallback: Gemini → Groq (`llama-3.3-70b-versatile`) → Cerebras (`gpt-oss-120b`), disk-cached per `(symbol, as_of_date)` | resilience + zero repeat cost; any provider failure falls through |
| Hosting | **Render.com free Web Service** (auto-deploy from `main`) | free, Linux, git-push deploys; Streamlit Community Cloud was retired |
| Keep-warm | GitHub Actions cron pinging `/_stcore/health` every 10 min | avoids free-tier cold-start without a new third-party service |
| VCS | Git; public GitHub repo `RAM-cybe/dealscope` | it's a skills-demo, no proprietary data |

**Platform is fixed:** Render (free tier) + Streamlit + GitHub. No migration, no
new hosting, no custom domain (domain purchase explicitly deferred).

## 3. Architecture & the composition-order contract

```
load_companies()  ─┐
                   ├─ valuation_range()  ─┐   (both on the FULL universe, once)
                   └─ score_companies()  ─┤
                                          └─ filter_companies()   (LAST, display only)
```

**Contract (must never be violated):** `score_companies()` and
`valuation_range()` always run on the full, unfiltered universe first;
`filter_companies()` runs last and its output must never feed back into either.
*Why:* both scoring percentiles and valuation peer-multiples are sector-relative;
computing them on an already-filtered subset would make a company's score/value
drift every time the user changes a filter, even though nothing about the company
changed. Enforced in the docstrings of `scoring.py` / `valuation.py`.

Presentation (`app.py`) is a thin layer over this pipeline. The 2026-07-16
redesign rewrote presentation only; `src/` was untouched.

## 4. The ten data-integrity rules (locked)

1. **Never fabricate or guess a value.** A genuine gap is blank / "N/A", always.
   This rule has caught every real data bug on the project (currency
   contamination ×2, negative revenue, zero-margin). It is the single most
   important discipline.
2. **Missing data never hides a company** from filters or scoring — a NaN always
   *passes* a range filter; it is only excluded when it has a present,
   out-of-range value.
3. A company with **< 2 of 4 scoring metrics** populated is left **unscored**
   (`score = NaN`, sorted last), never given a misleading blend.
4. Valuation is **null with a stated reason** when a company's own EBITDA /
   net income is missing/zero/negative, or its sector has < 3 qualifying peers —
   never a fabricated range.
5. **No currency guessing:** fields that yfinance reports in a non-INR currency
   (`currency_flag != OK`, e.g. INFY/HCLTECH) are blanked, never FX-converted.
6. **±inf is treated as a gap** (NaN), never shown.
7. Every **qualitative output traces to a real number/trend/filing category** —
   never AI-invented sentiment. The AI rationale prompt forbids inventing figures.
8. **No scraping** of any site whose ToU forbids it (nseindia/bseindia pages
   forbidden; their own RSS feeds are fine). screener.in ruled out.
9. Data is refreshed by **redeploy or the quarterly GitHub Actions pipeline**,
   which writes a dated snapshot (never overwrites), runs the quality checker,
   and opens a PR — **never auto-merges**; a human reviews before new data goes
   live.
10. The **automated quality checker** (`src/data/quality_checks.py`) runs on
    every refresh: range violations, cross-field consistency (incl.
    zero-margin-nonzero-ebitda and quick≤current invariants), and stale dates.

## 5. Scope (locked — do not expand without re-approving the PRD)

**In:** (1) Target Screening — sector multi-select + 5 range filters (revenue,
EBITDA margin %, ROCE %, total debt, market cap) + promoter-pledge ceiling; live
weighted scoring on 4 factors (Revenue Growth, EBITDA Margin, ROCE, Debt Level
inverted); ranked table. (2) Indicative Valuation tear sheet — sector-multiple
EV/EBITDA and P/E ranges. (3) AI-drafted rationale. (4) Sector-matched comparable
deals (context only, never used to derive multiples).

**Out (permanently, unless re-scoped):** due diligence, negotiation, legal,
integration, login, database, live price feeds, payments, native app.

**Deferred, not forgotten:** Altman Z-Score / Piotroski F-Score / Beneish
M-Score (blocked on `ebit`/`total_liabilities` fields + multi-period history);
real news/filings feed via official RSS + Reg-30 tagging; term-sheet generator.

## 6. Security posture (as of 2026-07-16)

- **Secrets:** never in code/tracked files/git history; API keys resolved at
  runtime from Streamlit secrets → env (`src/config.py`), never logged, never
  sent client-side (AI calls are server-side only).
- **XSS:** every dynamic/data/AI/user value is `html.escape()`'d before any
  `unsafe_allow_html` block. Search is a literal (`regex=False`) match.
- **Dependencies:** `pip-audit` → 0 known CVEs; versions pinned with `==`.
- **External calls:** every AI provider call has a 30 s timeout; no other
  outbound HTTP.
- **Error exposure:** `showErrorDetails = "none"` — no traceback ever reaches a
  visitor; detail stays in server logs.
- **GitHub:** secret scanning + push protection + Dependabot (alerts + auto-fix)
  + code scanning all on; 0 open alerts. Branch protection intentionally off
  (solo direct-push repo).
- **Admin model:** the app stays permanently login-free; "admin control" means
  owner-only external mechanisms (GitHub Actions manual dispatch, 2FA on
  GitHub/Render), never a login screen.

## 7. Error states (exact wording, locked)

| Condition | UI |
|---|---|
| Zero filter results | "No companies match these filters." + "Try widening your ranges." + Reset button |
| Missing metric | "N/A" in that cell, excluded from that metric's score only |
| No deal comps for a sector | "No comparable 2025 Indian M&A deals found in this sector." |
| AI rationale failure | "AI rationale unavailable right now — the rest of this tear sheet is unaffected." |
| Company cannot be scored | grey "—" ring + "cannot currently be scored" |
| Required column missing entirely | build/test-time warning only (`SchemaError`) |
