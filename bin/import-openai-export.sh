#!/bin/bash
set -euo pipefail

PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

REPO_DIR="/Users/jordan/code/second-brain"
DATA_DIR="${SECOND_BRAIN_DATA_DIR:-$HOME/second-brain-data}"
export SECOND_BRAIN_DATA_DIR="$DATA_DIR"
VENV_PYTHON="$REPO_DIR/.venv/bin/python"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*"; }

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <path-to-openai-export.zip-or-dir>" >&2
  exit 1
fi

EXPORT_PATH="$1"

cd "$DATA_DIR"

log "Converting openai export: $EXPORT_PATH"
"$VENV_PYTHON" "$REPO_DIR/bin/import_openai_export.py" "$EXPORT_PATH"

git add "sessions/"

if git diff --cached --quiet; then
  log "No net changes to commit."
else
  COMMIT_MSG="Import openai export - $(date '+%Y-%m-%d %H:%M %Z')"
  git commit --quiet -m "$COMMIT_MSG"
  log "Committed: $COMMIT_MSG"
fi

if [[ -x "$VENV_PYTHON" ]]; then
  log "Updating semantic search index..."
  if "$VENV_PYTHON" "$REPO_DIR/bin/build_index.py"; then
    log "Search index updated."
  else
    log "WARNING: build_index.py failed. Search index may be stale."
  fi
else
  log "WARNING: $VENV_PYTHON not found. Skipping search index update."
fi
