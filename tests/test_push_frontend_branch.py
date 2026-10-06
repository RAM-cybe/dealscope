"""Integration test for .github/scripts/push_frontend_branch.sh against a real
(local, throwaway) git remote.

Run: python3 tests/test_push_frontend_branch.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "push_frontend_branch.sh"
FILES = ["companies", "narratives", "deals", "filter-bands", "sector-bands", "dataset-meta"]

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


def git(*args, cwd, check_rc=True):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          cwd=cwd, capture_output=True, text=True, check=check_rc)


def write_data(directory, version, prices="2026-10-05"):
    directory.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        payload = {"v": version}
        if f == "dataset-meta":
            payload = {"prices_as_of": prices, "fundamentals_as_of": "2026-07-11",
                       "universe_size": 2381, "v": version}
        (directory / f"{f}.json").write_text(json.dumps(payload))


tmp = Path(tempfile.mkdtemp())
try:
    remote = tmp / "remote.git"
    git("init", "-q", "--bare", str(remote), cwd=tmp)
    seed = tmp / "seed"
    git("clone", "-q", str(remote), str(seed), cwd=tmp, check_rc=False)
    write_data(seed / "data", 0)
    git("checkout", "-q", "-B", "main", cwd=seed)
    git("add", ".", cwd=seed)
    git("commit", "-qm", "seed", cwd=seed)
    git("push", "-q", "origin", "main", cwd=seed)
    git("--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main", cwd=tmp)

    workspace = tmp / "ws"

    def run(branch, version=1, prices="2026-10-05"):
        write_data(workspace / "data" / "frontend", version, prices)
        fe = tmp / "fe"
        shutil.rmtree(fe, ignore_errors=True)
        git("clone", "-q", str(remote), str(fe), cwd=tmp)
        env = {**os.environ, "GITHUB_WORKSPACE": str(workspace)}
        env.pop("GITHUB_OUTPUT", None)
        p = subprocess.run(["bash", str(SCRIPT), str(fe), branch, "msg"], env=env,
                           capture_output=True, text=True, cwd=REPO_ROOT)
        return p, p.stdout + p.stderr

    def remote_branches():
        return git("--git-dir", str(remote), "branch", "--format=%(refname:short)", cwd=tmp).stdout.split()

    print("=== New branch ===")
    p, out = run("price-sync/1-1")
    check("pushes a new branch", p.returncode == 0 and "price-sync/1-1" in remote_branches(), out)

    print("=== Re-run with identical data (the 2026-10-06 failure) ===")
    p, out = run("price-sync/1-1")
    check("identical data on an existing branch is success", p.returncode == 0, out)

    print("=== Same name, different data ===")
    p, out = run("price-sync/1-1", version=2)
    check("refuses to overwrite and fails loudly", p.returncode != 0 and "refusing to overwrite" in out, out)

    print("=== Next attempt gets a fresh name ===")
    p, out = run("price-sync/1-2", version=2)
    check("new attempt name succeeds", p.returncode == 0 and "price-sync/1-2" in remote_branches(), out)

    print("=== Safety rails ===")
    p, out = run("main")
    check("never pushes to main", p.returncode != 0 and "Refusing to push directly" in out, out)

    print("=== Regression guard (the 2026-10-06 smoke-test incident) ===")
    git("checkout", "-q", "main", cwd=seed)
    write_data(seed / "data", 5, prices="2026-10-05")
    git("add", ".", cwd=seed)
    git("commit", "-qm", "live is at oct 5", cwd=seed)
    git("push", "-q", "origin", "main", cwd=seed)
    p, out = run("price-sync/9-1", version=6, prices="2026-10-02")
    check("older prices than the live site are refused", p.returncode != 0 and "prices_regress" in out, out)
    check("and nothing was pushed", "price-sync/9-1" not in remote_branches())
    p, out = run("price-sync/9-2", version=6, prices="2026-10-06")
    check("newer prices go through", p.returncode == 0 and "price-sync/9-2" in remote_branches(), out)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{checks - failures}/{checks} checks passed")
sys.exit(1 if failures else 0)
