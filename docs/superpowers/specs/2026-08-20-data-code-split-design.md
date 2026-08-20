# Second-brain data/code split — design

## Why

`~/code/second-brain` (this repo) is currently both the code repo *and* the data store: `sessions/`,
`embeddings/`, `logs/`, `.state/`, `inbox/`, `inbox-openai/` all live inside the same git working tree
that `bin/` and `README.md` live in. Because that data must never be public, a second, independently-
tracked directory (`~/code/second-brain-public`) was created to hold a public-safe copy of just `bin/`,
pushed by hand to `https://github.com/jordanskole/second-brain`. Nothing keeps the two in sync
automatically, and both directories share the name "second-brain," which has already caused a mix-up
(asking "is origin/main current?" without specifying which one).

A fresh discovery mid-design: `second-brain-public` already has an `init.sh` + launchd templates
(added earlier the same day) that scaffold `sessions/`, `logs/`, `.state/`, `inbox*/` directly inside
wherever the public repo is cloned, relying on `.gitignore` (which already excludes `sessions/` there)
to keep that data out of git history. That's a clean answer to "where should we save your sessions" —
the clone location *is* the answer — but it only works for a **fresh** clone. It cannot be retrofitted
onto the *existing* `~/code/second-brain`, because that repo's local git history already has session
transcripts committed into past commits (`archive-sessions.sh` runs `git add sessions/ && git commit`
nightly). `.gitignore` only stops *new* files from being staged — it does nothing to blobs already
committed. Pointing that specific `.git` at the public GitHub remote and ever running `git push` would
upload the entire history, transcripts included.

## Decisions (confirmed with Jordan 2026-08-20)

1. **Data root stays a local git repo** — commits continue, but the repo is never given a remote. This
   preserves diff/revert-ability of the session archive (over plain-files-plus-rsync).
2. **The current `~/code/second-brain`'s git history is archived locally, untouched** — renamed to
   `~/code/second-brain-legacy`, never connected to a remote, kept as a local-only fallback. Its
   sessions-in-history problem is *why* it can never be reused as the code root going forward.
3. **`~/code/second-brain-public` is promoted to become the canonical code root**, taking over the path
   `~/code/second-brain` (freed up by the rename in #2). It already has `origin` pointing at
   `https://github.com/jordanskole/second-brain` and never had private data in its history.
4. **A new, separate data root** (`~/second-brain-data`) holds `sessions/`, `embeddings/`, `logs/`,
   `.state/`, `inbox/`, `inbox-openai/` going forward, seeded fresh from the current live data (not a
   history-preserving migration — the old history stays in the legacy dir per #2).

## Target layout

```
~/code/second-brain/          <- code root (was second-brain-public), has origin, no private data ever
~/code/second-brain-legacy/   <- frozen, untouched, no remote (was second-brain, has old session history)
~/second-brain-data/          <- data root, local git only (no remote), sessions/embeddings/logs/.state/inbox*
```

## Wiring: `SECOND_BRAIN_DATA_DIR`

Every script that currently derives a data path from `REPO_DIR` (script location) switches to reading
an env var, defaulting to the new data root:

```python
DATA_DIR = Path(os.environ.get("SECOND_BRAIN_DATA_DIR", str(Path.home() / "second-brain-data")))
```

```bash
DATA_DIR="${SECOND_BRAIN_DATA_DIR:-$HOME/second-brain-data}"
export SECOND_BRAIN_DATA_DIR="$DATA_DIR"
```

`REPO_DIR` (script location, i.e. the code root) is kept wherever a script needs it for genuinely
code-relative things (`.venv`, other `bin/*.py` scripts) — only *data* paths move to `DATA_DIR`. This
`SECOND_BRAIN_DATA_DIR` env var is also the onboarding hook a future packaged app's "where should we
save your sessions" step would set — for now it's a shell default, not an interactive prompt (no app
exists yet to prompt from — YAGNI).

launchd jobs don't inherit shell rc files, so each plist template gets an explicit
`<key>EnvironmentVariables</key>` block setting `SECOND_BRAIN_DATA_DIR`, rather than relying on the
script's bash default (keeps the launchd config the single source of truth for where a given machine's
data lives, visible in `launchctl print`).

## Non-goals

- No interactive onboarding wizard — that's for when this becomes a packaged app, not now.
- No change to the import/archive logic itself, only to *where* it reads/writes.
- No git history rewriting/filtering of the legacy repo (e.g. `git filter-repo` to strip transcripts) —
  it's being retired, not cleaned up, since it's never getting a remote.
