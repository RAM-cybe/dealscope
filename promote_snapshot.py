"""Promote a reviewed quarterly snapshot to the live dataset.

This is the only path that turns a candidate snapshot into production data.
It does not push, merge, or talk to the frontend repo — the Promote snapshot
workflow opens review PRs from the files this script writes.

What it does:
  1. Load the snapshot and the current live CSV.
  2. Keep live market_cap / market_cap_as_of when they are newer than the
     snapshot, so promoting fundamentals never rolls prices backwards.
  3. Copy the merged frame to data/enriched/dealscope_base_<date>.csv.
  4. Point DEFAULT_COMPANIES_PATH at that file.
  5. Regenerate frontend JSON (including dataset-meta.json dates).

Run from the repo root:
    python3 promote_snapshot.py data/snapshots/dealscope_2026-10-01.csv
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from src.data.loaders import DEFAULT_COMPANIES_PATH, load_companies  # noqa: E402

LIVE_POINTER = REPO_ROOT / "src" / "data" / "loaders.py"
ENRICHED_DIR = REPO_ROOT / "data" / "enriched"
POINTER_RE = re.compile(
    r'(DEFAULT_COMPANIES_PATH = _PROJECT_ROOT / "data" / "enriched" / ")'
    r'dealscope_base_\d{4}-\d{2}-\d{2}\.csv(")'
)


def merge_live_prices(snapshot: pd.DataFrame, live: pd.DataFrame) -> pd.DataFrame:
    """Prefer live market caps when they are dated on or after the snapshot's."""
    out = snapshot.copy()
    if "market_cap" not in live.columns or "symbol" not in live.columns:
        return out
    live_idx = live.set_index("symbol")
    for i, row in out.iterrows():
        symbol = row["symbol"]
        if symbol not in live_idx.index:
            continue
        live_cap = live_idx.at[symbol, "market_cap"] if "market_cap" in live_idx.columns else None
        live_as_of = None
        snap_as_of = None
        if "market_cap_as_of" in live_idx.columns:
            live_as_of = live_idx.at[symbol, "market_cap_as_of"]
        if "market_cap_as_of" in out.columns:
            snap_as_of = row.get("market_cap_as_of")
        live_newer = False
        if pd.notna(live_as_of) and (snap_as_of is None or pd.isna(snap_as_of) or str(live_as_of) >= str(snap_as_of)):
            live_newer = True
        if live_newer and pd.notna(live_cap):
            out.at[i, "market_cap"] = live_cap
            if "market_cap_as_of" in out.columns:
                out.at[i, "market_cap_as_of"] = live_as_of
    return out


def repoint_live_dataset(new_name: str) -> None:
    text = LIVE_POINTER.read_text()
    replaced, n = POINTER_RE.subn(rf"\1{new_name}\2", text, count=1)
    if n != 1:
        raise RuntimeError(
            f"Could not update DEFAULT_COMPANIES_PATH in {LIVE_POINTER} "
            f"(expected exactly one match, got {n})"
        )
    LIVE_POINTER.write_text(replaced)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 promote_snapshot.py <snapshot_csv>")
        sys.exit(2)

    snapshot_path = Path(sys.argv[1]).expanduser()
    if not snapshot_path.is_absolute():
        snapshot_path = REPO_ROOT / snapshot_path
    snapshot_path = snapshot_path.resolve()
    snapshots_root = (REPO_ROOT / "data" / "snapshots").resolve()
    if snapshots_root not in snapshot_path.parents and snapshot_path.parent != snapshots_root:
        print(f"Refusing to promote a file outside data/snapshots/: {snapshot_path}")
        sys.exit(2)
    if not snapshot_path.name.startswith("dealscope_") or snapshot_path.suffix != ".csv":
        print(f"Snapshot name must look like dealscope_YYYY-MM-DD.csv, got {snapshot_path.name}")
        sys.exit(2)
    if not snapshot_path.exists():
        print(f"Snapshot not found: {snapshot_path}")
        sys.exit(2)

    print(f"Validating snapshot: {snapshot_path}")
    load_companies(snapshot_path)

    snapshot = pd.read_csv(snapshot_path)
    live = pd.read_csv(DEFAULT_COMPANIES_PATH)
    merged = merge_live_prices(snapshot, live)

    stamp = snapshot_path.stem.replace("dealscope_", "")
    dest_name = f"dealscope_base_{stamp}.csv"
    dest = ENRICHED_DIR / dest_name
    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(dest, index=False)
    print(f"Wrote live candidate: {dest}")

    repoint_live_dataset(dest_name)
    print(f"DEFAULT_COMPANIES_PATH -> data/enriched/{dest_name}")

    from export_for_frontend import main as export_main

    export_main()
    print("Frontend JSON regenerated (including dataset-meta.json dates).")
    print("Next: open review PRs. Merging those PRs is what goes live.")


if __name__ == "__main__":
    main()
