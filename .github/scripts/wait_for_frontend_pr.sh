#!/usr/bin/env bash
# Wait until a dealscope-frontend PR for BRANCH reaches the expected state.
# Used so a backend success ping does not fire before the frontend apply
# job has actually opened (promote) or merged (daily) the matching PR.
# Missing PRs are retried until timeout; the job then fails.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: wait_for_frontend_pr.sh <branch> <OPEN|MERGED> [attempts]" >&2
  exit 2
fi

BRANCH=$1
EXPECT=$2
ATTEMPTS=${3:-30}
OWNER="${GITHUB_REPOSITORY_OWNER:-${GITHUB_REPOSITORY%%/*}}"
REPO=${FRONTEND_REPO:-${OWNER}/dealscope-frontend}

if [[ "$EXPECT" != "OPEN" && "$EXPECT" != "MERGED" ]]; then
  echo "::error::Expected state must be OPEN or MERGED, got $EXPECT"
  exit 2
fi

CLOSED_RETRIES=0

for i in $(seq 1 "$ATTEMPTS"); do
  STATE=""
  if STATE=$(gh pr list --repo "$REPO" --head "$BRANCH" --state all --json state --jq '.[0].state // empty'); then
    if [[ -n "$STATE" ]]; then
      echo "Frontend PR $BRANCH is $STATE (attempt $i/${ATTEMPTS})"
      if [[ "$STATE" == "$EXPECT" ]]; then
        exit 0
      fi
      if [[ "$STATE" == "OPEN" ]]; then
        CLOSED_RETRIES=0
      fi
      if [[ "$EXPECT" == "MERGED" && "$STATE" == "CLOSED" ]]; then
        COMMENT=$(gh pr list --repo "$REPO" --head "$BRANCH" --state all --json state,comments --jq '[ .[0].comments[]?.body? | select(type == "string" and (startswith("Squash-merged onto main as Ram VP") or startswith("Already on main."))) ] | first // empty' 2>/dev/null || true)
        if [[ -n "$COMMENT" ]]; then
          echo "Frontend PR $BRANCH was merged: ${COMMENT%%$'\n'*}"
          exit 0
        fi
        CLOSED_RETRIES=$((CLOSED_RETRIES + 1))
        if [[ "$CLOSED_RETRIES" -le 3 ]]; then
          echo "Frontend PR $BRANCH is CLOSED without merge comment yet (retry $CLOSED_RETRIES/3)"
        else
          echo "::error::Frontend PR for $BRANCH was closed without merging"
          exit 1
        fi
      fi
    else
      echo "Frontend PR $BRANCH not visible yet (attempt $i/${ATTEMPTS})"
    fi
  else
    echo "gh pr list failed looking for $BRANCH (attempt $i/${ATTEMPTS})"
  fi
  if [[ "$i" -eq "$ATTEMPTS" ]]; then
    echo "::error::Timed out waiting for frontend PR $BRANCH to become $EXPECT"
    exit 1
  fi
  sleep 10
done
