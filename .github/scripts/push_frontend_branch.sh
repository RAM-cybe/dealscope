#!/usr/bin/env bash
# Copy live JSON into a dealscope-frontend checkout and push a NEW branch.
# Credentials must already be configured on that checkout (actions/checkout
# with a GitHub App token extraheader, or an SSH deploy key). Never put a
# token in a remote URL. Never force-push.
set -euo pipefail

usage() {
  echo "Usage: push_frontend_branch.sh <frontend_dir> <branch> <commit_message>" >&2
  exit 2
}

[[ $# -ge 3 ]] || usage

FRONTEND_DIR=$1
BRANCH=$2
COMMIT_MSG=$3
SRC_DIR="${GITHUB_WORKSPACE:-.}/data/frontend"
FILES=(companies.json narratives.json deals.json filter-bands.json sector-bands.json dataset-meta.json)

if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
  echo "::error::Refusing to push directly to $BRANCH. Use a price-sync/* or promote/* branch."
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/.git" ]]; then
  echo "::error::Frontend checkout missing at $FRONTEND_DIR"
  exit 1
fi

for f in "${FILES[@]}"; do
  if [[ ! -f "$SRC_DIR/$f" ]]; then
    echo "::error::Missing source file $SRC_DIR/$f"
    exit 1
  fi
done

git -C "$FRONTEND_DIR" checkout -B "$BRANCH"

# Release guard: the site must never move backwards. Compare what we are about
# to publish with what the frontend serves right now, BEFORE overwriting it.
# (A 20-company smoke test once published an older committed export over fresh
# data and rolled live prices back three days.)
CURRENT_META=""
if [[ -f "$FRONTEND_DIR/data/dataset-meta.json" ]]; then
  CURRENT_META=$(mktemp)
  cp "$FRONTEND_DIR/data/dataset-meta.json" "$CURRENT_META"
fi
REPO_ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if ! (cd "$REPO_ROOT_DIR" && python3 -m src.data.release_guard "$SRC_DIR/dataset-meta.json" "${CURRENT_META:-/nonexistent}"); then
  echo "::error::Release guard blocked this publish; the live site keeps its current data."
  exit 1
fi

for f in "${FILES[@]}"; do
  cp "$SRC_DIR/$f" "$FRONTEND_DIR/data/$f"
done

git -C "$FRONTEND_DIR" add "${FILES[@]/#/data/}"

if git -C "$FRONTEND_DIR" diff --cached --quiet; then
  echo "No frontend data change."
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "changed=false" >> "$GITHUB_OUTPUT"
  fi
  exit 0
fi

git -C "$FRONTEND_DIR" config user.name "github-actions[bot]"
git -C "$FRONTEND_DIR" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git -C "$FRONTEND_DIR" commit -m "$COMMIT_MSG"

# Idempotent push. A workflow re-run, or a retried step, can find BRANCH already
# on the remote from an earlier attempt. Never force-push: if the remote branch
# carries exactly the data we are about to publish, treat it as already pushed;
# if it carries different data, fail loudly rather than overwrite it.
if git -C "$FRONTEND_DIR" ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  git -C "$FRONTEND_DIR" fetch --quiet origin "$BRANCH"
  if git -C "$FRONTEND_DIR" diff --quiet FETCH_HEAD HEAD -- data; then
    echo "Remote branch $BRANCH already has identical data -- nothing to push."
  else
    echo "::error::Remote branch $BRANCH already exists with different data; refusing to overwrite."
    exit 1
  fi
else
  # Transient network/auth blips: retry a few times (still no force).
  for attempt in 1 2 3; do
    if git -C "$FRONTEND_DIR" push -u origin "HEAD:refs/heads/$BRANCH"; then
      break
    fi
    if [[ "$attempt" -eq 3 ]]; then
      echo "::error::Failed to push $BRANCH after 3 attempts"
      exit 1
    fi
    echo "Push failed (attempt $attempt/3); retrying in $((attempt * 10))s"
    sleep $((attempt * 10))
  done
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "changed=true" >> "$GITHUB_OUTPUT"
  echo "branch=$BRANCH" >> "$GITHUB_OUTPUT"
fi
echo "Pushed frontend branch $BRANCH"
