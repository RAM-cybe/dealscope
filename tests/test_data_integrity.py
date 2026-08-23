"""Live pointer, as-of dates, and CSV/JSON agreement.

Scoring and daily refresh both regenerate dataset-meta.json from the live
CSV. These checks make sure the dates on every page cannot silently drift
apart from the file they describe.

Run: python3 tests/test_data_integrity.py
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.data.paths import (
    FRONTEND_DATA_DIR,
    LIVE_MANIFEST_PATH,
    companies_csv_path,
    deals_csv_path,
    load_live_manifest,
)
from src.data.schema import REQUIRED_COMPANY_COLUMNS, REQUIRED_DEAL_COLUMNS

failures = 0
checks = 0


def check(name, cond, detail=""):
    global failures, checks
    checks += 1
    if not cond:
        failures += 1
        print(f"  FAIL  {name}{('  -- ' + detail) if detail else ''}")
    else:
        print(f"  ok    {name}")


print("=== Live pointer ===")
manifest = load_live_manifest()
check("live.json exists", LIVE_MANIFEST_PATH.is_file())
check("companies path is under data/", str(manifest["companies"]).startswith("data/"))
check("deals path is under data/", str(manifest["deals"]).startswith("data/"))
check("companies CSV exists", companies_csv_path().is_file())
check("deals CSV exists", deals_csv_path().is_file())

print("\n=== CSV schema ===")
companies = pd.read_csv(companies_csv_path())
deals = pd.read_csv(deals_csv_path())
missing_c = [c for c in REQUIRED_COMPANY_COLUMNS if c not in companies.columns]
missing_d = [c for c in REQUIRED_DEAL_COLUMNS if c not in deals.columns]
check("companies CSV has required columns", not missing_c, f"missing {missing_c}")
check("deals CSV has required columns", not missing_d, f"missing {missing_d}")
check("universe is non-empty", len(companies) > 0, f"n={len(companies)}")

print("\n=== dataset-meta.json matches the live CSV ===")
meta_path = FRONTEND_DATA_DIR / "dataset-meta.json"
check("dataset-meta.json exists", meta_path.is_file())
meta = json.loads(meta_path.read_text())
as_of = pd.to_datetime(companies["as_of_date"], errors="coerce")
mcap_as_of = pd.to_datetime(companies["market_cap_as_of"], errors="coerce") if "market_cap_as_of" in companies.columns else pd.Series(dtype="datetime64[ns]")
as_of_counts = as_of.dt.strftime("%Y-%m-%d").value_counts(dropna=True)
fundamentals_mode = as_of_counts.idxmax() if len(as_of_counts) else None
prices_max = mcap_as_of.max().strftime("%Y-%m-%d") if mcap_as_of.notna().any() else None
check("prices_as_of is the max market_cap_as_of", meta.get("prices_as_of") == prices_max,
      f"meta={meta.get('prices_as_of')} csv={prices_max}")
check("fundamentals_as_of is the modal as_of_date", meta.get("fundamentals_as_of") == fundamentals_mode,
      f"meta={meta.get('fundamentals_as_of')} csv={fundamentals_mode}")
check("universe_size matches the companies CSV", meta.get("universe_size") == len(companies),
      f"meta={meta.get('universe_size')} csv={len(companies)}")
check("deal_count matches the deals CSV", meta.get("deal_count") == len(deals),
      f"meta={meta.get('deal_count')} csv={len(deals)}")

print("\n=== Frontend JSON agrees with meta ===")
companies_json_path = FRONTEND_DATA_DIR / "companies.json"
check("companies.json exists", companies_json_path.is_file())
payload = json.loads(companies_json_path.read_text())
check("companies.json row count matches meta", len(payload) == meta.get("universe_size"),
      f"json={len(payload)} meta={meta.get('universe_size')}")
json_as_of = {row.get("as_of_date") for row in payload if row.get("as_of_date")}
json_mcap = [row.get("market_cap_as_of") for row in payload if row.get("market_cap_as_of")]
check("every company JSON row has as_of_date", all(row.get("as_of_date") for row in payload))
check("JSON as_of_date set matches the CSV", json_as_of == set(as_of_counts.index),
      f"json={sorted(json_as_of)} csv={sorted(as_of_counts.index)}")
if json_mcap:
    check("JSON max market_cap_as_of matches prices_as_of", max(json_mcap) == meta.get("prices_as_of"),
          f"json={max(json_mcap)} meta={meta.get('prices_as_of')}")

print("\n=== Factor percentiles are real numbers or blank, never inf ===")
factor_keys = ("factor_revenue_growth", "factor_ebitda_margin", "factor_roce", "factor_debt_level")
bad_inf = 0
for row in payload:
    for key in factor_keys:
        value = row.get(key)
        if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
            bad_inf += 1
check("no inf/NaN slipped into JSON factor fields", bad_inf == 0, f"bad={bad_inf}")

print(f"\n{checks - failures}/{checks} checks passed")
if failures:
    sys.exit(1)
