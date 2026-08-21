# Architecture

Two repos, one data clock.

| Repo | Role |
|---|---|
| `RAM-cybe/dealscope` | Dataset, scoring, refresh jobs |
| `RAM-cybe/dealscope-frontend` | The public site |

The backend never serves HTTP. The frontend never pulls yfinance. JSON
copied by the data bot is the only join.

## Live data pointer

`data/live.json` names the CSV files in production:

```json
{ "schema_version": 1, "companies": "data/enriched/dealscope_base_YYYY-MM-DD.csv", "deals": "data/deals.csv" }
```

Daily prices overwrite that companies file in place. A quarterly snapshot
is a new file under `data/snapshots/`. Promoting it copies the snapshot to
`data/enriched/` and updates `live.json`. Nothing in Python is rewritten.

## Frontend payload

`export_for_frontend.py` writes `data/frontend/`:

- `companies.json` — screening numbers only (no long text)
- `narratives.json` — about / why-this-score, keyed by ticker
- `deals.json`, `filter-bands.json`, `sector-bands.json`, `dataset-meta.json`

The site loads `companies.json` for search and ranking. Tear-sheet copy and
`news.json` load after first paint, so the landing page does not parse 12MB.

## Do not

- Put a token in a git clone URL
- Force-push `main`
- Auto-merge a fundamentals promotion
- Serve screening from a database or a live API
