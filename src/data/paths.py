"""Canonical paths for the live dataset and the frontend staging folder.

Production identity lives in data/live.json so promotion does not have to
rewrite Python. Daily price refresh writes in place to the companies CSV
named there. Quarterly snapshots stay under data/snapshots/; promoting one
copies it to data/enriched/ and updates live.json.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIVE_MANIFEST_PATH = PROJECT_ROOT / "data" / "live.json"
FRONTEND_DATA_DIR = PROJECT_ROOT / "data" / "frontend"
SNAPSHOTS_DIR = PROJECT_ROOT / "data" / "snapshots"
ENRICHED_DIR = PROJECT_ROOT / "data" / "enriched"


def load_live_manifest() -> dict:
    data = json.loads(LIVE_MANIFEST_PATH.read_text())
    if not isinstance(data, dict) or "companies" not in data or "deals" not in data:
        raise RuntimeError(f"Invalid live dataset pointer: {LIVE_MANIFEST_PATH}")
    return data


def companies_csv_path() -> Path:
    return PROJECT_ROOT / load_live_manifest()["companies"]


def deals_csv_path() -> Path:
    return PROJECT_ROOT / load_live_manifest()["deals"]


def write_live_manifest(*, companies: str, deals: str | None = None, **extra) -> None:
    current = load_live_manifest()
    current["companies"] = companies
    if deals is not None:
        current["deals"] = deals
    current.update(extra)
    current["schema_version"] = int(current.get("schema_version", 1))
    LIVE_MANIFEST_PATH.write_text(json.dumps(current, indent=2) + "\n")
