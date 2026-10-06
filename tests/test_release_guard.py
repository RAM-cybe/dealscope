"""Release guard: a publish must never roll the live site backwards.

Run: python3 tests/test_release_guard.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.data.release_guard import check_release

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


CUR = {"prices_as_of": "2026-10-05", "fundamentals_as_of": "2026-07-11", "universe_size": 2381}

print("=== Allowed ===")
check("same dates", check_release(dict(CUR), CUR) == [])
check("newer prices", check_release({**CUR, "prices_as_of": "2026-10-06"}, CUR) == [])
check("newer fundamentals", check_release({**CUR, "fundamentals_as_of": "2026-10-01"}, CUR) == [])
check("1% fewer companies tolerated", check_release({**CUR, "universe_size": 2360}, CUR) == [])
check("no current meta (first ever release)", check_release(dict(CUR), None) == [])

print("=== Blocked: the 2026-10-06 incident ===")
r = check_release({**CUR, "prices_as_of": "2026-10-02"}, CUR)
check("older prices block", len(r) == 1 and r[0].startswith("prices_regress"), str(r))
r = check_release({**CUR, "fundamentals_as_of": "2026-04-01"}, CUR)
check("older fundamentals block", len(r) == 1 and r[0].startswith("fundamentals_regress"), str(r))
r = check_release({**CUR, "universe_size": 1200}, CUR)
check("universe shrink blocks", len(r) == 1 and r[0].startswith("universe_shrink"), str(r))
r = check_release({**CUR, "prices_as_of": None}, CUR)
check("missing prices date blocks", any(x.startswith("prices_regress") for x in r), str(r))
r = check_release({}, CUR)
check("empty meta blocks, does not raise", len(r) >= 1)

print("=== CLI ===")
with tempfile.TemporaryDirectory() as d:
    new, cur = Path(d, "new.json"), Path(d, "cur.json")
    cur.write_text(json.dumps(CUR))
    new.write_text(json.dumps({**CUR, "prices_as_of": "2026-10-02"}))
    p = subprocess.run([sys.executable, "-m", "src.data.release_guard", str(new), str(cur)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    check("exit 1 on regression", p.returncode == 1, p.stdout + p.stderr)
    check("message names the problem", "prices_regress" in p.stdout + p.stderr)
    new.write_text(json.dumps({**CUR, "prices_as_of": "2026-10-06"}))
    p = subprocess.run([sys.executable, "-m", "src.data.release_guard", str(new), str(cur)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    check("exit 0 when fine", p.returncode == 0, p.stdout + p.stderr)
    p = subprocess.run([sys.executable, "-m", "src.data.release_guard", str(new), str(Path(d, "missing.json"))],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    check("missing current meta is the first release, exit 0", p.returncode == 0, p.stdout + p.stderr)

print(f"\n{checks - failures}/{checks} checks passed")
sys.exit(1 if failures else 0)
