"""Promote a quarterly snapshot to the live dataset -- automatically.

This is the only path that turns a candidate snapshot into production data.
It does not push, merge, or talk to the frontend repo; the workflow does that
from the files this script writes.

There is no human approval step. Two machine checks replace it:
  * src/data/sanitize.py repairs values that are impossible for a real
    company (last-good value, else null -- never an invented number).
  * src/data/publish_gate.py blocks the whole promotion if the result looks
    wrong (lost tickers, coverage collapse, drifted medians, too many
    repairs, any critical flag left). A blocked run writes only reports.

What it does:
  1. Load the snapshot and the current live CSV.
  2. Keep live market_cap / market_cap_as_of when they are newer than the
     snapshot, so promoting fundamentals never rolls prices backwards.
  3. Sanitize, then run the publish gate. Always write the repair report and
     gate summary to data/quality_reports/. Exit 3 if blocked.
  4. Copy the merged frame to data/enriched/dealscope_base_<date>.csv.
  5. Point data/live.json at that file.
  6. Regenerate frontend JSON (including dataset-meta.json dates).

Run from the repo root:
    python3 promote_snapshot.py data/snapshots/dealscope_2026-10-01.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from src.data.loaders import load_companies  # noqa: E402
from src.data.paths import (  # noqa: E402
    ENRICHED_DIR,
    SNAPSHOTS_DIR,
    companies_csv_path,
    write_live_manifest,
)
from src.data.publish_gate import evaluate_gate  # noqa: E402
from src.data.sanitize import sanitize  # noqa: E402

EXIT_BLOCKED = 3


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


def prepare_candidate(snapshot: pd.DataFrame, live: pd.DataFrame):
    """Pure decision step: returns (cleaned_frame, repairs, gate_result)."""
    merged = merge_live_prices(snapshot, live)
    cleaned, repairs = sanitize(merged, live=live)
    gate = evaluate_gate(cleaned, live, repairs)
    return cleaned, repairs, gate


def repoint_live_dataset(rel_path: str) -> None:
    write_live_manifest(companies=rel_path)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 promote_snapshot.py <snapshot_csv>")
        sys.exit(2)

    snapshot_path = Path(sys.argv[1]).expanduser()
    if not snapshot_path.is_absolute():
        snapshot_path = REPO_ROOT / snapshot_path
    snapshot_path = snapshot_path.resolve()
    snapshots_root = SNAPSHOTS_DIR.resolve()
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
    live = pd.read_csv(companies_csv_path())
    stamp = snapshot_path.stem.replace("dealscope_", "")
    merged, repairs, gate = prepare_candidate(snapshot, live)

    reports = REPO_ROOT / "data" / "quality_reports"
    reports.mkdir(parents=True, exist_ok=True)
    repairs.to_csv(reports / f"repairs_{stamp}.csv", index=False)
    (reports / f"gate_{stamp}.md").write_text(gate.markdown())
    print(gate.markdown())
    print(f"Repairs: {len(repairs)} cell(s) across {repairs['symbol'].nunique()} row(s) "
          f"-> data/quality_reports/repairs_{stamp}.csv")
    if not gate.passed:
        print("PROMOTION BLOCKED by the publish gate. Nothing was written to the live dataset; "
              "the site keeps serving the last good data.")
        sys.exit(EXIT_BLOCKED)

    dest_name = f"dealscope_base_{stamp}.csv"
    dest = ENRICHED_DIR / dest_name
    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(dest, index=False)
    print(f"Wrote live candidate: {dest}")

    rel_path = f"data/enriched/{dest_name}"
    repoint_live_dataset(rel_path)
    print(f"data/live.json companies -> {rel_path}")

    from export_for_frontend import main as export_main

    export_main()
    print("Frontend JSON regenerated (including dataset-meta.json dates).")
    print("Next: the workflow commits, merges and verifies the deploy.")


if __name__ == "__main__":
    main()
