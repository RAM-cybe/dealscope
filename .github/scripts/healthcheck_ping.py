"""Ping monitoring after a refresh workflow.

Always writes a GitHub Actions job summary. If HEALTHCHECKS_URL is set,
pings that URL (success) or URL/fail (failure) and does not swallow errors.
On failure, opens or updates a GitHub issue so a red run is visible even
without healthchecks.io.

Usage:
    python .github/scripts/healthcheck_ping.py success
    python .github/scripts/healthcheck_ping.py failure
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ISSUE_TITLE = {
    "daily": "[DealScope] Daily price refresh failed",
    "quarterly": "[DealScope] Quarterly fundamentals refresh failed",
    "promote": "[DealScope] Snapshot promotion failed",
}
def request(method, url, token, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def write_summary(action, kind, ping_url, extra):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"## Refresh monitor — {kind} — **{action.upper()}**",
        "",
        f"- Time: {now}",
        f"- Healthchecks ping: {'configured (' + ping_url + ')' if ping_url else 'NOT CONFIGURED'}",
        extra,
        "",
    ]
    with open(path, "a") as f:
        f.write("\n".join(lines))


def ping_healthchecks(url, action):
    target = url.rstrip("/")
    if action == "failure":
        target = f"{target}/fail"
    req = urllib.request.Request(target, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"healthchecks ping HTTP {resp.status}")


def find_open_issue(repo, token, title):
    q = urllib.parse.urlencode({"state": "open", "per_page": 50})
    url = f"https://api.github.com/repos/{repo}/issues?{q}"
    issues = request("GET", url, token)
    for issue in issues:
        if issue.get("title") == title and "pull_request" not in issue:
            return issue
    return None


def ensure_failure_issue(repo, token, title, run_url):
    body = (
        "The scheduled refresh failed. This issue is opened automatically so "
        "the failure is visible — it is not a data bug in the live site "
        "(failed runs do not publish).\n\n"
        f"Failed run: {run_url or '(unknown)'}\n"
    )
    existing = find_open_issue(repo, token, title)
    if existing:
        request(
            "POST",
            f"https://api.github.com/repos/{repo}/issues/{existing['number']}/comments",
            token,
            {"body": f"Failed again: {run_url or '(unknown)'}"},
        )
        return existing["html_url"]
    created = request(
        "POST",
        f"https://api.github.com/repos/{repo}/issues",
        token,
        {"title": title, "body": body},
    )
    return created.get("html_url", "")


def close_failure_issue(repo, token, title):
    existing = find_open_issue(repo, token, title)
    if not existing:
        return
    request(
        "POST",
        f"https://api.github.com/repos/{repo}/issues/{existing['number']}/comments",
        token,
        {"body": "Refresh succeeded. Closing this monitor issue."},
    )
    request(
        "PATCH",
        f"https://api.github.com/repos/{repo}/issues/{existing['number']}",
        token,
        {"state": "closed"},
    )


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {"success", "failure"}:
        print("Usage: healthcheck_ping.py success|failure")
        sys.exit(2)

    action = sys.argv[1]
    kind = os.environ.get("HEALTHCHECK_KIND", "daily")
    ping_url = (os.environ.get("HEALTHCHECKS_URL") or "").strip()
    token = os.environ.get("GITHUB_TOKEN") or ""
    repo = os.environ.get("GITHUB_REPOSITORY") or ""
    run_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if repo and run_id:
        run_url = f"{run_url}/{repo}/actions/runs/{run_id}"

    extra = ""
    errors = []

    if ping_url:
        try:
            ping_healthchecks(ping_url, action)
            extra = f"- Pinged healthchecks.io: `{action}`"
        except Exception as exc:
            errors.append(f"healthchecks ping failed: {exc}")
    else:
        extra = (
            "- HEALTHCHECKS_URL secret is not set. Add a free healthchecks.io "
            "check URL as HEALTHCHECKS_DAILY_URL / HEALTHCHECKS_QUARTERLY_URL."
        )
        if action == "success":
            print(f"::warning::{extra}")
        else:
            print(f"::error::{extra}")

    title = ISSUE_TITLE.get(kind, ISSUE_TITLE["daily"])
    if token and repo:
        try:
            if action == "failure":
                issue_url = ensure_failure_issue(repo, token, title, run_url)
                extra += f"\n- Tracking issue: {issue_url}"
            else:
                close_failure_issue(repo, token, title)
        except Exception as exc:
            errors.append(f"GitHub issue update failed: {exc}")
    elif action == "failure":
        errors.append("GITHUB_TOKEN or GITHUB_REPOSITORY missing; cannot open a failure issue")

    write_summary(action, kind, ping_url, extra)

    if errors:
        for err in errors:
            print(f"::error::{err}")
        sys.exit(1)

    print(f"monitor {kind} {action}: ok")


if __name__ == "__main__":
    main()
