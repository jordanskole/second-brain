#!/bin/bash
set -euo pipefail

PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

_guard="_ARGV0_RENAMED_$(basename "$0" .sh | tr -c '[:alnum:]_' '_')"
[ -n "${!_guard:-}" ] || { export "$_guard=1"; exec -a "sb-$(basename "$0" .sh)" /bin/bash "$0" "$@"; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${SECOND_BRAIN_DATA_DIR:-$HOME/second-brain-data}"
export SECOND_BRAIN_DATA_DIR="$DATA_DIR"
INBOX_DIR="$DATA_DIR/inbox"
PROCESSED_DIR="$INBOX_DIR/processed"
STATE_DIR="$DATA_DIR/.state"
LOCK_DIR="$STATE_DIR/watch-inbox.lock"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*"; }

mkdir -p "$INBOX_DIR" "$PROCESSED_DIR" "$STATE_DIR"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "Another run appears to be in progress ($LOCK_DIR exists). Exiting."
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

cd "$REPO_DIR"

shopt -s nullglob
EXPORTS=("$INBOX_DIR"/*.zip)
shopt -u nullglob

if [[ ${#EXPORTS[@]} -eq 0 ]]; then
  log "No export files in $INBOX_DIR. Nothing to do."
  exit 0
fi

for export_file in "${EXPORTS[@]}"; do
  log "Found export: $export_file"
  if "$REPO_DIR/bin/import-claude-ai-export.sh" "$export_file"; then
    dest="$PROCESSED_DIR/$(date '+%Y%m%d-%H%M%S')-$(basename "$export_file")"
    mv "$export_file" "$dest"
    log "Processed and moved to $dest"
  else
    log "ERROR: import failed for $export_file, leaving it in place for retry."
  fi
done
