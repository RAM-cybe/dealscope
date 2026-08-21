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
REPO=${FRONTEND_REPO:-RAM-cybe/dealscope-frontend}

if [[ "$EXPECT" != "OPEN" && "$EXPECT" != "MERGED" ]]; then
  echo "::error::Expected state must be OPEN or MERGED, got $EXPECT"
  exit 2
fi

for i in $(seq 1 "$ATTEMPTS"); do
  STATE=""
  if STATE=$(gh pr list --repo "$REPO" --head "$BRANCH" --state all --json state --jq '.[0].state // empty'); then
    if [[ -n "$STATE" ]]; then
      echo "Frontend PR $BRANCH is $STATE (attempt $i/${ATTEMPTS})"
      if [[ "$STATE" == "$EXPECT" ]]; then
        exit 0
      fi
      if [[ "$EXPECT" == "MERGED" && "$STATE" == "CLOSED" ]]; then
        echo "::error::Frontend PR for $BRANCH was closed without merging"
        exit 1
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
