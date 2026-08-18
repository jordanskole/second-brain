# second-brain

Durable, version-controlled archive of Claude Code session transcripts.

**This repo is the tooling only.** The actual archive it produces
(`sessions/`, `embeddings/`, and other personal transcript data) is
gitignored here and kept in a separate private store — nothing in this repo
ever contains conversation content.

## Why

Claude Code session transcripts (`~/.claude/projects/<project>/<uuid>.jsonl`) expire
after 30 days locally. This repo is a nightly mirror of those files, committed to git,
so they survive past that expiry window.

**Scope (phase one):** only the top-level `<uuid>.jsonl` transcript per session.
Sidecar data (`subagents/`, `tool-results/`) and the `memory/` notes folder are not
archived yet.

## Layout

- `sessions/` — mirror of `~/.claude/projects/`, one subdirectory per project. Gitignored in this repo; tracked in git in the private archive.
- `bin/archive-sessions.sh` — the archival script, run nightly by launchd.
- `launchd/*.plist.template` — launchd job templates, filled in by `init.sh`.
- `init.sh` — one-time bootstrap: scaffolds dirs and installs the launchd jobs.
- `.state/` — local bookkeeping (last-run timestamp, run lock). Gitignored.
- `logs/` — launchd stdout/stderr from each run. Gitignored.

## How it works

Each run:
1. Finds every `~/.claude/projects/*/*.jsonl` file with an mtime newer than the last
   successful run.
2. Copies changed files into `sessions/`, preserving the relative
   `<project-dir>/<uuid>.jsonl` path.
3. `git add` + `git commit`s the result. If nothing actually changed content-wise,
   git no-ops (commit is skipped).
4. Only after a successful add/commit does it advance the last-run timestamp — a
   crash or failure mid-run just means the next run retries everything missed.

Nothing is ever deleted or pruned from `sessions/` — once a session is archived it
stays in history even after the source `.jsonl` expires and disappears upstream.

## Scheduling

Runs nightly at 3:00 AM via a macOS launchd LaunchAgent:
`~/Library/LaunchAgents/com.$(whoami).second-brain.archive-sessions.plist`. It also
runs on login/reboot (`RunAtLoad`), which is safe since the script is idempotent.

Useful commands:

```bash
# Check the job is loaded and see its last exit code
launchctl print gui/$(id -u)/com.$(whoami).second-brain.archive-sessions

# Trigger an immediate run
launchctl kickstart -k gui/$(id -u)/com.$(whoami).second-brain.archive-sessions

# Check what happened
tail logs/archive-sessions.out.log
tail logs/archive-sessions.err.log
git log --oneline
```

## Importing claude.ai (web) chat history

claude.ai has no local file to mirror and no live API — the only bulk export
is the account data export (Settings → Account → "Export data" on claude.ai),
which emails a download link for a zip containing `conversations.json` (and
`projects.json` if you use claude.ai Projects). This is a manual, periodic
step; there's no nightly automation for it.

Once you have the zip:

```bash
bin/import-claude-ai-export.sh ~/Downloads/data-export.zip
```

This converts each conversation into the same JSONL schema Claude Code
transcripts use (via `bin/import_claude_ai_export.py`), files it under
`sessions/claude-ai/` (or `sessions/claude-ai-<project-name>/` for
conversations that belong to a claude.ai Project), commits any new/changed
conversations, and rebuilds the search index. Re-running against a later
export is idempotent — unchanged conversations are skipped, only ones with
new messages get re-embedded.

### Automatic import: drop the export in `inbox/`

Instead of running `import-claude-ai-export.sh` by hand, drop the downloaded
zip into `inbox/` (create it if it doesn't exist — it's gitignored, just
local staging). A macOS launchd LaunchAgent
(`~/Library/LaunchAgents/com.$(whoami).second-brain.watch-claude-ai-inbox.plist`,
`WatchPaths` on `inbox/`) fires within seconds of a file appearing there,
runs every `*.zip` in `inbox/` through `import-claude-ai-export.sh`, and
moves each one to `inbox/processed/<timestamp>-<name>.zip` once it succeeds.
Failed imports are left in place in `inbox/` for retry. Backed by
`bin/watch-claude-ai-inbox.sh`; logs go to `logs/watch-claude-ai-inbox.{out,err}.log`.

## Importing ChatGPT (OpenAI) chat history

Like claude.ai, ChatGPT has no live API for pulling history — the only bulk
export is Settings → Data controls → Export data on chatgpt.com, which
emails a download link for a zip containing `conversations.json`. This is a
manual, periodic step; there's no nightly automation for it.

Once you have the zip:

```bash
bin/import-openai-export.sh ~/Downloads/chatgpt-export.zip
```

This converts each conversation into the same JSONL schema Claude Code
transcripts use (via `bin/import_openai_export.py`), filing everything under
`sessions/openai/` (ChatGPT's export has no reliable project-equivalent
grouping field, so there's no per-project splitting here, unlike the
claude.ai importer). Each ChatGPT conversation stores its messages as a
branching tree rather than a flat list (to support edits/regenerations); the
importer walks from the active leaf (`current_node`) back to the root via
parent pointers to reconstruct the single conversation actually shown,
discarding abandoned branches. System and tool-call messages are dropped
(only user/assistant text is imported, matching this repo's phase-one
text-only scope). Re-running against a later export is idempotent —
unchanged conversations are skipped, only ones with new messages get
re-embedded.

### Automatic import: drop the export in `inbox-openai/`

Instead of running `import-openai-export.sh` by hand, drop the downloaded
zip into `inbox-openai/` (create it if it doesn't exist — it's gitignored,
just local staging; kept separate from the claude.ai `inbox/` rather than a
shared/dispatched inbox). A macOS launchd LaunchAgent
(`~/Library/LaunchAgents/com.$(whoami).second-brain.watch-openai-inbox.plist`,
`WatchPaths` on `inbox-openai/`) fires within seconds of a file appearing
there, runs every `*.zip` in `inbox-openai/` through
`import-openai-export.sh`, and moves each one to
`inbox-openai/processed/<timestamp>-<name>.zip` once it succeeds. Failed
imports are left in place in `inbox-openai/` for retry. Backed by
`bin/watch-openai-inbox.sh`; logs go to `logs/watch-openai-inbox.{out,err}.log`.

## Bootstrap (one-time setup on a new machine)

Don't run shell scripts off the internet willy-nilly, including this one —
read [`init.sh`](init.sh) first so you know what it's doing (scaffolding
dirs, writing launchd plists into `~/Library/LaunchAgents/`, and enabling
them) before you run it.

Clone this repo wherever you want it to live (e.g. `~/code/second-brain`),
then run:

```bash
./init.sh
```

This creates the local dirs (`sessions/`, `logs/`, `.state/`, `inbox/`,
`inbox-openai/`), `git init`s if needed, and installs+enables all three
launchd jobs under a label derived from your username and the repo's actual
path (`com.$(whoami).second-brain.*`) — no manual path/label editing
required. The plist templates live in `launchd/`; `init.sh` fills in
`__REPO_DIR__`/`__LABEL_PREFIX__` and writes the result to
`~/Library/LaunchAgents/`. Safe to re-run.

## Encryption

None beyond macOS FileVault (whole-disk encryption) and whatever the private
data store (outside this repo) provides. This repo itself never contains
transcript content, so there's nothing here to encrypt.
