# DealScope — App Flow

The user journey through the "DealScope - Final Design" (dark/teal five-view
flow), as shipped and live on production. Last updated 2026-07-16.

State is carried entirely in **URL query params** (no login, no server session,
no browser storage) — every view is deep-linkable and shareable.

---

## View state machine

```
                       ┌──────────────────────────────────────────────┐
                       │                                              │
              (bare visit, no params)                                 │
                       │                                              │
                       ▼                                              │
             ┌───────────────────┐                                   │
             │  1. LANDING        │   search / pick sector / "Browse" │
             │  (view=landing)    │ ─────────────────────────────────▶│
             │  search pill,      │                                   │
             │  sector chips,     │                                   ▼
             │  Advanced filters  │                        ┌───────────────────┐
             └───────────────────┘                        │  2. RESULTS        │◀──┐
                       ▲                                   │  (view=results)    │   │
                       │  wordmark (home)                  │  score-ring table  │   │
                       └───────────────────────────────────│  top bar + chips   │   │
                                                           └───────────────────┘   │
                                              ┌──────────────────┬─────────────────┤
                                     click "Advanced filters"    click a row       │
                                              │ (?panel=1)       │                 │
                                              ▼                  ▼                 │
                                   ┌───────────────────┐  ┌───────────────────┐    │
                                   │  3. FILTERS        │  │  4/5. TEAR SHEET   │    │
                                   │  slide-over (right)│  │  (view=tearsheet   │    │
                                   │  sliders+weights   │  │   &symbol=XXX)     │    │
                                   │  Reset / Apply     │  │  populated OR      │    │
                                   └───────────────────┘  │  data-sparse       │    │
                                        │ Apply/Reset      └───────────────────┘    │
                                        │ (closes panel)          │ "← Back"        │
                                        ▼                         └─────────────────┘
                                   back to RESULTS
```

Also reachable: **"How scoring works"** (`view=scoring`) from the results bar —
a plain explainer page with a "← Back to results" link.

Inbound deep links that carry a `sectors` or `q` param open straight into
**Results** (so old/shared filter links don't dead-end on the landing).

---

## 1 · Landing / search (`view=landing`, the default)

- DEALSCOPE wordmark, headline "Screen NSE-listed companies like a deal team.",
  one-line pitch, a **search pill** (company or ticker), a row of **sector
  quick-chips**, a "Browse all companies →" button, and a
  `DATA AS OF … · 2,046 COMPANIES` footer. Top-right: **Advanced filters**.
- **Actions:** typing a query + Enter → Results filtered by that text. Clicking a
  sector chip → Results filtered to that sector. "Browse all" → Results,
  unfiltered. "Advanced filters" → Results with the slide-over open.

## 2 · Results (`view=results`)

- **Top bar:** wordmark (→ home/landing), search box (live), **Advanced filters**
  (opens slide-over), **CSV** (downloads the full filtered set), **Share** (copies
  the current deep link).
- **Sector chips:** toggle sectors in/out (selected = teal fill).
- **Count line:** "N companies matched" + "How scoring works ⓘ".
- **Score-ring table:** rank · company (name + ticker) · sector · **score ring**
  (teal arc = score, white tick = sector-average score) · revenue · margin · ROCE
  · debt. N/A cells are dimmed. **Each row is a link to that company's tear sheet.**
  The top ~60 rows render, with a "Show more" step; the count and CSV always
  reflect the full filtered set.
- **Zero results:** the exact-worded "No companies match these filters. / Try
  widening your ranges." card + a Reset button.

## 3 · Advanced-filters slide-over (`?panel=1` on Results)

- A right-docked dark drawer over a dimmed/scrimmed results view, holding the
  real working widgets: **range sliders** (revenue, EBITDA margin %, ROCE %, total
  debt, market cap), a **max promoter-pledge** slider, and the four **factor-weight**
  sliders (Revenue Growth, EBITDA Margin, ROCE, Debt Level). Filters/weights apply
  live (the table re-ranks behind the scrim). **Reset** clears everything;
  **Apply** closes the drawer (changes are already applied).

## 4 · Tear sheet — populated (`view=tearsheet&symbol=XXX`)

Order, top to bottom: back link; company name + ticker badge + "Sector · Industry";
**score ring** (with glow + sector-average tick + "sector avg N"); four headline
stat cards (Market Cap, Revenue, ROCE, Total Debt); **Score Breakdown** (per-factor
bars with weights + percentiles; a missing factor shows "reweighted — no data");
four more cards (EBITDA, EBITDA Margin, Net Income, Promoter Pledge); **teal
gradient valuation card** (EV/EBITDA-implied and P/E-implied ranges); **AI-DRAFTED
rationale** (or the non-blocking "unavailable" fallback); **comparable deals** table
(or the exact "no comparable deals" line); a "Filings & news — reserved for a future
release" footer.

## 5 · Tear sheet — data-sparse (same URL, a company that can't be scored)

Same skeleton, honest empty states: grey "—" ring + "no sector peers to compare";
all-N/A stat cards; every breakdown factor "reweighted — no data" + "All 4 factors
unavailable — this company cannot currently be scored."; a **dashed** valuation
card "Insufficient data to estimate a valuation range." + the specific reason; an
**UNAVAILABLE** rationale card. Nothing is faked — the sparse state is the point.
