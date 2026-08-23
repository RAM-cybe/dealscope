"""Landmark deal rescue and sector_raw lookup.

The 48 blank-sector_raw deals are classified by exact CSV identity, not by
inventing a sector_raw label. Sister deals that share a target name keep
their existing labelled mapping.

Run: python3 tests/test_deals_sector_v2.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.data.deals_sector_v2 import (
    LANDMARK_DEAL_SECTOR_V2,
    classify_deal_sector_v2,
    landmark_deal_key,
)
from src.data.loaders import load_deals
from src.data.sector_taxonomy_v2 import SECTOR_V2_BUCKETS, UNCLASSIFIED_V2

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


print("=== Landmark map is well-formed ===")
check("exactly 48 landmark identities", len(LANDMARK_DEAL_SECTOR_V2) == 48,
      f"n={len(LANDMARK_DEAL_SECTOR_V2)}")
check("no duplicate landmark keys", len(LANDMARK_DEAL_SECTOR_V2) == len(set(LANDMARK_DEAL_SECTOR_V2)))
bad_buckets = sorted({
    sector for sector in LANDMARK_DEAL_SECTOR_V2.values()
    if sector not in SECTOR_V2_BUCKETS
})
check("every landmark sector is a v2 bucket", not bad_buckets, f"bad={bad_buckets}")

print("\n=== Blank sector_raw stays Unclassified without an identity ===")
check("null sector_raw, no identity", classify_deal_sector_v2(None) == UNCLASSIFIED_V2)
check("Others without identity stays Unclassified",
      classify_deal_sector_v2("Others") == UNCLASSIFIED_V2)
check("labelled Pharma still Healthcare",
      classify_deal_sector_v2("Pharma") == "Healthcare & Lifesciences")

print("\n=== Live CSV: every landmark identity exists once and is rescued ===")
deals = load_deals()
missing = []
collisions = []
wrong = []
for (target, acquirer, year), sector in LANDMARK_DEAL_SECTOR_V2.items():
    match = deals[
        (deals["target"].astype(str).str.strip() == target)
        & (deals["acquirer"].astype(str).str.strip() == acquirer)
        & (deals["report_year"].map(lambda y: landmark_deal_key(target, acquirer, y) == (target, acquirer, year)))
    ]
    if len(match) == 0:
        missing.append((target, acquirer, year))
        continue
    if len(match) != 1:
        collisions.append((target, acquirer, year, len(match)))
        continue
    got = match.iloc[0]["sector_v2"]
    if got != sector:
        wrong.append((target, year, sector, got))

check("every landmark key hits a live deal", not missing,
      f"missing={missing[:5]} n={len(missing)}")
check("no landmark key hits more than one live deal", not collisions,
      f"collisions={collisions}")
check("every landmark deal has the lock sector", not wrong, f"wrong={wrong[:5]} n={len(wrong)}")

unclassified = deals[deals["sector_v2"] == UNCLASSIFIED_V2]
check("no unclassified deals remain after rescue", len(unclassified) == 0,
      f"n={len(unclassified)} sample={unclassified['target'].head(3).tolist() if len(unclassified) else []}")

print("\n=== Sister deals that share a target name are not reassigned ===")
flipkart_2015 = deals[
    (deals["target"].astype(str).str.strip() == "Flipkart")
    & (deals["report_year"] == 2015)
]
check("Flipkart 2015 still Consumer Discretionary (labelled)",
      len(flipkart_2015) == 2 and (flipkart_2015["sector_v2"] == "Consumer Discretionary & Retail").all(),
      f"n={len(flipkart_2015)} sectors={flipkart_2015['sector_v2'].tolist()}")

credila_labelled = deals[
    (deals["target"].astype(str).str.strip() == "HDFC Credila Financial Services Ltd")
    & (deals["acquirer"].astype(str).str.strip() == "BPEA EQT and ChrysCapital")
]
check("labelled Credila 2023 stays Financial Services",
      len(credila_labelled) == 1
      and credila_labelled.iloc[0]["sector_v2"] == "Financial Services")

manipal_labelled = deals[
    (deals["target"].astype(str).str.strip() == "Manipal Health Enterprises Pvt Ltd")
    & (deals["acquirer"].astype(str).str.strip() == "Temasek Holdings")
]
check("labelled Manipal 2023 stays Healthcare",
      len(manipal_labelled) == 1
      and manipal_labelled.iloc[0]["sector_v2"] == "Healthcare & Lifesciences")

print("\n=== AdPushup 'Others' is rescued by identity, not by remapping Others ===")
adpushup = deals[
    (deals["target"].astype(str).str.strip() == "AdPushup")
    & (deals["acquirer"].astype(str).str.strip() == "Geniee")
]
check("AdPushup is Technology & IT Services",
      len(adpushup) == 1 and adpushup.iloc[0]["sector_v2"] == "Technology & IT Services")
check("generic Others lookup is still Unclassified",
      classify_deal_sector_v2("Others") == UNCLASSIFIED_V2)

print(f"\n{checks - failures}/{checks} checks passed")
if failures:
    sys.exit(1)
