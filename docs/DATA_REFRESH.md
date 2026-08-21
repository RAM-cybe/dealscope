# Data refresh

Two clocks, two gates. The data bot must be able to publish daily prices
without a long-lived token that can rewrite production.

| Job | What it refreshes | Cadence | Goes live? |
|---|---|---|---|
| Daily price refresh | Market cap | 04:00 UTC every day | Yes, auto-merged (circuit breaker can stop it) |
| Quarterly fundamentals | Revenue, EBITDA, margins, ROCE, debt | 1st of Jan / Apr / Jul / Oct | **No.** Snapshot + review PR only |
| Promote snapshot | Turns a reviewed snapshot into production | Manual | Opens PRs. A human merges them |

## Daily

`refresh_daily_prices.py` overwrites market cap in the live CSV, stamps
`market_cap_as_of` only on rows that actually refreshed, regenerates
`dataset-meta.json`, and pushes a `price-sync/<run-id>` branch to
`dealscope-frontend`. That repo's **Apply data-bot branch** workflow opens
a PR and squash-merges it (required reviews = 0). Vercel deploys from
`main`. The backend job waits for that merge before it reports success.

If more than 10% of companies that already had a market cap fail to refresh,
the job exits without writing. Last good data stays on the site.

## Quarterly (review only)

`refresh_quarterly_fundamentals.py` writes `data/snapshots/dealscope_YYYY-MM-DD.csv`.
The workflow opens a PR that contains the snapshot and a quality report.

Merging that PR does **not** change `data/live.json`, the frontend,
or the dates on the live site.

## Promotion (the only publish step)

1. Review and merge the quarterly snapshot PR.
2. Actions → **Promote snapshot** → Run workflow.
3. `snapshot_path`: `data/snapshots/dealscope_YYYY-MM-DD.csv`
4. Merge the backend promotion PR, then the frontend promotion PR.

Promotion keeps any live market caps that are newer than the snapshot, so
fundamentals can move forward without rolling prices back.

A limited (`DEALSCOPE_LIMIT`) smoke test must not be promoted.

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
- Auto-merge allowed (daily prices only; promotions never auto-merge).
