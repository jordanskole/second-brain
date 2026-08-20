#!/bin/bash
_guard="_ARGV0_RENAMED_$(basename "$0" .sh | tr '-' '_')"
[ -n "${!_guard:-}" ] || { export "$_guard=1"; exec -a "sb-$(basename "$0" .sh)" /bin/bash "$0" "$@"; }
set -euo pipefail

PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

REPO_DIR="/Users/jordan/code/second-brain"
DATA_DIR="${SECOND_BRAIN_DATA_DIR:-$HOME/second-brain-data}"
export SECOND_BRAIN_DATA_DIR="$DATA_DIR"
SOURCE_ROOT="$HOME/.claude/projects"
DEST_ROOT="$DATA_DIR/sessions"
STATE_DIR="$DATA_DIR/.state"
STATE_FILE="$STATE_DIR/last_run_epoch"
LOCK_DIR="$STATE_DIR/run.lock"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*"; }

mkdir -p "$DEST_ROOT" "$STATE_DIR"

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
log "Starting archive run. Cutoff epoch=$LAST_RUN_EPOCH"

CHANGED_COUNT=0
CHANGED_PROJECTS=()

if [[ -d "$SOURCE_ROOT" ]]; then
  while IFS= read -r -d '' src_file; do
    file_epoch=$(stat -f %m "$src_file")
    if (( file_epoch > LAST_RUN_EPOCH )); then
      rel_path="${src_file#"$SOURCE_ROOT"/}"
      dest_file="$DEST_ROOT/$rel_path"
      mkdir -p "$(dirname "$dest_file")"
      cp -p "$src_file" "$dest_file"
      CHANGED_COUNT=$((CHANGED_COUNT + 1))
      CHANGED_PROJECTS+=("${rel_path%%/*}")
    fi
  done < <(find "$SOURCE_ROOT" -mindepth 2 -maxdepth 2 -type f -name '*.jsonl' -print0)
fi

log "Copied $CHANGED_COUNT file(s) newer than cutoff."

if [[ -x "$VENV_PYTHON" ]]; then
  log "Importing plan files..."
  if ! "$VENV_PYTHON" "$REPO_DIR/bin/import_plans.py"; then
    log "WARNING: import_plans.py failed. Continuing without plan updates."
  fi
else
  log "WARNING: $VENV_PYTHON not found. Skipping plan import."
fi

git add "sessions/"

if git diff --cached --quiet; then
  log "No net changes to commit."
else
  UNIQUE_PROJECTS=0
  if [[ ${#CHANGED_PROJECTS[@]} -gt 0 ]]; then
    UNIQUE_PROJECTS=$(printf '%s\n' "${CHANGED_PROJECTS[@]}" | sort -u | wc -l | tr -d ' ')
  fi
  COMMIT_MSG="Archive sessions: $CHANGED_COUNT file(s) across $UNIQUE_PROJECTS project(s) - $(date '+%Y-%m-%d %H:%M %Z')"
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
    log "WARNING: build_index.py failed (exit $?). Search index may be stale; archive itself is unaffected."
  fi
else
  log "WARNING: $VENV_PYTHON not found. Skipping search index update."
fi

log "Backing up to apps.jarvis T7..."
if rsync -a --delete "$DATA_DIR/" jordan@apps.jarvis:/mnt/t7/backups/second-brain-data/; then
  log "Backup to apps.jarvis complete."
else
  log "WARNING: backup to apps.jarvis failed (exit $?). Local archive is unaffected."
fi
