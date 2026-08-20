#!/bin/bash
set -euo pipefail

PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

_guard="_ARGV0_RENAMED_$(basename "$0" .sh | tr -c '[:alnum:]_' '_')"
[ -n "${!_guard:-}" ] || { export "$_guard=1"; exec -a "sb-$(basename "$0" .sh)" /bin/bash "$0" "$@"; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${SECOND_BRAIN_DATA_DIR:-$HOME/second-brain-data}"
export SECOND_BRAIN_DATA_DIR="$DATA_DIR"
VENV_PYTHON="$REPO_DIR/.venv/bin/python"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*"; }

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <path-to-claude-ai-export.zip-or-dir>" >&2
  exit 1
fi

EXPORT_PATH="$1"

cd "$DATA_DIR"

log "Converting claude.ai export: $EXPORT_PATH"
"$VENV_PYTHON" "$REPO_DIR/bin/import_claude_ai_export.py" "$EXPORT_PATH"

git add "sessions/"

if git diff --cached --quiet; then
  log "No net changes to commit."
else
  COMMIT_MSG="Import claude.ai export - $(date '+%Y-%m-%d %H:%M %Z')"
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
