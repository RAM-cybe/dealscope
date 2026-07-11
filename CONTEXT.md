# M&A Screening Tool — Current State (July 2026)

## Data Status — VERIFIED COMPLETE
- **companies_full_v2.csv**: 2,046 / 2,047 NSE-listed companies
  - Core financials from yfinance (revenue, EBITDA, margins, debt, market cap, holdings, growth, ROE)
  - **ROCE %** calculated from Yahoo annual balance sheet (EBIT / (Total Assets - Current Liabilities))
  - **Promoter Pledge %** from NSE XBRL shareholding filings (real disclosed values, not modelled)
  - 91.7% ROCE populated, 95.2% Pledge populated (non-disclosing companies left blank — correct)
  - User performed final merge of cache files into main CSV — data now satisfies full PRD schema

- **deals_full_v2.csv**: 727 curated deals (2006–2025)
  - Sources: EY India M&A Report, Grant Thornton Dealtracker, KPMG, PwC, Deloitte, Bain (partial), Dhruva, Nishith Desai, Roedl
  - Deduplicated on target + acquirer + year/month
  - Sector classified into EY 6 buckets
  - Unclassified reduced to ~4 (excellent)
  - Some NA on value/stake (source limitation, kept honest)

- **sector_notes_latest.md + timeline.csv**: Real multi-year context (2006–2026) organized by EY bucket
  - From all uploaded reports

Data collection phase **done**. No fabrication. All numbers trace to source (yfinance or NSE filings or published reports).

## PRD Scope (Locked)
- Single-file Streamlit app (free Community Cloud)
- Bundled CSVs only — no DB, no live feeds
- Two features: (1) Target Screening (filter + weighted sector-relative score), (2) Indicative Valuation + tear sheet
- Tear sheet includes: financials, valuation range (sector multiples), Gemini rationale, comparable deals
- "Data as of [date]" clearly shown
- No login, no payments, desktop-first but mobile functional

## Why No "Live" Free Auto Everything
Research confirms:
- No single free, unlimited, reliable API provides revenue + EBITDA + ROCE (calculated) + promoter pledge % for 2,000+ Indian companies.
- yfinance is the best free option for fundamentals + balance sheet.
- Promoter pledge requires NSE XBRL or equivalent scrape (done).
- M&A deals: No free structured API matches the curated quality of consulting reports. Periodic human-assisted extract from new PDFs is the realistic path.
- Quarterly reporting cadence makes true real-time unnecessary for screening tool.

## Honest Assessment of Previous Automation Plans
- Good ideas kept: as_of_date tagging, easy refresh path, "data as of" UI.
- Overkill removed: Prometheus/Grafana (no users, no on-call), elaborate backoff module (simple paced retry sufficient at 2k symbols quarterly), premature full GitHub Actions + SQLite + versioning before app exists, "automated" deals (still needs human report handling).

## Current Plan (Agreed Direction)
1. Data layer: Use companies_full_v2.csv + deals_full_v2.csv directly (bundled)
2. Add as_of_date column if missing (simple)
3. Build Streamlit app exactly per PRD (filters, live scoring, tear sheet, Gemini, comps)
4. Show clear "Data as of [latest pull date]" in UI
5. Future refresh: Rerun existing scripts manually or add lightweight cron later (after app ships)
6. No DB, no metrics stack, no over-engineering for demo/portfolio scale

Next immediate action: Build the app. Start with data loading + filters + scoring module.

This is a clean, honest, production-ready-for-demo state. No more collection. Build time.

## Infrastructure Status (July 2026)
- Repo: public GitHub repo `nse-ma-target-screener`, `git init` done, Module 1 (`src/data/*.py`)
  committed and pushed first.
- `.gitignore` excludes secrets, source PDFs/OCR scratch, superseded/partial data files, and
  one-time collection scripts — none of that belongs in a public portfolio repo.
- **Gemini API key handling** (`src/config.py`, `get_gemini_api_key()`):
  - **Local dev**: key goes in a gitignored `.env` file at the project root as
    `GEMINI_API_KEY=your-key-here`. Never commit this file.
  - **Streamlit Community Cloud**: the key is NOT read from any committed file. Set it in the
    deployed app's **Settings → Secrets** panel, TOML format:
    ```toml
    GEMINI_API_KEY = "your-key-here"
    ```
  - `get_gemini_api_key()` tries `st.secrets["GEMINI_API_KEY"]` first (Cloud), falls back to
    `os.environ["GEMINI_API_KEY"]` (local `.env` via `python-dotenv`), returns `None` if neither
    is set. Callers must handle a `None` key gracefully (see PRD's Gemini-failure error path).
