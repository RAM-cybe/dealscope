# DealScope — Implementation Plan

The phased build plan, current status, and the build/deploy workflow. This
complements `CONTEXT.md` (the living change-log) with a stable, at-a-glance
status view. Last updated 2026-07-16.

---

## Delivery workflow (locked)

- **One module/fix per unit of work**, independently verified (not self-reported)
  and committed before the next starts.
- **Test locally → commit → push → confirm live on the real production URL**
  before calling anything done. Never "works locally" alone.
- **Deploy = git push to `main`.** Render auto-builds and redeploys the Web
  Service from `main` (free tier, ~2–5 min). There is no separate deploy step.
- **Data refresh** is out-of-band: the quarterly GitHub Actions pipeline writes a
  dated snapshot, runs the quality checker, and opens a PR for human review —
  never auto-merges.
- **Local dev:** `streamlit run app.py` (a `.claude/launch.json` config exists for
  the in-tool preview). `.streamlit/config.toml` carries the dark theme +
  `showErrorDetails="none"`.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 0 — Cleanup | Retire Streamlit Cloud, public-repo decision, doc consolidation, `archive/` reorg | **Done** (reorg pushed 2026-07-16) |
| 1 — Lock feature list | Final feature list on paper before redesign | Folded into the design + this doc set |
| 2 — Data foundation | Enriched dataset live, currency guard, automated quality checker, quarterly GitHub Actions refresh, spot-audits | **Functionally complete**; remaining: add `ebit`/`total_liabilities` fields (blocks Altman) |
| 3 — Smarter analysis | Altman Z / Piotroski F / Beneish M scores; real news/filings via official RSS + Reg-30 tagging | **Deferred, not forgotten** — blocked on new fields + multi-period history |
| 4 — Security & admin | Secret scanning, push protection, Dependabot, pip-audit/bandit, pinned deps, external-call timeouts | **Complete** (0 CVEs, 0 open alerts as of 2026-07-16) |
| 5 — Term-sheet generator | Illustrative non-binding term sheet per company (PDF/Excel) | Not started (built last on purpose) |
| 6 — Full UI/UX redesign | The DealScope Final Design dark five-view flow | **Done and live (2026-07-16)** |
| 7 — Final polish | Provenance panel, side-by-side compare, sector dashboard, methodology page | Not started |
| 8 — Final QA & launch | Full acceptance re-run, edge cases, secret re-scan, then resume/LinkedIn/Big-4 outreach | Not started |

Ordering note: the redesign (Phase 6) shipped ahead of Phases 3/5 by Ram's
explicit call — he wanted the finished look live first. That does not close the
deferred analytics/term-sheet work.

## What "done" looked like for the redesign (Phase 6, 2026-07-16)

1. Confirm production stable on streamlit 1.54.0 (no regression) before building.
2. Reconcile local repo to `origin/main`; stand up a local dev server.
3. Rewrite `app.py`'s presentation layer to the five-view flow; leave `src/`
   untouched.
4. Iterate each view against the local server (caught and fixed a real
   `%`-format bug and a search-regex bug this way).
5. Push; confirm all five views + parity live on production.
6. Security + data audits; documentation; push the parked reorg.

## The parked reorg — now resolved

For several sessions, the consolidated `CONTEXT.md` plus the move of the old
planning docs (`EXECUTION_PLAN.md`, `SHIP_CHECKLIST.md`, `V2_ROADMAP.md`,
`files/PRD.md`, `files/BLUEPRINT.md`) into `archive/old_planning_docs/` sat
locally, unpushed, awaiting approval because it changes the public repo layout.
Approved and **pushed 2026-07-16**. Local-only scratch (`.claude/`, logs, the
`.dc.html` design mockups, leftover test CSVs) is gitignored rather than
committed. The live `CONTEXT.md` on GitHub now reflects the actual current state.
