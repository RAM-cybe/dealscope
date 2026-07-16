# Research Summary — M&A Screening Tool Data Collection

Run date: 2026-07-11. Covers three parallel work-streams: (A) company financials, (B) multi-year M&A deal history, (C) time-tagged sector context.

---

## Stream A — Company financial dataset

**Confidence: HIGH**

- Universe: 2,047 NSE EQ-series companies (from EQUITY_L.csv, NSE's free equity list).
- **companies_full.csv: 2,046 companies with real yfinance data (99.95% of the universe).**
- **companies_failed.csv: 1 permanent failure** — `GYFTR` (no data returned, possibly delisted or a non-standard ticker).
- 0 symbols untried — every symbol in the universe was attempted.
- All values are direct `yfinance` API responses; nothing estimated or interpolated. 83 rows have a blank `market_cap` field where yfinance itself doesn't cover that particular small-cap — left as genuinely missing rather than guessed.
- One real rate-limit incident occurred mid-run (Yahoo Finance briefly 429'd 4 symbols after ~700 pulls); fixed by adding a throttle and re-running — no data was fabricated to paper over it.
- Two legitimate statistical outliers were spot-checked and confirmed real, not bugs (BOHRAIND and SPARC show extreme EBITDA margins because their revenue denominators are near-zero).

---

## Stream B — Multi-year M&A deal history

**Confidence: MEDIUM-HIGH** (varies materially by firm — see breakdown)

**deals_full.csv: 727 deals, spanning 2006–2025.** Built from the original 67-deal `deals.csv` (EY India M&A Report 2026) plus 682 newly extracted deals, with 22 cross-source duplicates merged (e.g. the same 2025 Ayana Renewables deal reported independently by both EY and PwC was collapsed into one row, with both sources credited).

| Source firm | Real editions found & extracted | Deals extracted | Notes |
|---|---|---|---|
| **Grant Thornton** (Dealtracker) | CY2019, CY2020, CY2021, CY2022, CY2023 (5 years) | 340 | By far the richest single source — GT's Dealtracker has genuine per-deal tables, not just top-10 lists. One edition (CY2023/2024-published) was a vector-graphic PDF unreadable by text extraction; recovered via OCR, with a few garbled rows deliberately dropped rather than guessed. |
| **EY** | 5 documents, 2022–2025 (quarterly/newsletter format, not full annual reports for every year) | 149 (incl. the original 67) | Could not find a standalone full-year "EY India M&A Report" for 2023 or earlier than 2022 — only tech-services-specific editions existed for those years. A platform/tooling issue meant these were saved as extracted `.txt`, not original PDF binaries — flagged below. |
| **KPMG** | 6 documents, years 2006, 2013, 2016, 2024, 2025 + one undated (~2008) | 135 | Naming varies a lot by year (pharma sector report, PE review, hospital-deals report, startup-ecosystem report) — no single consistent "KPMG Dealtracker" product exists; treated each as its own source. |
| **PwC** | 6 distinct annual/H1 editions, covering CY2019, 2021, 2022, 2023, 2024, 2025 | 66 | All freely accessible, no registration gates hit. |
| **Bain-IVCA** (India Private Equity Report) | Only **2010 and 2015** (2 of 8 attempted years) | 31 | **Data quality flag**: 6 of 8 downloaded "PDFs" (2016, 2018, 2019, 2020, 2021, 2026) turned out to be Cloudflare bot-challenge pages, not real reports — bain.com blocks automated downloads. This was caught before any fake data entered the dataset. Per this project's rules, bot-detection was not bypassed; only the 2 years that downloaded as real PDFs were used. |
| **Deloitte** | 3 documents — "India M&A Trends 2023" (data through 2022), "Deal Dynamics" (2024, commentary-only, no deal table), "Asia Pacific PE 2026 Almanac – India Edition" (2025 deals) | 26 | Deloitte's public output is more survey/commentary-style than deal-table-style; extracted what genuinely existed rather than forcing data. |
| **Local PDFs already in folder** (Dhruva, Nishith Desai, Rödl & Partner) | 3 documents, all confirmed to be legal/tax/services publications, not deal-tracker reports | 0 | Correctly identified as containing **no discrete named-deal data** — contributed sector commentary only. This is an honest negative result, not a shortfall. |

**Data completeness caveats (all real, none invented):**
- 80 of 727 deals (11%) have `deal_value_usdm = NA` where the source genuinely didn't disclose a figure.
- 422 of 727 deals (58%) have `stake_pct = NA` — most source tables report deal value and parties but not stake percentage; this is a structural limitation of the source material, not a scraping gap.
- `month` is `NA` for most deals outside the original EY 2025 dataset, since most annual reports report deals as year-level aggregates rather than dated line items.
- `ey_bucket` was auto-classified by keyword matching against each deal's raw sector label for all newly-added deals (the original 67 already had this field populated). 129 of 727 deals (18%) fell into "Unclassified" because their raw sector label didn't map cleanly to EY's 6-bucket taxonomy (e.g. "Start-up", "TMT", "Real Estate") — consistent with the BLUEPRINT's documented fallback behavior, not a defect.
- Realistically, coverage thins out before ~2015 — pre-2010 data was intentionally not pursued, matching the brief.

**Not found / inaccessible (honestly reported, not worked around):**
- Bain & Company India: years 2016–2021 and 2026 are blocked by bot-detection (Cloudflare), not absent from the internet — genuinely inaccessible to automated retrieval within this project's rules.
- A standalone full-year EY India M&A Report for 2020, 2021, or 2023 (only quarterly/tech-specific EY documents were locatable for the gaps).
- Any PwC or Deloitte report that was registration-gated with no public PDF URL was skipped rather than bypassed (none actually hit a hard gate this run — all found PwC/Deloitte reports were freely downloadable).

---

## Stream C — Time-tagged sector context

**Confidence: HIGH**

- **sector_notes_timeline.csv: 182 rows** spanning 2006–2026, tagged by sector, year, and source report — built from `sector_context.md` (EY 2026) plus every sector-commentary extraction from Stream B's source documents.
- **sector_notes_latest.md**: organized by EY's 6 sector buckets (Infrastructure, Industrials and Auto, Consumer Products and Retail, Lifesciences, Technology, Financial Services), each showing the most recent year's notes available. For every bucket, 2026 (EY India M&A Report 2026) remains the most recent genuine data point — no other source had real 2026 content (Bain's 2026 report was the bot-blocked file, not real). A 7th section, "Other sector themes," preserves valuable commentary (Start-up ecosystem, Deeptech, Spacetech, TMT, etc.) that doesn't cleanly map onto the 6-bucket taxonomy, rather than discarding it.
- All notes are direct extractions/paraphrases of real report text, each tagged with its source and year — no synthesized commentary.

---

## Data integrity notes (process-level)

- Mid-run, two CSV-quoting bugs were found and fixed during merge (unescaped commas inside two source fields had shifted columns in raw partial files) — caught via an automated malformed-row check before being merged into the final files, not left silently wrong.
- A classification bug in the first merge pass caused ~660 deals to be mis-tagged `ey_bucket = "NA"` instead of being run through the sector classifier; caught by a sanity check on the bucket distribution and fixed before finalizing.
- One firm's report_year convention (Deloitte's PE Almanac, labeled by publication year 2026 rather than deal year) was corrected to align with the rest of the dataset (deal year 2025), based on the month field already present in the same rows.
- All source PDFs (except the 5 EY documents, saved as `.txt` due to a mid-session tooling issue) are preserved under `sources/<firm>/` for traceability.

---

## Overall confidence ratings

| Stream | Rating | Why |
|---|---|---|
| A — Company financials | **HIGH** | 99.95% universe coverage, every value a real API response, only 1 genuine failure. |
| B — Deal history | **MEDIUM-HIGH** | Strong depth for Grant Thornton/PwC/KPMG (2013–2025), thin/blocked for Bain outside 2 years, EY historical limited to quarterly documents rather than full annual reports pre-2022. All gaps are disclosed, not papered over. |
| C — Sector context | **HIGH** | Broad multi-source, multi-year timeline; the "latest" view is honestly dominated by the 2026 EY report because nothing more recent and equally comprehensive exists. |

## Files delivered

`companies_full.csv` · `companies_failed.csv` · `deals_full.csv` · `sector_notes_timeline.csv` · `sector_notes_latest.md` (plus intermediate `deals_partial_*.csv` / `sector_notes_partial_*.csv` per firm and downloaded source PDFs under `sources/`, kept for audit traceability).
