#!/bin/bash
# One-time setup: scaffolds ~/code/second-brain, installs the launchd jobs
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
LABEL_PREFIX="com.$(whoami).second-brain"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "Repo dir:     $REPO_DIR"
echo "Label prefix: $LABEL_PREFIX"

mkdir -p "$REPO_DIR"/{sessions,logs,.state,inbox,inbox-openai}
chmod +x "$REPO_DIR"/bin/*.sh

if [[ ! -d "$REPO_DIR/.git" ]]; then
  git -C "$REPO_DIR" init
  echo "Initialized a fresh git repo at $REPO_DIR."
  echo "Set your identity if needed: git config user.name / user.email"
fi

mkdir -p "$LAUNCH_AGENTS_DIR"

install_job() {
  local name="$1"
  local template="$REPO_DIR/launchd/$name.plist.template"
  local dest="$LAUNCH_AGENTS_DIR/$LABEL_PREFIX.$name.plist"

  sed -e "s|__REPO_DIR__|$REPO_DIR|g" -e "s|__LABEL_PREFIX__|$LABEL_PREFIX|g" \
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
  tail -f "$REPO_DIR/logs/archive-sessions.out.log"
  git -C "$REPO_DIR" log --oneline
EOF
