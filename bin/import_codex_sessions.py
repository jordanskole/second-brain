#!/usr/bin/env python3
"""Convert Codex CLI rollout session files into session .jsonl files.

Codex CLI (like Claude Code) stores live session transcripts locally, at
~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl, in Codex's own record schema
(session_meta / event_msg / response_item). This mirrors those into the same
minimal schema Claude Code transcripts already use (type, uuid, sessionId,
timestamp, message.content), one output file per Codex session.

Codex has its own "import external agent sessions" feature that replays
previously-imported history (e.g. Claude Code sessions) into new Codex
session files, tagging every replayed turn's turn_id with the prefix
"external-import-turn-". That content is already archived from the
original side, so those turns are dropped here to avoid double-indexing.
Filtering happens per turn (tracked via event_msg/task_started), not per
file, so a session that starts as a replay and is later continued with
genuinely new messages still has those new messages captured.

Idempotent: each session's .jsonl mtime is stamped to the source rollout
file's mtime, so build_index.py's existing mtime-based skip logic only
re-embeds sessions that actually changed since the last import.

Usage: import_codex_sessions.py <rollout.jsonl> [<rollout.jsonl> ...]
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = REPO_DIR / "sessions"

EXTERNAL_IMPORT_PREFIX = "external-import-turn-"
TEXT_CONTENT_TYPES = {"input_text", "output_text"}

# Codex auto-creates a scratch workspace under here (named from a slug of the
# conversation's opening message) for chats not attached to a real project.
# Treat that like "no cwd" rather than minting a one-off folder per chat.
CODEX_SCRATCH_ROOT = Path.home() / "Documents" / "Codex"

# Codex injects this boilerplate (available plugins, permissions, filesystem
# roots) as its own synthetic role=user response_item at the start of a
# session -- not something the user actually typed. Strip it out rather than
# archiving/indexing it as a real user message.
SYNTHETIC_CONTEXT_BLOCKS = re.compile(
    r"<(recommended_plugins|environment_context)>.*?</\1>", re.DOTALL
)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "untitled"


def target_dir_for(cwd: str | None) -> Path:
    if not cwd:
        return SESSIONS_DIR / "codex"
    cwd_path = Path(cwd)
    if cwd_path.is_relative_to(CODEX_SCRATCH_ROOT):
        return SESSIONS_DIR / "codex"
    basename = cwd_path.name or cwd
    return SESSIONS_DIR / f"codex-{slugify(basename)}"


def message_text(payload: dict) -> str | None:
    parts = payload.get("content") or []
    text = "\n".join(
        p.get("text", "")
        for p in parts
        if isinstance(p, dict) and p.get("type") in TEXT_CONTENT_TYPES and p.get("text")
    ).strip()
    if not text:
        return None
    text = SYNTHETIC_CONTEXT_BLOCKS.sub("", text).strip()
    return text or None


def extract_records(rollout_path: Path) -> tuple[str | None, str | None, list[dict]]:
    session_id: str | None = None
    cwd: str | None = None
    active_turn_id: str | None = None
    records: list[dict] = []
    line_no = 0

    with rollout_path.open() as fh:
        for line in fh:
            line_no += 1
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                print(f"warn: {rollout_path}:{line_no}: skipping malformed JSON", file=sys.stderr)
                continue

            rtype = rec.get("type")
            payload = rec.get("payload") or {}

            if rtype == "session_meta":
                session_id = payload.get("session_id") or payload.get("id")
                cwd = payload.get("cwd")
                continue

            if rtype == "event_msg":
                etype = payload.get("type")
                if etype == "task_started":
                    active_turn_id = payload.get("turn_id")
                elif etype == "task_complete":
                    active_turn_id = None
                continue

            if rtype != "response_item" or payload.get("type") != "message":
                continue

            if active_turn_id and active_turn_id.startswith(EXTERNAL_IMPORT_PREFIX):
                continue

            role = payload.get("role")
            if role not in ("user", "assistant"):
                continue

            text = message_text(payload)
            if not text:
                continue

            timestamp = rec.get("timestamp")
            if not timestamp:
                continue

            uuid = hashlib.sha1(f"{session_id}:{line_no}".encode()).hexdigest()
            content = text if role == "user" else [{"type": "text", "text": text}]
            records.append(
                {
                    "type": role,
                    "uuid": uuid,
                    "sessionId": session_id,
                    "timestamp": timestamp,
                    "message": {"role": role, "content": content},
                }
            )

    return session_id, cwd, records


def process(rollout_path: Path) -> str:
    session_id, cwd, records = extract_records(rollout_path)

    if not session_id:
        print(f"warn: {rollout_path}: no session_meta found, skipping", file=sys.stderr)
        return "skipped"

    if not records:
        return "empty"

    target_dir = target_dir_for(cwd)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{session_id}.jsonl"

    new_content = "\n".join(json.dumps(r) for r in records) + "\n"
    old_content = target_file.read_text() if target_file.exists() else None

    if old_content == new_content:
        status = "unchanged"
    else:
        status = "updated" if target_file.exists() else "written"
        target_file.write_text(new_content)

    src_mtime = rollout_path.stat().st_mtime
    os.utime(target_file, (src_mtime, src_mtime))
    return status


def main() -> None:
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <rollout.jsonl> [<rollout.jsonl> ...]", file=sys.stderr)
        sys.exit(1)

    counts = {"written": 0, "updated": 0, "unchanged": 0, "empty": 0, "skipped": 0}
    for arg in sys.argv[1:]:
        path = Path(arg).expanduser().resolve()
        if not path.exists():
            print(f"warn: {path} does not exist, skipping", file=sys.stderr)
            counts["skipped"] += 1
            continue
        try:
            status = process(path)
        except Exception as exc:  # noqa: BLE001 - one bad rollout must not abort the batch
            print(f"warn: {path}: failed to convert ({exc}), skipping", file=sys.stderr)
            counts["skipped"] += 1
            continue
        counts[status] += 1

    print(
        f"Rollout files: {len(sys.argv) - 1} total, "
        f"written={counts['written']} updated={counts['updated']} "
        f"unchanged={counts['unchanged']} empty={counts['empty']} skipped={counts['skipped']}"
    )


if __name__ == "__main__":
    main()
