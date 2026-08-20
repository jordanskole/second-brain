# Second-brain data/code split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate second-brain's code (public, GitHub-backed) from its data (private, never remoted), so the two "second-brain" directories stop colliding in name and in git history.

**Architecture:** Promote the already-public `~/code/second-brain-public` to become the canonical `~/code/second-brain` code root. Retire the *current* `~/code/second-brain` (whose git history already contains committed session transcripts) to `~/code/second-brain-legacy`, untouched, no remote, ever. Seed a brand-new data root at `~/second-brain-data` (local git, no remote) from the current live data. Every script that currently derives a data path from its own location switches to reading `SECOND_BRAIN_DATA_DIR` (env var, default `~/second-brain-data`) instead.

**Tech Stack:** bash, Python 3 (stdlib `pathlib`/`os` only for the path changes), launchd plists, git, rsync.

**Spec:** `docs/superpowers/specs/2026-08-20-data-code-split-design.md`

## Global Constraints

- Every data-path read in `bin/` must resolve through `SECOND_BRAIN_DATA_DIR`, defaulting to `$HOME/second-brain-data` — never hardcode `/Users/jordan/second-brain-data`.
- `REPO_DIR` (or `Path(__file__).resolve().parent.parent`) is kept only for genuinely code-relative needs (`.venv`, other `bin/*.py`) — never reused for a data path after this migration.
- No step may attach a remote to, or push, the current `~/code/second-brain` (soon `second-brain-legacy`) — its git history already contains private transcripts.
- All edits happen in `~/code/second-brain-public` (the soon-to-be-promoted code root), never in the legacy dir.
- Any step that pushes to GitHub or renames/deletes a directory on the live machine must be flagged and confirmed before running — these are hard to reverse.

---

### Task 1: Update Python scripts to read `SECOND_BRAIN_DATA_DIR`

**Files:**
- Modify: `~/code/second-brain-public/bin/build_index.py`
- Modify: `~/code/second-brain-public/bin/search.py`
- Modify: `~/code/second-brain-public/bin/mcp_server.py`
- Modify: `~/code/second-brain-public/bin/import_plans.py`
- Modify: `~/code/second-brain-public/bin/import_codex_sessions.py`
- Modify: `~/code/second-brain-public/bin/import_claude_ai_export.py`
- Modify: `~/code/second-brain-public/bin/import_openai_export.py`

**Interfaces:**
- Produces: every one of these modules now exposes a module-level `DATA_DIR: Path`, resolved from `SECOND_BRAIN_DATA_DIR` env var (default `~/second-brain-data`). `SESSIONS_DIR`, `DB_PATH`, and `TARGET_DIR` (where present) are derived from `DATA_DIR`, not `REPO_DIR`.

- [ ] **Step 1: `bin/build_index.py`** — replace the path block:

```python
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract
import storage

REPO_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = REPO_DIR / "sessions"
DB_PATH = REPO_DIR / "embeddings" / "index.duckdb"
```

with:

```python
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract
import storage

DATA_DIR = Path(os.environ.get("SECOND_BRAIN_DATA_DIR", str(Path.home() / "second-brain-data")))
SESSIONS_DIR = DATA_DIR / "sessions"
DB_PATH = DATA_DIR / "embeddings" / "index.duckdb"
```

Then find the later line `rel_path = str(jsonl_file.relative_to(REPO_DIR))` and change `REPO_DIR` to `DATA_DIR`.

- [ ] **Step 2: `bin/search.py`** — replace:

```python
REPO_DIR = Path(__file__).resolve().parent.parent
DB_PATH = REPO_DIR / "embeddings" / "index.duckdb"
```

with:

```python
import os

DATA_DIR = Path(os.environ.get("SECOND_BRAIN_DATA_DIR", str(Path.home() / "second-brain-data")))
DB_PATH = DATA_DIR / "embeddings" / "index.duckdb"
```

(`import os` goes with the other stdlib imports at the top of the file, not inline — put it next to `import sys`.)

- [ ] **Step 3: `bin/mcp_server.py`** — same replacement as search.py:

```python
REPO_DIR = Path(__file__).resolve().parent.parent
DB_PATH = REPO_DIR / "embeddings" / "index.duckdb"
```

becomes:

```python
DATA_DIR = Path(os.environ.get("SECOND_BRAIN_DATA_DIR", str(Path.home() / "second-brain-data")))
DB_PATH = DATA_DIR / "embeddings" / "index.duckdb"
```

with `import os` added to the top-of-file imports (currently just `import sys` and `from pathlib import Path`).

- [ ] **Step 4: `bin/import_plans.py`** — replace:

```python
SOURCE_DIR = Path.home() / ".claude" / "plans"
REPO_DIR = Path(__file__).resolve().parent.parent
TARGET_DIR = REPO_DIR / "sessions" / "plans"
```

with:

```python
SOURCE_DIR = Path.home() / ".claude" / "plans"
DATA_DIR = Path(os.environ.get("SECOND_BRAIN_DATA_DIR", str(Path.home() / "second-brain-data")))
TARGET_DIR = DATA_DIR / "sessions" / "plans"
```

(`import os` is already present in this file's imports — leave it.)

- [ ] **Step 5: `bin/import_codex_sessions.py`** — replace:

```python
REPO_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = REPO_DIR / "sessions"
```

with:

```python
DATA_DIR = Path(os.environ.get("SECOND_BRAIN_DATA_DIR", str(Path.home() / "second-brain-data")))
SESSIONS_DIR = DATA_DIR / "sessions"
```

(`import os` already present.) The test file `tests/test_import_codex_sessions.py` monkeypatches `ics.SESSIONS_DIR` directly after import and never touches `REPO_DIR`/`DATA_DIR`, so it needs no changes — verify this in Step 8 below.

- [ ] **Step 6: `bin/import_claude_ai_export.py`** — replace:

```python
REPO_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = REPO_DIR / "sessions"
```

with:

```python
DATA_DIR = Path(os.environ.get("SECOND_BRAIN_DATA_DIR", str(Path.home() / "second-brain-data")))
SESSIONS_DIR = DATA_DIR / "sessions"
```

(`import os` already present.)

- [ ] **Step 7: `bin/import_openai_export.py`** — replace:

```python
REPO_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = REPO_DIR / "sessions"
TARGET_DIR = SESSIONS_DIR / "openai"
```

with:

```python
DATA_DIR = Path(os.environ.get("SECOND_BRAIN_DATA_DIR", str(Path.home() / "second-brain-data")))
SESSIONS_DIR = DATA_DIR / "sessions"
TARGET_DIR = SESSIONS_DIR / "openai"
```

(`import os` already present.)

- [ ] **Step 8: Verify no other `REPO_DIR` data-path usage was missed**

Run: `grep -rn "REPO_DIR" ~/code/second-brain-public/bin/`
Expected: only hits left are `.venv`, other `bin/*.py` paths, or `sys.path` — no `sessions`, `embeddings`, or `index.duckdb` reference through `REPO_DIR` anywhere.

- [ ] **Step 9: Run the existing smoke test**

Run: `cd ~/code/second-brain-public && SECOND_BRAIN_DATA_DIR=/tmp/sb-test-data .venv/bin/python tests/test_import_codex_sessions.py` (create `.venv` per README first if it doesn't exist in this dir yet — see Task 2 note)
Expected: all `PASS:` lines print, no `AssertionError`/traceback.

- [ ] **Step 10: Commit**

```bash
cd ~/code/second-brain-public
git add bin/build_index.py bin/search.py bin/mcp_server.py bin/import_plans.py \
  bin/import_codex_sessions.py bin/import_claude_ai_export.py bin/import_openai_export.py
git commit -m "Read data paths from SECOND_BRAIN_DATA_DIR instead of REPO_DIR"
```

---

### Task 2: Update shell scripts to read `SECOND_BRAIN_DATA_DIR`

**Files:**
- Modify: `~/code/second-brain-public/bin/archive-sessions.sh`
- Modify: `~/code/second-brain-public/bin/archive-codex-sessions.sh`
- Modify: `~/code/second-brain-public/bin/watch-claude-ai-inbox.sh`
- Modify: `~/code/second-brain-public/bin/watch-openai-inbox.sh`
- Modify: `~/code/second-brain-public/bin/import-claude-ai-export.sh`
- Modify: `~/code/second-brain-public/bin/import-openai-export.sh`

**Interfaces:**
- Consumes: nothing new from Task 1.
- Produces: every entry-point script now exports `SECOND_BRAIN_DATA_DIR` (so any script it shells out to inherits the same value) and uses `$DATA_DIR` for all session/log/state/inbox paths, while `$REPO_DIR` keeps meaning "where this script and `.venv` live."

- [ ] **Step 1: `bin/archive-sessions.sh`** — replace the whole file with:

```bash
#!/bin/bash
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
```

Note the rsync destination changed from `.../backups/second-brain/` to `.../backups/second-brain-data/` — this is a deliberate rename to make the remote side's naming match what's actually being backed up (data only, not a full repo checkout). Flag this in Task 6's verification step; the old `.../backups/second-brain/` path on the T7 is not deleted by this change, just no longer written to.

- [ ] **Step 2: `bin/archive-codex-sessions.sh`** — replace the whole file with:

```bash
#!/bin/bash
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
```

- [ ] **Step 3: `bin/watch-claude-ai-inbox.sh`** — replace the whole file with:

```bash
#!/bin/bash
set -euo pipefail

PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

REPO_DIR="/Users/jordan/code/second-brain"
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
```

- [ ] **Step 4: `bin/watch-openai-inbox.sh`** — replace the whole file with:

```bash
#!/bin/bash
set -euo pipefail

PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

REPO_DIR="/Users/jordan/code/second-brain"
DATA_DIR="${SECOND_BRAIN_DATA_DIR:-$HOME/second-brain-data}"
export SECOND_BRAIN_DATA_DIR="$DATA_DIR"
INBOX_DIR="$DATA_DIR/inbox-openai"
PROCESSED_DIR="$INBOX_DIR/processed"
STATE_DIR="$DATA_DIR/.state"
LOCK_DIR="$STATE_DIR/watch-inbox-openai.lock"

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
  if "$REPO_DIR/bin/import-openai-export.sh" "$export_file"; then
    dest="$PROCESSED_DIR/$(date '+%Y%m%d-%H%M%S')-$(basename "$export_file")"
    mv "$export_file" "$dest"
    log "Processed and moved to $dest"
  else
    log "ERROR: import failed for $export_file, leaving it in place for retry."
  fi
done
```

- [ ] **Step 5: `bin/import-claude-ai-export.sh`** — replace the whole file with:

```bash
#!/bin/bash
set -euo pipefail

PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

REPO_DIR="/Users/jordan/code/second-brain"
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
```

- [ ] **Step 6: `bin/import-openai-export.sh`** — replace the whole file with:

```bash
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
```

- [ ] **Step 7: Shellcheck / syntax sanity pass**

Run: `for f in ~/code/second-brain-public/bin/*.sh; do bash -n "$f" || echo "SYNTAX ERROR: $f"; done`
Expected: no `SYNTAX ERROR` lines.

- [ ] **Step 8: Commit**

```bash
cd ~/code/second-brain-public
git add bin/archive-sessions.sh bin/archive-codex-sessions.sh bin/watch-claude-ai-inbox.sh \
  bin/watch-openai-inbox.sh bin/import-claude-ai-export.sh bin/import-openai-export.sh
git commit -m "Read/write data paths under SECOND_BRAIN_DATA_DIR instead of REPO_DIR"
```

---

### Task 3: Update launchd templates and `init.sh` for the new data root

**Files:**
- Modify: `~/code/second-brain-public/launchd/archive-sessions.plist.template`
- Modify: `~/code/second-brain-public/launchd/archive-codex-sessions.plist.template`
- Modify: `~/code/second-brain-public/launchd/watch-claude-ai-inbox.plist.template`
- Modify: `~/code/second-brain-public/launchd/watch-openai-inbox.plist.template`
- Modify: `~/code/second-brain-public/init.sh`

**Interfaces:**
- Consumes: `SECOND_BRAIN_DATA_DIR` contract from Tasks 1–2.
- Produces: `install_job()` in `init.sh` now substitutes a third placeholder, `__DATA_DIR__`, into each rendered plist; every plist sets `SECOND_BRAIN_DATA_DIR` explicitly via `<key>EnvironmentVariables</key>` so launchd-spawned scripts don't rely on a shell default; `WatchPaths` and log paths that point at data (not code) use `__DATA_DIR__`.

- [ ] **Step 1: `launchd/archive-sessions.plist.template`** — replace with:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>__LABEL_PREFIX__.archive-sessions</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>__REPO_DIR__/bin/archive-sessions.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>__REPO_DIR__</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>SECOND_BRAIN_DATA_DIR</key>
        <string>__DATA_DIR__</string>
    </dict>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>__DATA_DIR__/logs/archive-sessions.out.log</string>

    <key>StandardErrorPath</key>
    <string>__DATA_DIR__/logs/archive-sessions.err.log</string>

    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
```

- [ ] **Step 2: `launchd/archive-codex-sessions.plist.template`** — same pattern, replace with:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>__LABEL_PREFIX__.archive-codex-sessions</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>__REPO_DIR__/bin/archive-codex-sessions.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>__REPO_DIR__</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>SECOND_BRAIN_DATA_DIR</key>
        <string>__DATA_DIR__</string>
    </dict>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>15</integer>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>__DATA_DIR__/logs/archive-codex-sessions.out.log</string>

    <key>StandardErrorPath</key>
    <string>__DATA_DIR__/logs/archive-codex-sessions.err.log</string>

    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
```

- [ ] **Step 3: `launchd/watch-claude-ai-inbox.plist.template`** — replace with:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>__LABEL_PREFIX__.watch-claude-ai-inbox</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>__REPO_DIR__/bin/watch-claude-ai-inbox.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>__REPO_DIR__</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>SECOND_BRAIN_DATA_DIR</key>
        <string>__DATA_DIR__</string>
    </dict>

    <key>WatchPaths</key>
    <array>
        <string>__DATA_DIR__/inbox</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>__DATA_DIR__/logs/watch-claude-ai-inbox.out.log</string>

    <key>StandardErrorPath</key>
    <string>__DATA_DIR__/logs/watch-claude-ai-inbox.err.log</string>

    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
```

- [ ] **Step 4: `launchd/watch-openai-inbox.plist.template`** — replace with:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>__LABEL_PREFIX__.watch-openai-inbox</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>__REPO_DIR__/bin/watch-openai-inbox.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>__REPO_DIR__</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>SECOND_BRAIN_DATA_DIR</key>
        <string>__DATA_DIR__</string>
    </dict>

    <key>WatchPaths</key>
    <array>
        <string>__DATA_DIR__/inbox-openai</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>__DATA_DIR__/logs/watch-openai-inbox.out.log</string>

    <key>StandardErrorPath</key>
    <string>__DATA_DIR__/logs/watch-openai-inbox.err.log</string>

    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
```

- [ ] **Step 5: `init.sh`** — replace the whole file with:

```bash
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
```

- [ ] **Step 6: Verify template substitution has no leftover placeholders**

Run: `DATA_DIR=/tmp/sb-data-check; REPO_DIR=/tmp/sb-repo-check; for f in ~/code/second-brain-public/launchd/*.plist.template; do sed -e "s|__REPO_DIR__|$REPO_DIR|g" -e "s|__DATA_DIR__|$DATA_DIR|g" -e "s|__LABEL_PREFIX__|com.test.second-brain|g" "$f" | grep -q '__' && echo "LEFTOVER PLACEHOLDER: $f"; done`
Expected: no `LEFTOVER PLACEHOLDER` lines.

- [ ] **Step 7: Commit**

```bash
cd ~/code/second-brain-public
git add launchd/ init.sh
git commit -m "Wire launchd jobs and init.sh to a separate SECOND_BRAIN_DATA_DIR"
```

---

### Task 4: Push code-root changes to GitHub

This step publishes to a shared, third-party-hosted remote — confirm with Jordan before running, per the standing rule on remote-visible actions.

- [ ] **Step 1: Review the diff one more time**

Run: `cd ~/code/second-brain-public && git log --oneline origin/main..HEAD && git diff origin/main..HEAD --stat`
Expected: only the files touched in Tasks 1–3 show up; nothing from `sessions/`, `.env`, or other private paths (there shouldn't be any, since this directory never held them, but confirm).

- [ ] **Step 2: Push (only after explicit go-ahead)**

```bash
cd ~/code/second-brain-public
git push origin main
```

---

### Task 5: Seed the new data root from the current live data

This copies (not moves) the current data so the pre-migration `~/code/second-brain` is left fully intact for Task 6's rename — nothing here is destructive.

**Files:**
- Create: `~/second-brain-data/` (new directory, new git repo)

- [ ] **Step 1: Create the data root and copy current data into it**

```bash
DATA_DIR="$HOME/second-brain-data"
mkdir -p "$DATA_DIR"
rsync -a \
  ~/code/second-brain/sessions/ "$DATA_DIR/sessions/" \
  ~/code/second-brain/embeddings/ "$DATA_DIR/embeddings/" \
  ~/code/second-brain/logs/ "$DATA_DIR/logs/" \
  ~/code/second-brain/.state/ "$DATA_DIR/.state/" \
  ~/code/second-brain/inbox/ "$DATA_DIR/inbox/" \
  ~/code/second-brain/inbox-openai/ "$DATA_DIR/inbox-openai/"
```

(Note: `rsync -a src1/ src2/ ... dest/` only works when the last argument is the destination and you pass one source at a time in most rsync builds — if this errors, run the six `rsync -a <src>/ <dest>/` invocations separately instead, one per directory, all targeting subdirectories of `"$DATA_DIR"`.)

- [ ] **Step 2: git init the data root, no remote**

```bash
cd "$HOME/second-brain-data"
git init
printf '.state/\nlogs/\n.venv/\nembeddings/\n__pycache__/\ninbox/\ninbox-openai/\n' > .gitignore
git add sessions/ .gitignore
git commit -m "Seed data root from ~/code/second-brain (legacy) at time of code/data split"
git remote -v
```

Expected: `git remote -v` prints nothing (no remote configured).

- [ ] **Step 3: Verify byte-for-byte parity with the source before touching anything else**

Run: `diff -rq ~/code/second-brain/sessions "$HOME/second-brain-data/sessions"`
Expected: no output (identical trees). If it prints differences, stop and investigate before proceeding to Task 6 — do not rename the source directory until this is clean.

---

### Task 6: Promote/retire directories on this machine

Both renames are local filesystem operations, easily reversible (rename back) as long as nothing else has touched the paths in between — but flagged here because this session's own working directory is one of the paths being renamed. Confirm with Jordan before running.

- [ ] **Step 1: Rename the current (private-history) working repo to `-legacy`**

```bash
mv ~/code/second-brain ~/code/second-brain-legacy
```

- [ ] **Step 2: Promote the public repo to take over the canonical path**

```bash
mv ~/code/second-brain-public ~/code/second-brain
```

- [ ] **Step 3: Re-anchor this shell/session to the new path**

```bash
cd ~/code/second-brain
pwd
```

Expected: prints `/Users/jordan/code/second-brain`. If any subsequent command in this session reports a stale/missing-directory error, this `cd` should be re-run.

- [ ] **Step 4: Confirm the legacy repo is intact and has no remote**

```bash
git -C ~/code/second-brain-legacy remote -v
git -C ~/code/second-brain-legacy log --oneline -3
```

Expected: `remote -v` prints nothing; `log` shows the same recent commits it had before the rename.

- [ ] **Step 5: Confirm the promoted repo has the GitHub remote**

```bash
git -C ~/code/second-brain remote -v
```

Expected: `origin  https://github.com/jordanskole/second-brain.git (fetch)` and `(push)`.

---

### Task 7: Reinstall the live launchd jobs

The four jobs are currently installed pointing at the pre-migration paths and script contents (cached by launchd at load time — editing files on disk doesn't change a running job's config until it's reloaded). This step must run after Task 6's rename, since it re-renders the plists from `~/code/second-brain` (the now-promoted path).

- [ ] **Step 1: Unload the currently-installed jobs**

```bash
for name in archive-sessions watch-claude-ai-inbox archive-codex-sessions watch-openai-inbox; do
  launchctl bootout "gui/$(id -u)/com.jordan.second-brain.$name" 2>/dev/null || true
done
```

- [ ] **Step 2: Re-run init.sh to render and install fresh plists**

```bash
cd ~/code/second-brain
./init.sh
```

Expected output includes four `Installed com.jordan.second-brain.<name> -> ...` lines and ends with the `Done.` summary block.

- [ ] **Step 3: Confirm the installed plists point at the new data root**

```bash
grep -A1 SECOND_BRAIN_DATA_DIR ~/Library/LaunchAgents/com.jordan.second-brain.archive-sessions.plist
```

Expected: shows `<string>/Users/jordan/second-brain-data</string>` (or `$HOME`-expanded equivalent).

---

### Task 8: End-to-end verification

- [ ] **Step 1: Manually trigger the nightly archive job and watch it run**

```bash
launchctl kickstart -k "gui/$(id -u)/com.jordan.second-brain.archive-sessions"
sleep 5
tail -30 ~/second-brain-data/logs/archive-sessions.out.log
```

Expected: log shows a normal run (copied N files, committed or "No net changes", search index updated, backup to apps.jarvis complete) with no `WARNING` about missing `.venv` or failed rsync.

- [ ] **Step 2: Confirm the data root's git history advanced (or stayed clean) as expected**

```bash
git -C ~/second-brain-data log --oneline -5
git -C ~/second-brain-data remote -v
```

Expected: newest commit (if any) is from the archive run just triggered; `remote -v` still prints nothing.

- [ ] **Step 3: Confirm the T7 backup landed at the new path**

```bash
ssh jordan@apps.jarvis "ls -la /mnt/t7/backups/second-brain-data/ | head"
```

Expected: shows `sessions/`, `embeddings/`, `.state/`, `logs/` etc., with recent mtimes.

- [ ] **Step 4: Confirm semantic search still works against the new `DB_PATH`**

```bash
cd ~/code/second-brain
SECOND_BRAIN_DATA_DIR="$HOME/second-brain-data" .venv/bin/python bin/search.py "second brain data split" --k 3
```

(If `.venv` doesn't exist yet in the promoted `~/code/second-brain`, create it per this repo's own README before running — same steps as the legacy repo's setup.)

Expected: prints up to 3 results with no traceback; confirms `embeddings/index.duckdb` under the new data root is being read correctly.

- [ ] **Step 5: Confirm the MCP server (used by `second-brain-search` in Claude Code) still finds the index**

```bash
cd ~/code/second-brain
SECOND_BRAIN_DATA_DIR="$HOME/second-brain-data" .venv/bin/python -c "
from pathlib import Path
import bin.mcp_server as m
print(m.DATA_DIR, m.DB_PATH, m.DB_PATH.exists())
"
```

(Adjust the import if `bin/` isn't a package — running `PYTHONPATH=bin .venv/bin/python -c "import mcp_server as m; ..."` is the fallback if the above import fails.)

Expected: prints the new `DATA_DIR`/`DB_PATH` and `True` for existence. Note: any Claude Code MCP client config pointing at the old `mcp_server.py` path or lacking `SECOND_BRAIN_DATA_DIR` in its own env needs a matching update — check `~/.claude` MCP server config for this project and update it if it hardcodes anything under the old repo layout.

---

### Task 9: Update documentation

**Files:**
- Modify: `~/code/second-brain/README.md`
- Modify: `~/code/second-brain-legacy/README.md` (add a short pointer only — this repo is frozen)

- [ ] **Step 1: Update `~/code/second-brain/README.md`**

Add a section (near the top, after any existing overview) documenting the new layout:

```markdown
## Layout

This repo is code only — `bin/`, tests, launchd templates. It has no session data in its
history and never will.

Data lives in a separate root, `~/second-brain-data` by default (override with
`SECOND_BRAIN_DATA_DIR`): `sessions/`, `embeddings/`, `logs/`, `.state/`, `inbox/`,
`inbox-openai/`. That directory is its own local git repo (for archive history) but is never
given a remote.

Run `./init.sh` once to scaffold the data root, install the launchd jobs, and wire everything
together.
```

- [ ] **Step 2: Add a one-line pointer to the legacy repo's README**

```bash
cat >> ~/code/second-brain-legacy/README.md <<'EOF'

---

**This directory is retired.** As of 2026-08-20, the code moved to `~/code/second-brain`
(promoted from `second-brain-public`) and the data moved to `~/second-brain-data`. This repo
is kept only as a local, no-remote historical record — do not add a remote or push it.
EOF
```

- [ ] **Step 3: Commit both**

```bash
cd ~/code/second-brain && git add README.md && git commit -m "Document the code/data split layout"
cd ~/code/second-brain-legacy && git add README.md && git commit -m "Note this repo is retired"
```

- [ ] **Step 4: Push the code-root README change**

```bash
cd ~/code/second-brain && git push origin main
```

(Confirm before pushing, same as Task 4 — this is the second and last push in this plan.)
