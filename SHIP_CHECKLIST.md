# DealScope — Ship-It Checklist

Copy-paste this into a fresh chat alongside `CONTEXT.md`, `V2_ROADMAP.md`, and
`EXECUTION_PLAN.md`. This is the single consolidated checklist — every decision already
locked in those three docs, plus general production-launch practice (security, QA,
hosting, future-proofing) applied specifically to this project. Researched against
current OWASP, Streamlit, GitHub, and Render guidance.

---

## 0. Status snapshot (so nothing gets re-done by mistake)

- [x] Data layer, business logic, valuation module, Streamlit UI — built, committed, PRD-verified
- [x] Real AI rationale wired in (Gemini, cached per company)
- [x] Full 11/11 PRD acceptance criteria passed
- [x] Currently live on Streamlit Community Cloud
- [ ] Hosting migration to Render.com — not done
- [ ] Heavy UI/UX redesign — not done
- [ ] Everything in `V2_ROADMAP.md` (data expansion, refresh/history, news, distress scores, term sheet, bonus features) — not done

---

## 1. FEATURES — what ships, in order

### Phase 1 — finish v1 properly
- [ ] Heavy UI/UX redesign against the locked mockup (`MA Screener - Design Options.dc.html`), beyond the first palette/font pass — real layout, custom card components, custom-styled tables/filters
- [ ] Document any spot where Streamlit's native widgets can't fully match the mockup (sliders, grid) instead of quietly approximating
- [ ] Migrate hosting: Streamlit Community Cloud → Render.com free Web Service
- [ ] Re-run all 11 PRD acceptance criteria on the new host + new UI

### Phase 2 — data foundation
- [ ] Add new financial fields via yfinance: current ratio, interest coverage, net debt/EBITDA, free cash flow, FCF yield, operating cash flow, PEG ratio, EV/Revenue, price/book, FII/DII holding %, beta, total assets, retained earnings, working capital
- [ ] New fields as filters only — 4-factor score untouched this phase
- [ ] Automated data sanity-check rules built into the refresh pipeline (range checks, cross-field consistency, stale-date flags)
- [ ] GitHub Actions: full quarterly fundamentals refresh + lighter price/market-cap refresh in between
- [ ] Every quarterly run writes a dated snapshot (never overwrites) — this is what powers trend flags later
- [ ] Stratified manual spot-audit: 30–50 companies vs. real NSE/BSE filings, methodology + match rate published

### Phase 3 — derived intelligence
- [ ] Altman Z-Score (needs Phase 2's balance-sheet fields)
- [ ] Piotroski F-Score (needs snapshot history for prior-period deltas)
- [ ] Beneish M-Score — only if yfinance actually has the required accrual fields; otherwise document why it's out
- [ ] News/filings ingestion: NSE + BSE official RSS feeds (never scrape their pages), Google News RSS for general/sector/government context — every item sourced + linked
- [ ] Regulation 30 tagging: classify filings into SEBI's real disclosure taxonomy (no AI sentiment scoring, ever)

### Phase 4 — term sheet
- [ ] Standardized skeleton (price/structure, escrow %, indemnity cap, CCI/SEBI/RBI conditions precedent) — generic across all companies, labeled illustrative/non-binding
- [ ] Auto-filled per company: valuation range, Z/F-scores, real trend flags, Reg 30 flags, sector deal intensity
- [ ] PDF and Excel export
- [ ] Zero invented company-specific figures anywhere on the document

### Phase 5 — polish
- [ ] Data provenance/audit panel (refresh dates, spot-audit results, known gaps, per company)
- [ ] Side-by-side company compare (2–3 companies)
- [ ] Sector dashboard (deal intensity + multiples per EY bucket)
- [ ] Practice/interview mode (hide company name, screen from metrics)
- [ ] Methodology/limitations page — written last, describes the final state of everything

---

## 2. HOSTING — moving off Streamlit Cloud

- [ ] Create Render.com account, connect the GitHub repo
- [ ] Define a Web Service (free instance type): build command `pip install -r requirements.txt`, start command `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`
- [ ] Move the Gemini API key from Streamlit Secrets into Render's environment variables — never hardcode it
- [ ] Confirm WebSocket connectivity works (required for live sliders/filters)
- [ ] Confirm the deployed app has zero injected platform chrome (no "Manage app" badge, no fork banner)
- [ ] Test the free-tier cold start behavior (15 min idle → ~1 min wake) and decide if that's acceptable as-is, or whether to add a lightweight uptime ping (see §5) to reduce it
- [ ] Once Render is confirmed stable, retire/redirect the old Streamlit Cloud URL
- [ ] (Optional, later) buy a cheap custom domain and map it via Render's free custom-domain + managed TLS support

---

## 3. SECURITY CHECKLIST

**Secrets**
- [ ] Gemini API key is never committed to git, anywhere in history — check with `git log -p | grep -i "api_key\|AIza"` (or similar) across the whole repo history, not just the current commit
- [ ] `.streamlit/secrets.toml` and `.env` are in `.gitignore` and were never committed
- [ ] Key lives only in Render's environment variables in production, `.env` (gitignored) locally
- [ ] GitHub secret scanning + push protection enabled on the repo (free, automatic on public repos — confirm it's actually on in repo settings)

**Dependencies**
- [ ] GitHub Dependabot security alerts enabled (free on public repos)
- [ ] Run `pip-audit` (free) against `requirements.txt` before each major release, fix or document any flagged CVEs
- [ ] Pin dependency versions in `requirements.txt` rather than leaving them unbounded, so an upstream breaking change can't silently break the live app

**Code-level**
- [ ] Run `bandit` (free, Python-specific static security scanner) once against the codebase — catches hardcoded secrets, insecure function use
- [ ] No user-submitted free text is ever passed into a file path, shell command, or eval — confirm this stays true as new features (search, filters) are added
- [ ] Any external HTTP calls (RSS feeds, yfinance, Gemini) have timeouts set, so one slow external service can't hang the whole app

**Infrastructure**
- [ ] HTTPS/TLS confirmed on the final Render URL (managed automatically, but verify the padlock)
- [ ] No PII collected anywhere — no login, no user accounts, no forms that store personal data. This is a genuine structural advantage: confirm it stays true as features are added (e.g., a future "save your filter preset" feature would change this)
- [ ] If a custom domain is added later, consider free Cloudflare in front of it for basic DDoS/bot protection — not essential at current traffic scale, worth doing before any real launch push (LinkedIn, recruiter outreach)

---

## 4. BUG-FINDING / QA CHECKLIST

**Automated**
- [ ] Add a minimal `pytest` suite for the business-logic layer (`filtering.py`, `scoring.py`, `valuation.py`) — pure functions, cheap to test, catches silent regressions as new fields/models get added
- [ ] Run a linter (`ruff` or `flake8`) across the codebase once, fix real issues
- [ ] Re-run the full PRD section-8 acceptance criteria list after every phase, not just once at the very end

**Manual, every phase**
- [ ] Zero-result filter state still shows the friendly message + reset button
- [ ] A company with heavily missing data (e.g. currency-fix-blanked HCLTECH) still renders cleanly, no crash, no blank white section
- [ ] Empty states for every new v2 feature: no news items for a company, no deal comps for a sector, Altman Z-Score not computable, term sheet for a company missing key fields
- [ ] Desktop Chrome + one mobile browser, every phase, not just once at the end
- [ ] A fresh pair of eyes (or a fresh Claude session with zero context) uses the live app cold, with no instructions — if anything is confusing, that's a real finding, not a nitpick

**Data integrity, ongoing**
- [ ] Every new refresh run gets its flagged-rows report actually looked at, not just generated
- [ ] Spot-audit match rate stays published and current, not a stale one-time claim

---

## 5. FUTURE-PROOFING / AUTO-UPDATE CHECKLIST

This is the part that keeps the app alive and correct after you stop actively working on it.

- [ ] GitHub Actions quarterly refresh workflow is live and has run successfully at least once before being trusted
- [ ] **Dead-man's-switch monitoring** on the refresh workflow: a free heartbeat service (e.g. healthchecks.io or cron-job.org, both free) pinged as the last step of every successful run. If the ping doesn't arrive on schedule, you get an email — this is the only reliable way to know a scheduled job silently stopped firing, since GitHub's own notifications only cover runs that actually happened
- [ ] Know about, and plan around, GitHub's own auto-disable: a public repo's scheduled workflows turn off after 60 days with zero commits. Either commit something periodically (even a changelog line) or accept manual reactivation and put a reminder somewhere real (calendar, not memory)
- [ ] (Optional) a separate free uptime monitor (UptimeRobot free tier) on the live Render URL itself — tells you if the *site*, not just the data refresh, goes down
- [ ] Dependency updates: check `requirements.txt` against current versions every few months — a silent yfinance or Streamlit breaking change is the most likely long-term failure mode for this project, more likely than anything else on this list
- [ ] Renew awareness that Render's free tier terms can change — re-check their free-tier page roughly every 6 months, since these change more often on hosting platforms than most people expect
- [ ] Keep `CONTEXT.md` / `V2_ROADMAP.md` / `EXECUTION_PLAN.md` updated as living documents whenever a real change is made — not just at the start of this project. A future session (yours or an AI's) should always be able to read them cold and know true current state

---

## 6. FINAL GO-LIVE GATE — before calling it done and sending it to recruiters

- [ ] Every box above in §1–§5 is either checked or has an explicit, written reason it's deliberately deferred (not silently skipped)
- [ ] Full PRD-style acceptance pass run fresh, on the final Render-hosted, redesigned UI — not trusting any earlier partial pass
- [ ] Security check re-run one final time, specifically re-checking git history for secrets (the single most common real-world portfolio-project mistake)
- [ ] Live URL tested cold, from a browser with no cache, on both desktop and mobile
- [ ] Methodology/limitations page is live and accurate to what's actually built, not what was planned
- [ ] Resume bullet and LinkedIn post drafted only after all of the above, not before
