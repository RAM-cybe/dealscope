"""The frontend export never ships an impossible value, even from a dirty CSV.

Run: python3 tests/test_export_clean.py
"""

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from export_for_frontend import clean_companies_for_export
from src.data.loaders import load_companies

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


live_path = REPO_ROOT / "data" / "enriched" / "dealscope_base_2026-07-22.csv"
df = load_companies(live_path)
# The July file already contains the real-world offenders (GLOBE 133% etc).
before_bad_holding = int((df["insider_holding_pct"] > 100).sum())
check("fixture really contains impossible holdings", before_bad_holding > 0)

cleaned = clean_companies_for_export(df)
check("row count unchanged", len(cleaned) == len(df))
check("no holding above 100", not (cleaned["insider_holding_pct"] > 100).any())
check("no |beta| above 10", not (cleaned["beta"].abs() > 10).any())
check("no negative revenue", not (cleaned["revenue"] < 0).any())
check("ey_bucket / sector_v2 columns survive", {"ey_bucket", "sector_v2"} <= set(cleaned.columns))
check("input frame untouched", int((df["insider_holding_pct"] > 100).sum()) == before_bad_holding)

print(f"\n{checks - failures}/{checks} checks passed")
sys.exit(1 if failures else 0)
