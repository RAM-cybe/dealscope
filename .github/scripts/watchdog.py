"""Pipeline watchdog: notice drift and repair it without a human.

assess() is a pure function (state in, actions + problems out) so every rule
is unit-tested. main() gathers the state with the `gh` CLI, executes the
actions, and keeps ONE tracking issue open while anything is wrong (closing
it when everything is healthy again).

Rules, in plain words:
  * Live prices more than one weekday behind -> run the daily refresh.
  * Fundamentals older than 95 days          -> run the quarterly refresh.
  * A scheduled run failed                    -> re-run it once (re-runs are
    safe: branch names include the attempt). Failed twice -> report only.
  * A workflow GitHub disabled for inactivity -> enable it again.
  * A data branch stuck on the frontend for hours -> report it.
Dispatches are rate-limited (6h daily, 72h quarterly) so it can never loop.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

BACKEND = os.environ.get("GITHUB_REPOSITORY", "RAM-cybe/dealscope")
FRONTEND = "RAM-cybe/dealscope-frontend"
SITE_URL = "https://dealscope-screener.vercel.app/"
WORKFLOWS = {"daily": "daily_price_refresh.yml", "quarterly": "quarterly_refresh.yml"}
ISSUE_TITLE = "[DealScope] Pipeline health"

PRICE_LAG_TRIGGER = 2            # weekdays behind the last completed weekday
FUNDAMENTALS_MAX_AGE_DAYS = 95   # site goes "stale" at 100
COOLDOWN_HOURS = {"daily": 6, "quarterly": 72}
BRANCH_STUCK_HOURS = 6
ACTIVE_STATES = {"queued", "in_progress", "waiting", "requested", "pending"}


def _parse_day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _parse_ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _previous_weekday(d):
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _weekdays_after(start, end):
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def assess(snapshot, now):
    actions, problems = [], []
    meta = snapshot.get("meta") or {}
    runs = snapshot.get("runs") or {}

    def newest_first(kind):
        items = [r for r in (runs.get(kind) or []) if _parse_ts(r.get("created_at"))]
        return sorted(items, key=lambda r: _parse_ts(r["created_at"]), reverse=True)

    def may_dispatch(kind):
        history = newest_first(kind)
        if any(r.get("status") in ACTIVE_STATES for r in history):
            return False
        cutoff = now - timedelta(hours=COOLDOWN_HOURS[kind])
        return not any(_parse_ts(r["created_at"]) > cutoff for r in history)

    rerun_kinds = set()

    # 1. A failed latest run is retried exactly once.
    for kind in ("daily", "quarterly"):
        history = newest_first(kind)
        latest = history[0] if history else None
        if latest and latest.get("status") == "completed" and latest.get("conclusion") == "failure":
            if int(latest.get("run_attempt") or 1) == 1:
                actions.append({"type": "rerun", "run_id": latest["id"], "workflow": WORKFLOWS[kind]})
                rerun_kinds.add(kind)
            else:
                problems.append(f"{WORKFLOWS[kind]} failed twice (run {latest['id']}); needs the fix in its tracking issue")

    # 2. Prices.
    prices = _parse_day(meta.get("prices_as_of"))
    if prices is None:
        problems.append("cannot read prices_as_of from the live dataset")
    else:
        lag = _weekdays_after(prices, _previous_weekday(now.date()))
        if lag >= PRICE_LAG_TRIGGER:
            problems.append(f"live prices are as of {prices} ({lag} weekdays behind)")
            if "daily" not in rerun_kinds and may_dispatch("daily"):
                actions.append({"type": "dispatch", "workflow": WORKFLOWS["daily"]})

    # 3. Fundamentals.
    funda = _parse_day(meta.get("fundamentals_as_of"))
    if funda is None:
        problems.append("cannot read fundamentals_as_of from the live dataset")
    else:
        age = (now.date() - funda).days
        if age > FUNDAMENTALS_MAX_AGE_DAYS:
            problems.append(f"fundamentals are {age} days old (as of {funda})")
            if "quarterly" not in rerun_kinds and may_dispatch("quarterly"):
                actions.append({"type": "dispatch", "workflow": WORKFLOWS["quarterly"]})

    # 4. Disabled workflows.
    for name, state in (snapshot.get("workflows") or {}).items():
        if state == "active":
            continue
        if state == "disabled_inactivity":
            actions.append({"type": "enable", "workflow": name})
            problems.append(f"{name} had been disabled for inactivity; re-enabling")
        else:
            problems.append(f"{name} is {state} (left alone: a person disabled it)")

    # 5. Stuck data branches on the frontend.
    for branch in snapshot.get("branches") or []:
        if float(branch.get("age_hours") or 0) > BRANCH_STUCK_HOURS:
            problems.append(f"frontend branch {branch['name']} has been waiting {branch['age_hours']:.0f}h to be applied")

    return {"actions": actions, "problems": problems}


# ---------------------------------------------------------------------------
# IO layer (not unit-tested; thin on purpose)
# ---------------------------------------------------------------------------

def gh(*args, check=True):
    p = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dealscope-watchdog"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


MONTHS = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def meta_from_site():
    html = fetch_text(f"{SITE_URL}?watchdog={int(time.time())}")
    m = re.search(r"Prices as of (\d{1,2}) ([A-Z][a-z]{2}) (\d{4})\. Fundamentals as of (\d{1,2}) ([A-Z][a-z]{2}) (\d{4})", html)
    if not m:
        return None
    d1, m1, y1, d2, m2, y2 = m.groups()
    return {"prices_as_of": f"{y1}-{MONTHS[m1]:02d}-{int(d1):02d}",
            "fundamentals_as_of": f"{y2}-{MONTHS[m2]:02d}-{int(d2):02d}"}


def gather(now):
    meta = None
    try:
        meta = meta_from_site()
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::could not read the live site: {exc}")
    runs = {}
    for kind, wf in WORKFLOWS.items():
        out = gh("run", "list", "--repo", BACKEND, "--workflow", wf, "--limit", "10",
                 "--json", "databaseId,event,status,conclusion,createdAt,attempt")
        runs[kind] = [{"id": r["databaseId"], "event": r["event"], "status": r["status"],
                       "conclusion": r["conclusion"], "created_at": r["createdAt"],
                       "run_attempt": r.get("attempt", 1)} for r in json.loads(out)]
    workflows = {}
    for w in json.loads(gh("workflow", "list", "--repo", BACKEND, "--all", "--json", "path,state")):
        workflows[os.path.basename(w["path"])] = w["state"]
    branches = []
    try:
        names = gh("api", f"repos/{FRONTEND}/branches?per_page=100", "--jq", ".[].name").split()
        for name in names:
            if name.startswith(("price-sync/", "promote/")):
                ts = gh("api", f"repos/{FRONTEND}/commits/{name}", "--jq", ".commit.committer.date").strip()
                age = (now - _parse_ts(ts)).total_seconds() / 3600
                branches.append({"name": name, "age_hours": age})
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::could not list frontend branches: {exc}")
    return {"meta": meta, "runs": runs, "workflows": workflows, "branches": branches}


def execute(action):
    t = action["type"]
    if t == "dispatch":
        gh("workflow", "run", action["workflow"], "--repo", BACKEND)
    elif t == "rerun":
        gh("run", "rerun", str(action["run_id"]), "--repo", BACKEND, "--failed")
    elif t == "enable":
        gh("workflow", "enable", action["workflow"], "--repo", BACKEND)
    print(f"executed: {action}")


def sync_issue(problems):
    out = gh("issue", "list", "--repo", BACKEND, "--state", "open", "--search", f'"{ISSUE_TITLE}" in:title',
             "--json", "number,title")
    existing = [i for i in json.loads(out) if i["title"] == ISSUE_TITLE]
    body = "\n".join(f"- {p}" for p in problems)
    run_url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{BACKEND}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    if problems and existing:
        gh("issue", "comment", str(existing[0]["number"]), "--repo", BACKEND, "--body", f"Still unhealthy ({run_url}):\n{body}")
    elif problems:
        gh("issue", "create", "--repo", BACKEND, "--title", ISSUE_TITLE,
           "--body", f"The watchdog found problems it could not fully repair on its own ({run_url}):\n{body}\n\n"
                     "It repairs what it can automatically and closes this issue when everything is healthy.")
    elif existing:
        gh("issue", "close", str(existing[0]["number"]), "--repo", BACKEND, "--comment", "Everything is healthy again.")


def main():
    now = datetime.now(timezone.utc)
    snapshot = gather(now)
    result = assess(snapshot, now)
    print(json.dumps({"meta": snapshot["meta"], **result}, indent=2, default=str))
    errors = []
    for action in result["actions"]:
        try:
            execute(action)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"could not execute {action}: {exc}")
    problems = result["problems"] + errors
    try:
        sync_issue(problems)
    except Exception as exc:  # noqa: BLE001
        print(f"::error::could not update the tracking issue: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
