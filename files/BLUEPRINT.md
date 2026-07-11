# BLUEPRINT — M&A Target Screening & Valuation Tool
*(working name — rename as you like)*

## 1. Data Model

**Company** — one record per NSE-listed company from the Screener.in export.
Fields: Name, Raw Sector/Industry (Screener label), Revenue, EBITDA, EBITDA Margin %, ROCE %, Total Debt, Promoter Pledge %, Market Cap.

**SectorMapping** — a static lookup file, generated once by the coding AI at build time (not at runtime). Maps every raw Screener industry label to one of EY's 6 broad sector buckets: Infrastructure, Industrials & Auto, Consumer Products & Retail, Lifesciences, Technology, Financial Services. Every Company resolves to exactly one bucket through this table.

**Filter** — pure in-memory session state. Not saved anywhere, not persisted between visits. Represents whatever the user currently has selected: sector(s), revenue range, EBITDA margin range, ROCE range, debt range, market cap range, promoter pledge ceiling.

**Score** — computed live, never stored. For every visible company, blends 4 sector-relative percentile ranks (Revenue Growth, EBITDA Margin, ROCE, Debt Level — inverted, so lower debt ranks higher) using 4 independent user-controlled 0–10 weight sliders, auto-normalized so the weights always combine sensibly regardless of what the user drags them to. "Sector-relative" means a company is ranked against peers in its own EY bucket, not the whole 400-company universe.

**TearSheet** — not a stored entity, just a view rendered fresh each time a company is clicked. Assembles: Company data + Score breakdown + Valuation range + AI rationale + matched Deal Comps.

**DealComp** — one record per real 2025 deal from deals.csv (Month, Target, Acquirer, Sector, Deal Value US$m, Deal Type, Deal Stake %). Linked to Companies via SectorMapping, not by direct string match.

**Relationships:**
```
Company  ──1:1──  SectorMapping (each company → exactly one EY bucket)
SectorMapping  ──1:many──  DealComp (many deals share a bucket)
Company  ──1:1──  Score (computed on demand, not stored)
Company  ──1:1──  TearSheet (rendered on click; pulls in Score + matching DealComps + AI text)
```

## 2. User Flow

**Step 1 — Landing.** User opens the public URL. The app loads immediately showing the **full ranked table of all ~400 companies**, scored using default slider weights (all 4 sliders at equal weight). No setup screen, no blank state.

**Step 2 — Filtering.** User adjusts filters in a sidebar (sector, revenue, EBITDA margin, ROCE, debt, market cap, pledge ceiling). Table updates instantly to show only matches, still sorted by Score.

**Step 3 — Reweighting.** User drags any of the 4 scoring sliders. Every visible company's Score recalculates instantly and the table re-sorts live.

**Step 4 — Tear Sheet.** User clicks a company. App navigates to a dedicated tear sheet page: company header → Score badge + weight breakdown → key financials → valuation range (EV/EBITDA and P/E based) → AI-drafted rationale paragraph → up to 5 most recent comparable deals in the same sector bucket. A "← Back to results" button returns to the filtered table exactly as it was left.

**Error paths:**
- **Zero filter results** → friendly message ("No companies match these filters — try widening your ranges") + one-click "Reset all filters" button. Never a blank screen.
- **Missing data field** for a company (e.g. no reported ROCE) → shows "N/A" in that cell; that metric is dropped from that company's score only, remaining metrics reweight automatically; company still appears.
- **No deal comps** for a sector → "No comparable 2025 deals found in this sector" instead of an empty table.
- **Gemini API fails/times out/rate-limited** → tear sheet still renders fully; rationale section shows "AI rationale unavailable right now — the rest of this tear sheet is unaffected."

## 3. Dependencies

- **Screener.in CSV** (~300–500 NSE companies) — Ram exports before build begins via the "Export" button on the Screener results page. Exact column names get confirmed against the real export and locked into the schema.
- **deals.csv** — already extracted from the EY India M&A Report 2026 (2025 deal data), bundled as a static file.
- **Gemini API key** (free tier) — obtained from aistudio.google.com before build begins; used only for the tear sheet rationale text.
- **Streamlit Community Cloud** — free hosting, no separate signup needed beyond a GitHub account.
- Both CSVs are bundled directly into the app; no database, no live feeds, no runtime file uploads.

## 4. Failure Modes

- Screener export column names don't match what the app expects → caught at build/test time with a clear error, not silently wrong data.
- A rare Screener industry label wasn't seen during the one-time sector-mapping pass → falls into an "Unclassified" bucket; company still shows in results, just has no deal comps.
- Gemini free-tier rate limit hit during a live demo (e.g. clicking many companies fast) → falls back gracefully per the error path above, never crashes the app.
- Dataset larger than expected (>500 rows) → low risk, Streamlit/pandas handles a few thousand rows easily, but worth one test with the real file size.
- deals.csv has inconsistent number formatting (commas, "NA" text) → cleaned once during data prep, not parsed live at runtime.
