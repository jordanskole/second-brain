#!/bin/bash
_guard="_ARGV0_RENAMED_$(basename "$0" .sh | tr '-' '_')"
[ -n "${!_guard:-}" ] || { export "$_guard=1"; exec -a "sb-$(basename "$0" .sh)" /bin/bash "$0" "$@"; }
set -euo pipefail

PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

REPO_DIR="/Users/jordan/code/second-brain"
DATA_DIR="${SECOND_BRAIN_DATA_DIR:-$HOME/second-brain-data}"
export SECOND_BRAIN_DATA_DIR="$DATA_DIR"
SOURCE_ROOT="$HOME/.codex/sessions"
STATE_DIR="$DATA_DIR/.state"
STATE_FILE="$STATE_DIR/last_codex_run_epoch"
LOCK_DIR="$STATE_DIR/run-codex.lock"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*"; }

mkdir -p "$DATA_DIR/sessions" "$STATE_DIR"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "Another run appears to be in progress ($LOCK_DIR exists). Exiting."
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

cd "$DATA_DIR"

VENV_PYTHON="$REPO_DIR/.venv/bin/python"

LAST_RUN_EPOCH=0
[[ -f "$STATE_FILE" ]] && LAST_RUN_EPOCH=$(cat "$STATE_FILE")

RUN_START_EPOCH=$(date +%s)
log "Starting codex archive run. Cutoff epoch=$LAST_RUN_EPOCH"

CANDIDATES=()
if [[ -d "$SOURCE_ROOT" ]]; then
  while IFS= read -r -d '' src_file; do
    file_epoch=$(stat -f %m "$src_file")
    if (( file_epoch > LAST_RUN_EPOCH )); then
      CANDIDATES+=("$src_file")
    fi
  done < <(find "$SOURCE_ROOT" -type f -name '*.jsonl' -print0)
fi

log "Found ${#CANDIDATES[@]} rollout file(s) newer than cutoff."

if [[ ${#CANDIDATES[@]} -gt 0 ]]; then
  if [[ -x "$VENV_PYTHON" ]]; then
    "$VENV_PYTHON" "$REPO_DIR/bin/import_codex_sessions.py" "${CANDIDATES[@]}"
  else
    log "WARNING: $VENV_PYTHON not found. Skipping codex import."
  fi
fi

git add "sessions/"

if git diff --cached --quiet; then
  log "No net changes to commit."
else
  COMMIT_MSG="Import codex sessions: ${#CANDIDATES[@]} file(s) checked - $(date '+%Y-%m-%d %H:%M %Z')"
  git commit --quiet -m "$COMMIT_MSG"
  log "Committed: $COMMIT_MSG"
fi

echo "$RUN_START_EPOCH" > "$STATE_FILE"
log "Run complete. State advanced to $RUN_START_EPOCH."

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
