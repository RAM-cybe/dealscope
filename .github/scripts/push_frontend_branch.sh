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
git -C "$FRONTEND_DIR" push -u origin "HEAD:refs/heads/$BRANCH"

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "changed=true" >> "$GITHUB_OUTPUT"
  echo "branch=$BRANCH" >> "$GITHUB_OUTPUT"
fi
echo "Pushed frontend branch $BRANCH"
