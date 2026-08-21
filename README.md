# second-brain

Durable, version-controlled archive of Claude Code session transcripts.

**This repo is code only.** The actual archive it produces (`sessions/`,
`embeddings/`, and other personal transcript data) lives in a separate
directory — its own local git repo, never given a remote — that this code
reads and writes via the `SECOND_BRAIN_DATA_DIR` environment variable. See
[Layout](#layout). Nothing in this repo's working tree or history ever
contains conversation content.

## Requirements

- **macOS only.** Scheduling is done via launchd (`init.sh` installs
  LaunchAgents); there's no cron/systemd equivalent here yet.
- **Apple Silicon only, for the search index.** The embedding model runs on
  [MLX](https://github.com/ml-explore/mlx) (`mlx-embeddings`), which is
  Apple Silicon-specific — it won't run on Intel Macs or Linux. Archival
  itself (`bin/archive-sessions.sh`, the git mirroring) has no such
  restriction; only `build_index.py`/semantic search need MLX.
- Embedding a large backlog takes a while the first time (minutes, not
  seconds, for a few hundred sessions) since every session gets chunked and
  run through the model locally. Steady-state nightly runs are fast since
  only new/changed sessions get re-embedded.

## Why

Claude Code session transcripts (`~/.claude/projects/<project>/<uuid>.jsonl`) expire
after 30 days locally. This repo is a nightly mirror of those files, committed to git,
so they survive past that expiry window.

**Scope (phase one):** only the top-level `<uuid>.jsonl` transcript per session.
Sidecar data (`subagents/`, `tool-results/`) and the `memory/` notes folder are not
archived yet.

## Layout

Code and data are two separate roots, joined by one environment variable —
this repo never holds session content, so it can be public.

- **This repo** — `bin/*.sh`/`bin/*.py` (archival, import, and search
  scripts), `launchd/*.plist.template`, `init.sh` (one-time bootstrap:
  scaffolds the data root and installs the launchd jobs), tests.
- **The data root** — `$SECOND_BRAIN_DATA_DIR`, defaulting to
  `~/second-brain-data` if the variable is unset. Holds `sessions/`
  (mirror of `~/.claude/projects/`, one subdirectory per project),
  `embeddings/` (the search index), `logs/` (launchd stdout/stderr),
  `.state/` (last-run timestamps, run locks), `inbox/`/`inbox-openai/`
  (manual-export staging, see below). It's its own local git repo — commit
  history for the session archive — but `init.sh` never gives it a remote,
  and it shouldn't ever get one.

Every script resolves `SECOND_BRAIN_DATA_DIR` at startup with that same
`~/second-brain-data` fallback; export it before running `init.sh` (or
any `bin/*.sh` script) to put the data root somewhere else.

## How it works

Each run:
1. Finds every `~/.claude/projects/*/*.jsonl` file with an mtime newer than the last
   successful run.
2. Copies changed files into the data root's `sessions/`, preserving the
   relative `<project-dir>/<uuid>.jsonl` path.
3. `git add` + `git commit`s the result. If nothing actually changed content-wise,
   git no-ops (commit is skipped).
4. Only after a successful add/commit does it advance the last-run timestamp — a
   crash or failure mid-run just means the next run retries everything missed.

Nothing is ever deleted or pruned from `sessions/` — once a session is archived it
stays in history even after the source `.jsonl` expires and disappears upstream.

### Optional: offsite backup

After each run, `archive-sessions.sh` will also `rsync` the data root to a
remote destination — but only if you've configured one. This is
machine-specific, so it lives in an env file next to the data, not in this
repo: create `$SECOND_BRAIN_DATA_DIR/.env` (gitignored by `init.sh`) with

```bash
SECOND_BRAIN_T7_BACKUP_DEST=user@host:/path/to/backup/dir/
```

Leave it unset (or don't create the file) and this step is skipped with a
one-line log message, no error.

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

# Check what happened (paths under the data root, ~/second-brain-data by default)
tail "${SECOND_BRAIN_DATA_DIR:-$HOME/second-brain-data}/logs/archive-sessions.out.log"
tail "${SECOND_BRAIN_DATA_DIR:-$HOME/second-brain-data}/logs/archive-sessions.err.log"
git -C "${SECOND_BRAIN_DATA_DIR:-$HOME/second-brain-data}" log --oneline
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
zip into the data root's `inbox/` (`init.sh` creates it; just local
staging, not tracked in the data root's own git history). A macOS launchd
LaunchAgent
(`~/Library/LaunchAgents/com.$(whoami).second-brain.watch-claude-ai-inbox.plist`,
`WatchPaths` on `inbox/`) fires within seconds of a file appearing there,
runs every `*.zip` in `inbox/` through `import-claude-ai-export.sh`, and
moves each one to `inbox/processed/<timestamp>-<name>.zip` once it succeeds.
Failed imports are left in place in `inbox/` for retry. Backed by
`bin/watch-claude-ai-inbox.sh`; logs go to the data root's
`logs/watch-claude-ai-inbox.{out,err}.log`.

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
zip into the data root's `inbox-openai/` (`init.sh` creates it; kept
separate from the claude.ai `inbox/` rather than a shared/dispatched
inbox). A macOS launchd LaunchAgent
(`~/Library/LaunchAgents/com.$(whoami).second-brain.watch-openai-inbox.plist`,
`WatchPaths` on `inbox-openai/`) fires within seconds of a file appearing
there, runs every `*.zip` in `inbox-openai/` through
`import-openai-export.sh`, and moves each one to
`inbox-openai/processed/<timestamp>-<name>.zip` once it succeeds. Failed
imports are left in place in `inbox-openai/` for retry. Backed by
`bin/watch-openai-inbox.sh`; logs go to the data root's
`logs/watch-openai-inbox.{out,err}.log`.

## Importing Codex CLI chat history

Codex CLI stores live session transcripts locally at
`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`, the same way Claude Code stores
sessions under `~/.claude/projects/`. Because the data is already local (unlike
ChatGPT/claude.ai, which require a manual export), this is captured the same
way Claude Code sessions are: a nightly scan, not a manual import step.

Codex has its own "import external agent sessions" feature that can replay
previously-imported history (e.g. Claude Code sessions) into new Codex session
files. That content is already archived from the original side, so
`bin/import_codex_sessions.py` drops any turn tagged as a replay (`turn_id`
prefixed `external-import-turn-`) rather than double-indexing it. Filtering
happens per turn, not per file — if you continue one of those imported threads
in Codex, the new messages you add are still captured.

Each Codex session becomes `sessions/codex-<project-slug>/<session-id>.jsonl`
(`<project-slug>` derived from the session's working directory; sessions with
no recorded working directory land in `sessions/codex/`), converted into the
same JSONL schema every other provider uses here.

Two more Codex quirks the importer accounts for, found via real usage rather
than anticipated up front:

- For a chat with no project attached, Codex auto-creates a scratch workspace
  under `~/Documents/Codex/<date>/<slug-of-opening-message>/` and reports that
  as the session's working directory. Treating that path as a real project
  would mint a new one-off `sessions/codex-<slug>/` folder per ad-hoc chat, so
  it's detected and routed to the flat `sessions/codex/` fallback instead.
- Codex injects a `<recommended_plugins>`/`<environment_context>` boilerplate
  block as its own synthetic `role: user` message at the start of a session —
  not something actually typed. `import_codex_sessions.py` strips it rather
  than archiving/indexing it as real user content.

### Automatic import: nightly scan

A macOS launchd LaunchAgent
(`~/Library/LaunchAgents/com.$(whoami).second-brain.archive-codex-sessions.plist`)
runs `bin/archive-codex-sessions.sh` nightly at 3:15am (15 minutes after the
Claude Code archive run, to avoid both jobs touching the git repo and search
index at once). It finds rollout files with an mtime newer than the last
successful run, converts them, commits any new/changed sessions, and rebuilds
the search index. Logs go to the data root's
`logs/archive-codex-sessions.{out,err}.log`.

To run it immediately instead of waiting for the nightly schedule:

```bash
bin/archive-codex-sessions.sh
```

## Bootstrap (one-time setup on a new machine)

Don't run shell scripts off the internet willy-nilly, including this one —
read [`init.sh`](init.sh) first so you know what it's doing (scaffolding
dirs, writing launchd plists into `~/Library/LaunchAgents/`, and enabling
them) before you run it.

Clone this repo wherever you want the *code* to live (e.g.
`~/code/second-brain`), then run:

```bash
./init.sh
```

By default this creates the data root at `~/second-brain-data` — export
`SECOND_BRAIN_DATA_DIR=/wherever/you/want` first if you'd rather put it
somewhere else (a different drive, an iCloud-excluded folder, whatever).
`init.sh` scaffolds the data root's dirs (`sessions/`, `logs/`, `.state/`,
`inbox/`, `inbox-openai/`), `git init`s it if needed (and never gives it a
remote — keep it that way), and installs+enables all four launchd jobs
under a label derived from your username and this repo's actual path
(`com.$(whoami).second-brain.*`) — no manual path/label editing required.
The plist templates live in `launchd/`; `init.sh` fills in
`__REPO_DIR__`/`__DATA_DIR__`/`__LABEL_PREFIX__` and writes the result to
`~/Library/LaunchAgents/`, including an explicit `SECOND_BRAIN_DATA_DIR` in
each job's environment (launchd doesn't inherit your shell's env, so this
is what makes a non-default data root stick for the scheduled jobs, not
just interactive runs). Safe to re-run.

## Encryption

None beyond macOS FileVault (whole-disk encryption) and whatever the private
data store (outside this repo) provides. This repo itself never contains
transcript content, so there's nothing here to encrypt.
