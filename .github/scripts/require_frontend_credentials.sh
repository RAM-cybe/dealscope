#!/usr/bin/env bash
# Fail the job if neither GitHub App nor deploy-key credentials are present.
# Empty GitHub secrets expand to empty strings; that is not a leak.
set -euo pipefail

APP_ID="${DEALSCOPE_APP_ID:-}"
APP_KEY="${DEALSCOPE_APP_PRIVATE_KEY:-}"
DEPLOY_KEY="${FRONTEND_DEPLOY_KEY:-}"

if [[ -n "$APP_ID" && -n "$APP_KEY" ]]; then
  echo "Frontend git auth: GitHub App (short-lived installation token)"
  exit 0
fi

if [[ -n "$DEPLOY_KEY" ]]; then
  echo "Frontend git auth: repo-scoped SSH deploy key"
  exit 0
fi

echo "::error::No frontend credentials. Set DEALSCOPE_APP_ID + DEALSCOPE_APP_PRIVATE_KEY (preferred GitHub App) or FRONTEND_DEPLOY_KEY (write deploy key on dealscope-frontend). Do not use FRONTEND_REPO_TOKEN."
exit 1
