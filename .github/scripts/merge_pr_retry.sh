#!/usr/bin/env bash
# Squash-merge a pull request, retrying briefly for GitHub's "just opened,
# not mergeable yet" race. Real merge failures still fail the job.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: merge_pr_retry.sh <pr-number-or-branch>" >&2
  exit 2
fi

TARGET=$1
ATTEMPTS=${2:-8}

for i in $(seq 1 "$ATTEMPTS"); do
  if gh pr merge "$TARGET" --squash --delete-branch; then
    echo "Merged $TARGET"
    exit 0
  fi
  if [[ "$i" -eq "$ATTEMPTS" ]]; then
    echo "::error::Could not merge $TARGET after ${ATTEMPTS} attempts"
    exit 1
  fi
  echo "Merge not ready (attempt $i/${ATTEMPTS}); waiting 5s"
  sleep 5
done
