#!/usr/bin/env bash
# Squash-merge a pull request onto main as Ram VP (not github-actions[bot]).
# Retries briefly for GitHub's "just opened, not mergeable yet" race.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: merge_pr_retry.sh <pr-number-or-branch>" >&2
  exit 2
fi

TARGET=$1
ATTEMPTS=${2:-8}

git config user.name "Ram VP"
git config user.email "225523561+ram-vp@users.noreply.github.com"

# Resolve PR number + head ref + title
PR_JSON=$(gh pr view "$TARGET" --json number,title,headRefName,state)
PR=$(printf '%s' "$PR_JSON" | jq -r .number)
TITLE=$(printf '%s' "$PR_JSON" | jq -r .title)
HEAD=$(printf '%s' "$PR_JSON" | jq -r .headRefName)
STATE=$(printf '%s' "$PR_JSON" | jq -r .state)

if [[ "$STATE" == "MERGED" ]]; then
  echo "PR #$PR already merged"
  exit 0
fi

for i in $(seq 1 "$ATTEMPTS"); do
  MERGEABLE=$(gh pr view "$PR" --json mergeable --jq .mergeable || echo "UNKNOWN")
  if [[ "$MERGEABLE" == "MERGEABLE" ]]; then
    git fetch origin main --quiet
    git checkout -q -B "__squash_merge_main" origin/main
    git fetch origin "$HEAD" --quiet
    git merge --squash "origin/$HEAD"
    # If squash produced nothing, treat as success (already up to date)
    if git diff --cached --quiet; then
      echo "Nothing to squash for PR #$PR"
      git checkout -q main
      git branch -q -D "__squash_merge_main" || true
      gh pr close "$PR" --comment "Already reflected on main; closing." || true
      git push origin --delete "$HEAD" || true
      exit 0
    fi
    git commit -m "$TITLE"
    git push origin "HEAD:main"
    # Close PR as merged-equivalent and delete head branch
    gh pr close "$PR" --comment "Squash-merged onto main as Ram VP (commit $(git rev-parse --short HEAD))." || true
    git push origin --delete "$HEAD" || true
    git checkout -q main
    git branch -q -D "__squash_merge_main" || true
    echo "Merged #$PR onto main as Ram VP"
    exit 0
  fi
  if [[ "$i" -eq "$ATTEMPTS" ]]; then
    echo "::error::Could not merge $TARGET after ${ATTEMPTS} attempts (mergeable=$MERGEABLE)"
    exit 1
  fi
  echo "Merge not ready (attempt $i/${ATTEMPTS}, mergeable=$MERGEABLE); waiting 5s"
  sleep 5
done
