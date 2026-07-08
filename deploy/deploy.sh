#!/usr/bin/env bash
#
# Deploy the bot to prod.
#
# Prod is NOT a git checkout — it is a plain directory that we sync into over SSH.
# This script rsyncs the code, reinstalls deps and restarts the systemd service.
#
# Never touched on prod (kept only there, gitignored): .env, service_account.json, venv/.
#
# Usage:
#   deploy/deploy.sh            # sync + reinstall deps + restart
#   deploy/deploy.sh --dry-run  # show what rsync would change, do nothing
#   deploy/deploy.sh --no-deps  # skip pip install (code-only change)
#
set -euo pipefail

HOST="whalegraph-prod"          # ssh alias (root@...)
REMOTE_DIR="/opt/expense-bot"   # NOTE: not /opt/money-tracker-bot (repo docs are stale)
SERVICE="expense-bot"

# Only these paths are pushed. Everything else on prod (.env, service_account.json,
# venv) is left alone. --delete cleans stale files *inside* these dirs only.
PATHS=(bot tracker tests requirements.txt)

# Junk we never want on prod.
EXCLUDES=(--exclude __pycache__ --exclude '*.pyc' --exclude '*.xlsx'
          --exclude .env --exclude service_account.json --exclude venv --exclude .git)

DRY_RUN=""
INSTALL_DEPS=1
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN="--dry-run" ;;
    --no-deps) INSTALL_DEPS=0 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."   # repo root

echo ">> target: $HOST:$REMOTE_DIR  (service: $SERVICE)"

# Warn on uncommitted changes so we know exactly what is going out.
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  echo ">> WARNING: working tree has uncommitted changes — deploying them as-is."
fi

echo ">> syncing: ${PATHS[*]}"
# -r recurse, -l links, -p perms, -t times, -z compress, -i itemize, -v verbose.
# No -o/-g on purpose: files land owned by root on prod, not the local uid.
rsync -rlptziv --delete $DRY_RUN "${EXCLUDES[@]}" \
  "${PATHS[@]}" "$HOST:$REMOTE_DIR/"

if [ -n "$DRY_RUN" ]; then
  echo ">> dry-run done. Nothing changed on prod."
  exit 0
fi

if [ "$INSTALL_DEPS" -eq 1 ]; then
  echo ">> installing deps in prod venv"
  ssh "$HOST" "cd $REMOTE_DIR && ./venv/bin/pip install -q -r requirements.txt"
else
  echo ">> skipping deps (--no-deps)"
fi

echo ">> restarting $SERVICE"
ssh "$HOST" "systemctl restart $SERVICE && sleep 1 && systemctl --no-pager --lines=0 status $SERVICE"

echo ">> recent logs (Ctrl+C to stop tailing):"
ssh "$HOST" "journalctl -u $SERVICE -n 15 --no-pager"

echo ">> done."
