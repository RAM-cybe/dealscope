# Data refresh

Everything runs by itself. There is no human approval step anywhere.
Machines replace the reviewer, and every gate fails closed: when a check is
not satisfied, nothing new is published and the site keeps serving the last
good data.

| Job | What it refreshes | Cadence | Goes live? |
|---|---|---|---|
| Daily price refresh | Market cap | 11:00 UTC weekdays (16:30 IST) | Yes, automatically |
| Quarterly fundamentals | Revenue, EBITDA, margins, ROCE, debt | 03:00 UTC on the 1st of Jan / Apr / Jul / Oct | Yes, automatically, if the publish gate passes |
| Pipeline watchdog | Nothing: it repairs the two jobs above | Every 6 hours | Re-runs / dispatches them, opens one health issue |

## The safety chain

```
refresh -> sanitize -> publish gate -> push branch to frontend
        -> frontend validates (independent code) -> auto-merge -> Vercel deploy
        -> canary reads the live site -> roll back automatically if wrong
```

1. **Sanitizer** (`src/data/sanitize.py`). Values impossible for a real
   company (holding > 100%, negative revenue, |beta| > 10, current ratio >
   100, margin outside +/-300%, margin ~0 with real EBITDA) are replaced by the
   last-good live value, or null. It never invents a number. Every repair is
   written to `data/quality_reports/repairs_<snapshot>.csv`. The export step
   applies it too, so a bad value can never reach the site from any path.
2. **Publish gate** (`src/data/publish_gate.py`). Blocks the whole release if
   the candidate lost tickers (>1%), lost a column, lost field coverage
   (>5 points), moved a median outside its band (a unit bug looks like this),
   needed repairs on >5% of rows (the feed is broken, not just a few rows),
   still has a critical flag, or is older than the live data. Result:
   `data/quality_reports/gate_<snapshot>.md`.
3. **Release guard** (`src/data/release_guard.py`). A publish may never move
   `prices_as_of` or `fundamentals_as_of` backwards or shrink the universe.
4. **Frontend validator** (`dealscope-frontend/scripts/validate_data.py`).
   Separate code, same idea: shape, duplicates, impossible values, coverage,
   never roll back.
5. **Canary** (`apply-data-bot.yml`). After the merge it waits for the Vercel
   deployment, then checks that the live page shows the new "Prices as of /
   Fundamentals as of" dates. A failed deployment or a mismatch reverts the
   merge automatically and opens an issue. (A merely slow deployment is
   reported but not rolled back.)
6. **Watchdog** (`.github/scripts/watchdog.py`). Prices more than one weekday
   behind -> dispatch the daily job. Fundamentals older than 95 days ->
   dispatch the quarterly job. A failed run -> re-run once. A workflow disabled
   by GitHub for inactivity -> enable it. Everything it cannot fix goes into one
   `[DealScope] Pipeline health` issue, closed automatically when healthy.

Re-runs are safe: branch names include the run attempt, and the push script
treats an identical existing branch as success but refuses to overwrite
different data. Smoke tests (`limit` input) never publish.

## Daily

`refresh_daily_prices.py` overwrites market cap in the live CSV (NSE listing
first, BSE listing as a fallback when Yahoo has no NSE market cap), stamps
`market_cap_as_of` only on rows that actually refreshed, regenerates
`dataset-meta.json`, and pushes a `price-sync/<run-id>-<attempt>` branch to
`dealscope-frontend`, which validates, merges, deploys and canary-checks it.

If more than 10% of companies that already had a market cap fail to refresh
(including rows rejected as zero/negative, or as a >20x one-day move that
looks like a feed error), the job exits without writing. A row that fails
keeps yesterday's cap and yesterday's `market_cap_as_of`.

## Quarterly

`refresh_quarterly_fundamentals.py` writes `data/snapshots/dealscope_YYYY-MM-DD.csv`.
`promote_snapshot.py` then sanitizes it, runs the gate and, if it passes,
writes `data/enriched/dealscope_base_<date>.csv`, repoints `data/live.json`
and regenerates the frontend JSON. The workflow pushes a
`promote/<run-id>-<attempt>` branch, waits for the frontend to merge it, then
opens and merges the backend PR (snapshot, live pointer, reports).

Promotion keeps any live market caps that are newer than the snapshot, so
fundamentals move forward without rolling prices back.

If the gate blocks the snapshot the run fails (issue opens, reports are in the
`quarterly-reports` artifact) and the watchdog retries. To re-promote a stored
snapshot without a new 40-minute pull: Actions -> Quarterly data refresh ->
Run workflow -> `snapshot_path` = `data/snapshots/dealscope_YYYY-MM-DD.csv`.

A limited (`limit`) run never publishes.

## Dates on the site

`export_for_frontend.py` writes `dataset-meta.json`:

- `prices_as_of` — max `market_cap_as_of`
- `fundamentals_as_of` — modal `as_of_date`
- `stale_after_days` — 100; the site shows a banner past that

Daily and promote both regenerate this file. Do not edit it by hand.

## Monitoring

Set these repo secrets (free [healthchecks.io](https://healthchecks.io) ping URLs):

- `HEALTHCHECKS_DAILY_URL`
- `HEALTHCHECKS_QUARTERLY_URL`

Success pings the URL. Failure pings `URL/fail`. A failed run also opens a
GitHub issue so it cannot hide behind `|| true`. Auto-merge no longer
swallows errors either.

Those two secrets are **not set today**. Until they are, success/failure
still shows in the Actions job summary and as a GitHub issue on failure.
The ping step does not fake a green healthchecks.io check.

## Credentials (frontend publish)

Never put a token in a clone URL. Never force-push.

Preferred: a GitHub App with a short-lived installation token.

1. [Create a GitHub App](https://github.com/settings/apps/new) named
   `DealScope data bot` on the RAM-cybe account.
2. Homepage URL: `https://github.com/RAM-cybe/dealscope`. Uncheck webhook.
3. Repository permissions: **Contents: Read and write**. Nothing else.
4. Install it on `RAM-cybe/dealscope-frontend` only.
5. Generate a private key.
6. On `RAM-cybe/dealscope`:
   - variable `DEALSCOPE_APP_ID` = the App ID (number)
   - secret `DEALSCOPE_APP_PRIVATE_KEY` = the PEM contents

Until that App exists, the workflows use a **write deploy key**
(`FRONTEND_DEPLOY_KEY`) scoped to `dealscope-frontend`. It can push
branches; it cannot use the API, change settings, or force-push `main`
(ruleset). After the App is installed, the deploy key can be deleted.

Do **not** restore `FRONTEND_REPO_TOKEN`. That was a long-lived token
embedded in `https://x-access-token:...@github.com/...` clone URLs.

## Branch protection

Both repos:

- Ruleset **Protect main**: block force-push and branch deletion, including
  for admins. Required reviews stay at 0 so the data bot can merge.
- Automatically delete head branches after merge.
- Auto-merge allowed. The data bot merges its own validated branches; the
  frontend canary reverts them if the deployed site is wrong.
