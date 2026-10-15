# DealScope

Indian M&A target screener and peer valuation engine.

DealScope helps you screen Indian companies as acquisition targets and compare them against peers using fundamentals, deal context, and valuation bands.

## Stack

- Python
- Streamlit (`app.py`)
- Data refresh and export scripts under the repo root and `scripts/`

## Related frontend

The web UI lives in a separate repo:

- [RAM-cybe/dealscope-frontend](https://github.com/RAM-cybe/dealscope-frontend)
- Live site: [dealscope-frontend.vercel.app](https://dealscope-frontend.vercel.app)

## Run locally (high level)

1. Clone this repo and create a Python virtual environment.
2. Install dependencies from `requirements.txt`.
3. Put any API keys in a local env file or Streamlit secrets (never commit them).
4. Run the Streamlit app, for example: `streamlit run app.py`.

See `CONTEXT.md` and `docs/` for deeper architecture and data notes.
