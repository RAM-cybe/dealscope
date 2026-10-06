"""Never let a release roll the live site backwards.

Compares the dataset-meta.json about to be published with the one currently
live on the frontend. Born from the 2026-10-06 incident, where a 20-company
smoke test published the backend's older committed export and moved the live
site's prices from 2026-10-05 back to 2026-10-02.

    python -m src.data.release_guard <new_meta.json> <current_meta.json>

Exit 0 = safe, 1 = would regress (reasons printed). A missing current file is
treated as the first release.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MAX_UNIVERSE_SHRINK = 0.01


def _date(meta, key):
    value = (meta or {}).get(key)
    return str(value) if value else ""


def check_release(new_meta, current_meta):
    if current_meta is None:
        return []
    problems = []
    for key, code in (("prices_as_of", "prices_regress"), ("fundamentals_as_of", "fundamentals_regress")):
        new, cur = _date(new_meta, key), _date(current_meta, key)
        if cur and new < cur:
            problems.append(f"{code}: {key} would move {cur} -> {new or 'missing'}")
    try:
        new_size = int((new_meta or {}).get("universe_size") or 0)
        cur_size = int((current_meta or {}).get("universe_size") or 0)
    except (TypeError, ValueError):
        new_size, cur_size = 0, 1
    if cur_size and new_size < cur_size * (1 - MAX_UNIVERSE_SHRINK):
        problems.append(f"universe_shrink: universe_size would move {cur_size} -> {new_size}")
    return problems


def _load(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("Usage: python -m src.data.release_guard <new_meta.json> <current_meta.json>")
        return 2
    problems = check_release(_load(argv[0]) or {}, _load(argv[1]))
    for p in problems:
        print(f"::error::{p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
