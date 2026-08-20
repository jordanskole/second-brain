#!/bin/bash
# One-time setup: scaffolds the code + data roots, installs the launchd jobs
# for nightly archival and inbox watching. Safe to re-run (idempotent).
set -euo pipefail

if ! xcode-select -p >/dev/null 2>&1; then
  echo "Xcode Command Line Tools aren't installed, so git isn't available yet." >&2
  echo "Run 'xcode-select --install', click through the prompt, then re-run this script." >&2
  echo "(Just running 'git' would trigger the same install dialog, but as a GUI popup" >&2
  echo "this script can't wait on -- easy to miss and think the script hung.)" >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SECOND_BRAIN_DATA_DIR:-$HOME/second-brain-data}"
LABEL_PREFIX="com.$(whoami).second-brain"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "Code dir:     $REPO_DIR"
echo "Data dir:     $DATA_DIR (override by exporting SECOND_BRAIN_DATA_DIR before running this script)"
echo "Label prefix: $LABEL_PREFIX"

mkdir -p "$DATA_DIR"/{sessions,logs,.state,inbox,inbox-openai}
chmod +x "$REPO_DIR"/bin/*.sh

if [[ ! -d "$DATA_DIR/.git" ]]; then
  git -C "$DATA_DIR" init
  echo "Initialized a fresh git repo at $DATA_DIR (no remote -- keep it that way)."
  echo "Set your identity if needed: git -C \"$DATA_DIR\" config user.name / user.email"
fi

mkdir -p "$LAUNCH_AGENTS_DIR"

install_job() {
  local name="$1"
  local template="$REPO_DIR/launchd/$name.plist.template"
  local dest="$LAUNCH_AGENTS_DIR/$LABEL_PREFIX.$name.plist"

  sed -e "s|__REPO_DIR__|$REPO_DIR|g" -e "s|__DATA_DIR__|$DATA_DIR|g" -e "s|__LABEL_PREFIX__|$LABEL_PREFIX|g" \
    "$template" > "$dest"
  chmod 644 "$dest"

  launchctl bootstrap "gui/$(id -u)" "$dest" 2>/dev/null || true
  launchctl enable "gui/$(id -u)/$LABEL_PREFIX.$name"
  echo "Installed $LABEL_PREFIX.$name -> $dest"
}

install_job archive-sessions
install_job watch-claude-ai-inbox
install_job watch-openai-inbox
install_job archive-codex-sessions

launchctl kickstart -k "gui/$(id -u)/$LABEL_PREFIX.archive-sessions"

cat <<EOF

Done. Useful commands:
  launchctl print gui/$(id -u)/$LABEL_PREFIX.archive-sessions
  tail -f "$DATA_DIR/logs/archive-sessions.out.log"
  git -C "$DATA_DIR" log --oneline
EOF
