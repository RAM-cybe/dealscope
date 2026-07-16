# DealScope — Execution Plan (read this first, in a fresh session)

**Who this is for:** a new Claude Code session with no memory of prior conversations,
picking this project up to keep building it. This document tells you where the project
stands, what's still to be built, in what order, and the rules you inherit. It does not
replace `CONTEXT.md` or `V2_ROADMAP.md` — read both in full before touching anything.
This document sequences their content into one executable plan.

Repo: https://github.com/RAM-cybe/nse-ma-target-screener (public)

---

## 0. Where the project actually stands right now

**Update — v1 shipped since this document was first written.** The AI rationale is wired
in (real Google Gemini calls, cached per company so the free-tier quota isn't a
constraint), a full QA pass ran with all 11 PRD acceptance criteria passing (including a
real manual click-test closing out the one previously-open item), and the app has been
live on Streamlit Community Cloud. **That hosting choice is now being reversed — see §0B
below — and a heavy UI/UX redesign has been added as new locked scope before the next
deploy.** Nothing else about the built modules changes.

Built and committed (one commit per module, independently gate-verified — see
`CONTEXT.md` "Build Status" table for exact commit hashes and PASS/FAIL detail):

1. Data layer — CSV loading, validation, sector classification. **Done.**
2. Business logic — 7-field filtering, sector-relative percentile weighted scoring
   across 4 factors. **Done.**
3. Two real data bugs found and fixed (currency mismatch, missing net income). **Done.**
4. Valuation module — EV/EBITDA and P/E sector-multiple ranges. **Done.**
5. Streamlit UI (`app.py`, ~734 lines) — sidebar, ranked table, 6-section tear sheet,
   CSV export, shareable URL state. **Done**, all 11 PRD acceptance criteria independently
   verified, including the row-click mechanism.
6. AI rationale — real Gemini calls wired in, cached per company. **Done.**

Not started:

- Heavy UI/UX redesign (new locked scope, §0B / Phase 1 Module U below).
- Migrating hosting off Streamlit Community Cloud onto Render.com (§0B below).
- Everything in `V2_ROADMAP.md` (data expansion, refresh/history, news, distress scores,
  term sheet, bonus features).
- Launch (resume, LinkedIn, outreach) — comes after the above.

Data collected: 2,046 NSE-listed companies (16 fields, 91–99% population by field),
727 real Indian M&A deals 2006–2025 from EY/GT/KPMG/PwC/Deloitte/Bain. See
`RESEARCH_SUMMARY.md` for full provenance and confidence ratings per source.

**A separate research pass produced `V2_ROADMAP.md`** — a large set of new,
verified-feasible additions (expanded financial fields, quarterly refresh + history,
news/filings integration, distress-score models, a term-sheet generator, four bonus
features, the Render.com hosting migration, and the UI/UX redesign). Nothing in
`V2_ROADMAP.md` has been built yet.

## 0B. Two new locked decisions (this update)

1. **Hosting migration, Streamlit Community Cloud → Render.com.** Vercel is confirmed
   architecturally incompatible with Streamlit (persistent WebSocket process vs. Vercel's
   short-lived serverless functions) — ruled out for good. Streamlit Community Cloud's
   own viewer chrome (Share/star/GitHub icons, floating "Manage app" badge) is platform
   branding that can't be removed from inside the app — that's the real reason the current
   live site "looks" unfinished despite the underlying design work being done. Render's
   free Web Service tier runs the same `app.py` unchanged, supports WebSockets, and
   supports free custom domains + TLS with zero injected UI. Trade-off (15-min idle
   spin-down, ~1 min cold start) is the same class of trade-off Streamlit Cloud already
   made — not a new downside. Full detail: `V2_ROADMAP.md` §0.
2. **Heavy UI/UX redesign**, materially beyond the first design-matching pass already
   done. Full detail and the honest styling-ceiling note: `V2_ROADMAP.md` §9.

---

## 1. The one strategic call this document makes that neither prior doc made

**Ship the locked v1 scope first. Deploy it. Then build v2 on top as live updates.**

Reasoning: v2 scope (§3 onward below) is large — larger than v1 itself. Render (like
Streamlit Cloud before it) auto-redeploys on every push to the connected branch, so there
is zero cost to shipping v1 now and continuing to build afterward; the alternative — holding the
public link until the entire expanded scope is done — risks the project never actually
shipping, which is the single most common failure mode of scope growth like this. Do not
let Phase 2+ delay Phase 1. This is a direct instruction, not a suggestion to reconsider.

---

## Phase 1 — Ship v1 (do this before anything in `V2_ROADMAP.md`)

**Module A — Wire the real AI rationale.** ✅ **DONE.** Real Gemini calls, cached per
company. Verified across 10+ companies, failure path confirmed non-blocking.

**Module B — Full QA pass.** ✅ **DONE.** All 11 PRD acceptance criteria passed,
including a real manual click-test confirming the row-click-to-tear-sheet mechanism.

**Module U (NEW) — Heavy UI/UX redesign.** Not started. Full frontend overhaul, going
materially beyond the earlier design-matching pass — see `V2_ROADMAP.md` §9 for scope and
the honest note on Streamlit's native-widget styling ceiling. Do this **before** the
redeploy below, so the redeploy ships the real target look, not an interim one. Gate:
redesigned UI checked against the locked mockup (`MA Screener - Design Options.dc.html`)
section by section; any place the mockup can't be matched inside Streamlit's architecture
is explicitly flagged, not silently approximated.

**Module C — Deploy/redeploy.** ~~Streamlit Community Cloud~~ → **Render.com free Web
Service**, per the locked decision in §0B / `V2_ROADMAP.md` §0. Set up the Render service
(start command, Gemini key as an env var), confirm WebSocket-driven interactivity works,
confirm custom-domain-ready (even if a domain isn't purchased yet), confirm publicly
reachable with zero injected platform UI. This supersedes the app's current Streamlit
Cloud deployment — plan to retire that URL once Render is confirmed stable.

**Gate to leave Phase 1:** app is live on Render at a public URL, redesigned UI matches
the locked mockup (with any ceiling cases explicitly documented), all 11 PRD acceptance
criteria re-confirmed on the new host, no known bugs. Only then start Phase 2.

---

## Phase 2 — Data foundation (everything after this depends on it)

**Module D — Expand the company dataset.** Add these fields via the existing yfinance
enrichment script (same source, same discipline — genuine gap stays blank, never guessed):
current ratio, interest coverage ratio, net debt/EBITDA, free cash flow, FCF yield,
operating cash flow, PEG ratio, EV/Revenue, price/book, FII/DII institutional holding %,
beta, total assets, retained earnings, working capital (the last three specifically
needed for Module H's Altman Z-Score). New fields become filters only — do not touch
`scoring.py`'s 4-factor weighting in this module. Gate: population-rate table for every
new field, same honesty standard as the existing one in `CONTEXT.md`.

**Module E — Automated data-quality rules.** Build sanity-check rules into the
enrichment pipeline itself: range checks (impossible margins, negative revenue where
it shouldn't occur), cross-field consistency checks, stale `as_of_date` flags. This
runs automatically on every future refresh, not just once. Gate: run against the full
2,046-company dataset, produce a flagged-rows report, spot-check a sample of flags by hand
to confirm they're real issues and not false positives.

**Module F — Refresh architecture.** GitHub Actions workflow: full quarterly refresh of
every field (matches real disclosure cycles), lighter/more frequent price+market-cap-only
refresh in between. Every quarterly run writes a **dated snapshot** file, never overwrites
history. Note the 60-day workflow auto-disable on inactive public repos — build in a
keep-alive or accept manual reactivation. Gate: one full dry-run of the workflow, confirm
snapshot files accumulate correctly and the throttle avoids the 429 rate-limit issue
already seen once in this project's history.

**Module G — Stratified spot-audit.** Manually check 30–50 companies (spread across
sectors and market-cap bands) against their real NSE/BSE filings. Publish the methodology
and match rate as a real artifact (feeds Module M's provenance panel). Gate: audit
document exists, is honest about any mismatches found, not just a "100% verified" claim
unless that's actually true.

**Gate to leave Phase 2:** expanded dataset live, refresh pipeline tested end-to-end
at least once, first quarterly snapshot exists, spot-audit published.

---

## Phase 3 — Derived intelligence (needs Phase 2's data + history)

**Module H — Distress/quality scores.** Altman Z-Score (needs Module D's new balance-sheet
fields — standard public-company formula, no hidden assumptions). Piotroski F-Score (needs
Module F's snapshot history for prior-period deltas — ROA, cash flow vs net income,
leverage change, current ratio change, margin change, asset turnover change). Before
starting, check Beneish M-Score's required fields (accruals, receivables growth) against
actual yfinance coverage — only commit to building it if the fields are genuinely there;
otherwise document why it's out and stop, don't force it. Gate: both scores computed for
the full universe, population rate disclosed same as every other field, spot-checked
against 5–10 companies by hand against the textbook formula.

**Module I — News & filings ingestion.** NSE + BSE official RSS feeds (results, board
outcomes, pledge/insider changes, litigation) — **RSS only, never scrape nseindia.com's
own pages**, their Terms of Use explicitly forbid it regardless of what robots.txt allows.
Google News RSS by query for general/sector/government context. Store ingested items with
real source + link, segregated by bucket. Gate: live for a real sample of companies across
different sectors, every item traceable to its real source URL.

**Module J — Regulation 30 qualitative tagging.** Classify Module I's official filings
into SEBI's real disclosure taxonomy (order wins, credit rating actions, litigation,
auditor resignation, related-party transactions, insolvency, fraud, regulatory action).
This is the qualitative signal — a real legal category per filing, never AI sentiment.
Gate: classification accuracy spot-checked against a sample of real filings, categories
match SEBI's actual Schedule III Para A/B taxonomy.

**Gate to leave Phase 3:** Z-Score, F-Score, filings feed, and Reg 30 tags all live and
population/accuracy-disclosed, same honesty standard as everything else in this project.

---

## Phase 4 — Term sheet (needs everything above — build it last, not first)

**Module K — Term sheet generator.** One standardized skeleton for every company
(price/structure, escrow %, indemnity cap, CCI/SEBI/RBI conditions precedent — generic,
market-standard, clearly labeled illustrative/non-binding — never a company-specific
invented legal term). Auto-filled per company with: the existing mechanical valuation
range, Altman Z / Piotroski F scores, real trend flags (pledge, insider holding, debt,
margin — from Module F's snapshot history), Reg 30 filing flags, sector M&A intensity
from the 727-deal dataset. Output as both PDF and Excel. Gate: generate for 10+ companies
spanning sectors, confirm every populated field traces to a real number/trend/filing —
zero invented figures anywhere on the document.

---

## Phase 5 — Product polish (can interleave with Phase 3/4 if there's bandwidth, but don't let it block Phase 4)

**Module L — Data provenance/audit panel.** Surfaces Module E's flags, Module F's refresh
dates, Module G's spot-audit results, per company, in-app.

**Module M — Side-by-side company compare.** 2–3 companies, one view, using data already live.

**Module N — Sector dashboard.** Visual deal intensity + multiples per EY sector bucket,
from the existing 727-deal dataset — no new data needed, pure presentation.

**Module O — Practice/interview mode.** Hides the company name, user screens from metrics
alone. Independent of everything else — can be built any time bandwidth allows, including
earlier than this phase if it's wanted as a quick win.

**Module P — Methodology/limitations page.** Write last, once — describes the final
state of everything built (scoring math, data sources, refresh cadence, known gaps,
Reg 30 taxonomy, model formulas). This is the single highest credibility-per-effort item
in the whole plan; do not skip it even under time pressure.

---

## Phase 6 — Final QA, redeploy, launch

Re-run the full PRD-style acceptance pass against the now much larger feature set,
deliberate edge cases across every new module (empty filings feed, a company missing
all three Altman fields, zero deal comps for a sector, term sheet for a company with
heavily currency-fix-blanked data), security check again (news/filings ingestion adds
new external calls — confirm no leaked keys, no unbounded external requests). Redeploy
(automatic via git push to the connected branch). Then: resume bullet, LinkedIn post,
Big 4 / corp dev outreach.

---

## Rules that carry forward unchanged from `CONTEXT.md` — do not silently relax these

- No fabricated/estimated data anywhere, ever. A genuine gap is blank/"N/A," never guessed.
- Missing data never hides a company from filters or scoring.
- One module per session, independently gate-verified (not just self-reported) and
  committed before the next module starts.
- `score_companies()` and `valuation_range()` (and now Module H's distress scores) must
  run on the full unfiltered universe first — filtering happens last, for display only.
- No scraping of any site whose Terms of Use forbid it. Full stop, no exceptions, no
  "just this once" — this has already correctly ruled out screener.in and now nseindia.com's
  own pages (RSS feeds are fine; scraping their rendered pages is not).
- Every qualitative-sounding output (Reg 30 flags, trend narratives, term sheet color)
  must trace to a real number, real trend, or real filing — never an AI-invented judgment
  score. This is the single most important discipline added this session, on top of the
  original no-fabrication rule.

---

## One-paragraph summary if you only read this far

v1 (the screener + valuation tear sheet) is ~90% done — ship it first (Phase 1), deploy
it, get a real public link, before starting anything below. Then Phase 2 rebuilds the
data foundation (more fields, automated QA, quarterly refresh + history). Phase 3 adds
real derived intelligence on top of that foundation (Z-Score, F-Score, sourced news/filings,
Reg 30 tags — no invented sentiment anywhere). Phase 4 is the term sheet, built last
because it consumes everything from Phases 2–3. Phase 5 is polish, interleaved if there's
time. Phase 6 is the final QA-and-launch pass. Every module is gate-verified and committed
individually — same discipline that already caught two real data bugs in v1. Nothing here
gets built without an explicit go-ahead for that specific module.
