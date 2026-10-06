"""Watchdog decisions: detect drift and repair it without a human.

Run: python3 tests/test_watchdog.py
"""

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("watchdog", REPO_ROOT / ".github" / "scripts" / "watchdog.py")
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)

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


NOW = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)  # Wednesday 15:00 UTC


def run(rid, hours_ago, conclusion="success", status="completed", attempt=1, event="schedule"):
    return {"id": rid, "event": event, "status": status, "conclusion": conclusion,
            "run_attempt": attempt, "created_at": (NOW - timedelta(hours=hours_ago)).isoformat()}


def healthy():
    return {
        "meta": {"prices_as_of": "2026-10-06", "fundamentals_as_of": "2026-10-01"},
        "runs": {"daily": [run(1, 4)], "quarterly": [run(2, 24 * 6)]},
        "workflows": {"daily_price_refresh.yml": "active", "quarterly_refresh.yml": "active", "watchdog.yml": "active"},
        "branches": [],
    }


def kinds(result, kind):
    return [a for a in result["actions"] if a["type"] == kind]


print("=== Healthy system: nothing to do ===")
r = watchdog.assess(healthy(), NOW)
check("no actions", r["actions"] == [], str(r["actions"]))
check("no problems", r["problems"] == [], str(r["problems"]))

print("=== Prices ===")
s = healthy(); s["meta"]["prices_as_of"] = "2026-10-01"; s["runs"]["daily"] = [run(1, 40)]
r = watchdog.assess(s, NOW)
check("prices 4 weekdays behind -> dispatch daily", any(a.get("workflow") == "daily_price_refresh.yml" for a in kinds(r, "dispatch")), str(r))
s["runs"]["daily"] = [run(1, 1, status="in_progress", conclusion=None)]
r = watchdog.assess(s, NOW)
check("already running -> no second dispatch", kinds(r, "dispatch") == [], str(r))
s["runs"]["daily"] = [run(1, 2, conclusion="failure", attempt=2)]
r = watchdog.assess(s, NOW)
check("recent attempt inside cooldown -> no dispatch loop", kinds(r, "dispatch") == [], str(r))
s = healthy(); s["meta"]["prices_as_of"] = "2026-10-05"
r = watchdog.assess(s, NOW)
check("one weekday behind is normal (market holiday / run pending)", kinds(r, "dispatch") == [], str(r))
weekend = datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)  # Saturday
s = healthy(); s["meta"]["prices_as_of"] = "2026-10-09"
check("Saturday with Friday prices is healthy", watchdog.assess(s, weekend)["actions"] == [])
early = datetime(2026, 10, 7, 6, 0, tzinfo=timezone.utc)  # before the day's run
s = healthy(); s["meta"]["prices_as_of"] = "2026-10-06"
check("before today's run, yesterday's prices are fresh", watchdog.assess(s, early)["problems"] == [])

print("=== Fundamentals ===")
s = healthy(); s["meta"]["fundamentals_as_of"] = "2026-06-20"; s["runs"]["quarterly"] = [run(2, 24 * 20)]
r = watchdog.assess(s, NOW)
check("fundamentals 109 days old -> dispatch quarterly", any(a.get("workflow") == "quarterly_refresh.yml" for a in kinds(r, "dispatch")), str(r))
s["runs"]["quarterly"] = [run(2, 24, conclusion="failure")]
r = watchdog.assess(s, NOW)
check("quarterly tried yesterday -> wait, but flag it", kinds(r, "dispatch") == [] and r["problems"], str(r))
s = healthy(); s["meta"]["fundamentals_as_of"] = "2026-07-11"
r = watchdog.assess(s, NOW)
check("88 days old is still fine", kinds(r, "dispatch") == [] and r["problems"] == [], str(r))

print("=== Failed runs are retried once ===")
s = healthy(); s["runs"]["daily"] = [run(7, 3, conclusion="failure", attempt=1)]
r = watchdog.assess(s, NOW)
check("first failure -> rerun", [a["run_id"] for a in kinds(r, "rerun")] == [7], str(r))
s["runs"]["daily"] = [run(7, 3, conclusion="failure", attempt=2)]
r = watchdog.assess(s, NOW)
check("failed twice -> no retry loop, reported", kinds(r, "rerun") == [] and r["problems"], str(r))
s["runs"]["daily"] = [run(7, 3, conclusion="failure", attempt=1), run(6, 27)]
check("a failed run that a newer success follows is ignored",
      watchdog.assess({**s, "runs": {"daily": [run(9, 1), run(7, 3, conclusion="failure")], "quarterly": []}}, NOW)["actions"] == [])

print("=== Disabled workflows are re-enabled ===")
s = healthy(); s["workflows"]["daily_price_refresh.yml"] = "disabled_inactivity"
r = watchdog.assess(s, NOW)
check("inactivity-disabled workflow -> enable", [a["workflow"] for a in kinds(r, "enable")] == ["daily_price_refresh.yml"], str(r))
s["workflows"]["daily_price_refresh.yml"] = "disabled_manually"
r = watchdog.assess(s, NOW)
check("manually disabled is respected but reported", kinds(r, "enable") == [] and r["problems"], str(r))

print("=== Stuck frontend branches ===")
s = healthy(); s["branches"] = [{"name": "price-sync/55", "age_hours": 1.0}]
check("fresh branch is normal", watchdog.assess(s, NOW)["problems"] == [])
s["branches"] = [{"name": "price-sync/55", "age_hours": 9.0}]
r = watchdog.assess(s, NOW)
check("branch stuck for 9h is reported", any("price-sync/55" in p for p in r["problems"]), str(r))

print("=== Robustness ===")
check("missing meta does not crash", "problems" in watchdog.assess({**healthy(), "meta": None}, NOW))
check("empty run history does not crash", "actions" in watchdog.assess({**healthy(), "runs": {"daily": [], "quarterly": []}}, NOW))
check("garbage dates do not crash", "problems" in watchdog.assess({**healthy(), "meta": {"prices_as_of": "soon", "fundamentals_as_of": 5}}, NOW))

print(f"\n{checks - failures}/{checks} checks passed")
sys.exit(1 if failures else 0)
