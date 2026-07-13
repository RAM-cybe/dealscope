import os
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
from pathlib import Path

# Both overridable via env var so the quarterly refresh workflow can point
# this at whatever the app's actual current live dataset is (see
# src/data/loaders.py's DEFAULT_COMPANIES_PATH) and write into
# data/snapshots/ instead of the CWD, without changing default local-run
# behavior when run standalone.
INPUT_FILE = os.environ.get("DEALSCOPE_INPUT_FILE", "companies_full_v2.csv")
OUTPUT_DIR = Path(os.environ.get("DEALSCOPE_OUTPUT_DIR", "."))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
_STAMP = datetime.now().strftime('%Y-%m-%d')
OUTPUT_PARQUET = OUTPUT_DIR / f"dealscope_{_STAMP}.parquet"
OUTPUT_CSV = OUTPUT_DIR / f"dealscope_{_STAMP}.csv"
BATCH_SIZE = 100
SLEEP_BETWEEN = 1.2

# currency_flag != "OK" means yfinance's own financialCurrency metadata says
# this symbol's *.info-sourced figures aren't in INR -- revenue/ebitda/
# total_debt/net_income already get this protection for free (they're
# inherited from companies_full_v2.csv, itself already blanked for
# currency-flagged symbols). These 6 new fields are freshly pulled here and
# need the same guard explicitly. Confirmed empirically (2026-07-13, not
# assumed): for both currency-flagged symbols in this dataset (INFY,
# HCLTECH), every one of these 6 fields is USD-scale -- roughly 100x too
# small versus same-sector INR peers on a value/market_cap ratio basis. Do
# not narrow this to a subset of the 6 based on how any one field looks --
# a field looking "plausible" for one flagged symbol doesn't confirm it's
# actually INR (see HCLTECH: total_assets/working_capital happened to sit in
# a peer-plausible ratio range while total_cash/operating_cash_flow/
# free_cash_flow did not, for the same company, same flag) -- blank
# defensively per the project's established currency-bug precedent.
CURRENCY_SENSITIVE_NEW_FIELDS = [
    "total_assets", "retained_earnings", "working_capital",
    "total_cash", "operating_cash_flow", "free_cash_flow",
]

print("Loading existing dataset...")
df = pd.read_csv(INPUT_FILE)
print(f"Loaded {len(df)} companies")

# Test-only: DEALSCOPE_LIMIT truncates the pull to the first N companies, so
# a workflow_dispatch smoke-test can confirm the whole pipeline (pull ->
# snapshot -> quality check -> PR) in under a minute instead of the ~45+
# minutes a full 2,046-company quarterly run takes. Unset (the default) for
# every real scheduled run -- never used to silently skip companies in
# production.
_limit = os.environ.get("DEALSCOPE_LIMIT")
if _limit:
    df = df.head(int(_limit))
    print(f"DEALSCOPE_LIMIT set -- truncated to first {len(df)} companies (test run only)")

results = []

for idx, row in df.iterrows():
    symbol = row['symbol']
    ticker = f"{symbol}.NS"
    print(f"[{idx+1}/{len(df)}] {ticker} ...", end=" ")

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        fin_currency = info.get('financialCurrency', 'INR')
        currency_flag = "OK" if fin_currency == "INR" else "USD_REPORTED"

        bs = stock.balance_sheet
        total_assets = retained_earnings = working_capital = None

        if not bs.empty:
            latest = bs.columns[0]
            if 'Total Assets' in bs.index:
                total_assets = bs.loc['Total Assets', latest]
            if 'Retained Earnings' in bs.index:
                retained_earnings = bs.loc['Retained Earnings', latest]
            if 'Current Assets' in bs.index and 'Current Liabilities' in bs.index:
                working_capital = bs.loc['Current Assets', latest] - bs.loc['Current Liabilities', latest]

        new_row = {
            'symbol': symbol,
            'name': row.get('name', ''),
            'sector': row.get('sector', ''),
            'industry': row.get('industry', ''),
            'revenue': row.get('revenue'),
            'ebitda': row.get('ebitda'),
            'ebitda_margin_pct': row.get('ebitda_margin_pct'),
            'total_debt': row.get('total_debt'),
            'market_cap': row.get('market_cap'),
            'insider_holding_pct': row.get('insider_holding_pct'),
            'revenue_growth_pct': row.get('revenue_growth_pct'),
            'return_on_equity_pct': row.get('return_on_equity_pct'),
            'return_on_capital_employed_pct': row.get('return_on_capital_employed_pct'),
            'promoter_pledge_pct': row.get('promoter_pledge_pct'),
            'net_income': row.get('net_income'),
            'as_of_date': row.get('as_of_date'),
            'status': row.get('status', 'ok'),
            'financial_currency': fin_currency,
            'currency_flag': currency_flag,
            'total_assets': total_assets,
            'retained_earnings': retained_earnings,
            'working_capital': working_capital,
            'current_ratio': info.get('currentRatio'),
            'quick_ratio': info.get('quickRatio'),
            'debt_to_equity': info.get('debtToEquity'),
            'return_on_assets': info.get('returnOnAssets'),
            'beta': info.get('beta'),
            'peg_ratio': info.get('pegRatio'),
            'enterprise_value': info.get('enterpriseValue'),
            'total_cash': info.get('totalCash'),
            'operating_cash_flow': info.get('operatingCashflow'),
            'free_cash_flow': info.get('freeCashflow'),
            'price_to_book': info.get('priceToBook'),
            'trailing_pe': info.get('trailingPE'),
            'data_pull_date': datetime.now().strftime('%Y-%m-%d'),
        }

        if currency_flag != "OK":
            for field in CURRENCY_SENSITIVE_NEW_FIELDS:
                new_row[field] = None

        results.append(new_row)
        print("OK")

    except Exception as e:
        print(f"ERROR: {str(e)[:50]}")

    if (idx + 1) % BATCH_SIZE == 0:
        temp_df = pd.DataFrame(results)
        # Clean numeric columns (fix Infinity and other bad values)
        for col in ['trailing_pe', 'forward_pe', 'peg_ratio', 'beta', 'price_to_book', 'current_ratio', 'quick_ratio', 'debt_to_equity']:
            if col in temp_df.columns:
                temp_df[col] = pd.to_numeric(temp_df[col], errors='coerce')
        temp_df.to_parquet(OUTPUT_PARQUET, index=False)
        print(f"  Saved progress...")

    time.sleep(SLEEP_BETWEEN)

# Final save with cleaning
final_df = pd.DataFrame(results)
for col in ['trailing_pe', 'forward_pe', 'peg_ratio', 'beta', 'price_to_book', 'current_ratio', 'quick_ratio', 'debt_to_equity']:
    if col in final_df.columns:
        final_df[col] = pd.to_numeric(final_df[col], errors='coerce')

final_df.to_parquet(OUTPUT_PARQUET, index=False)
final_df.to_csv(OUTPUT_CSV, index=False)
print(f"\nDone! Files created:\n- {OUTPUT_PARQUET}\n- {OUTPUT_CSV}")
