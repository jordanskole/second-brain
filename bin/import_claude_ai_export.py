#!/usr/bin/env python3
"""Convert a claude.ai account data export into session .jsonl files.

Reuses the existing extract.py/build_index.py pipeline unmodified: each
claude.ai conversation becomes a sessions/<project>/<conversation-uuid>.jsonl
file in the same minimal schema Claude Code transcripts use (type, uuid,
sessionId, timestamp, message.content). Conversations belonging to a
claude.ai Project land in sessions/claude-ai-<slugified-project-name>/;
everything else lands in sessions/claude-ai/.

Idempotent: each conversation's .jsonl mtime is stamped to the conversation's
updated_at, so build_index.py's existing mtime-based skip logic only
re-embeds conversations that actually changed since the last import.

Usage: import_claude_ai_export.py <path-to-export.zip-or-already-unzipped-dir>
"""

import json
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

DATA_DIR = Path(os.environ.get("SECOND_BRAIN_DATA_DIR", str(Path.home() / "second-brain-data")))
SESSIONS_DIR = DATA_DIR / "sessions"

ROLE_BY_SENDER = {"human": "user", "assistant": "assistant"}


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "untitled"


def parse_timestamp(ts: str) -> float | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError, TypeError):
        return None


def message_text(msg: dict) -> str:
    text = (msg.get("text") or "").strip()
    if text:
        return text
    content = msg.get("content") or []
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(parts).strip()


def conversation_to_records(conv: dict) -> list[dict]:
    conv_uuid = conv.get("uuid")
    records = []
    for msg in conv.get("chat_messages", []):
        role = ROLE_BY_SENDER.get(msg.get("sender"))
        if role is None:
            continue
        msg_uuid = msg.get("uuid")
        timestamp = msg.get("created_at") or msg.get("updated_at")
        if not msg_uuid or not timestamp:
            continue
        text = message_text(msg)
        if not text:
            continue
        content = text if role == "user" else [{"type": "text", "text": text}]
        records.append(
            {
                "type": role,
                "uuid": msg_uuid,
                "sessionId": conv_uuid,
                "timestamp": timestamp,
                "message": {"role": role, "content": content},
            }
        )
    return records


def project_uuid_of(conv: dict) -> str | None:
    if conv.get("project_uuid"):
        return conv["project_uuid"]
    project = conv.get("project")
    if isinstance(project, dict):
        return project.get("uuid")
    return None


def target_dir_for(conv: dict, projects_by_uuid: dict) -> Path:
    puuid = project_uuid_of(conv)
    if puuid and puuid in projects_by_uuid:
        name = projects_by_uuid[puuid].get("name") or puuid
        return SESSIONS_DIR / f"claude-ai-{slugify(name)}"
    return SESSIONS_DIR / "claude-ai"


def process(base: Path) -> None:
    conversations_file = base / "conversations.json"
    if not conversations_file.exists():
        print(f"error: {conversations_file} not found in export", file=sys.stderr)
        sys.exit(1)
    conversations = json.loads(conversations_file.read_text())

    projects_by_uuid = {}
    projects_file = base / "projects.json"
    if projects_file.exists():
        for p in json.loads(projects_file.read_text()):
            if isinstance(p, dict) and p.get("uuid"):
                projects_by_uuid[p["uuid"]] = p

    written = updated = unchanged = skipped = 0
    found_project_linkage = False

    for conv in conversations:
        conv_uuid = conv.get("uuid")
        if not conv_uuid:
            skipped += 1
            continue

        if project_uuid_of(conv):
            found_project_linkage = True

        records = conversation_to_records(conv)
        if not records:
            skipped += 1
            continue

        target_dir = target_dir_for(conv, projects_by_uuid)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{conv_uuid}.jsonl"

        new_content = "\n".join(json.dumps(r) for r in records) + "\n"
        old_content = target_file.read_text() if target_file.exists() else None

        if old_content == new_content:
            unchanged += 1
        else:
            if target_file.exists():
                updated += 1
            else:
                written += 1
            target_file.write_text(new_content)

        updated_at = conv.get("updated_at") or conv.get("created_at")
        mtime = parse_timestamp(updated_at) if updated_at else None
        if mtime is not None:
            os.utime(target_file, (mtime, mtime))
        else:
            print(f"warn: no usable timestamp for conversation {conv_uuid}, mtime left as-is", file=sys.stderr)

    if projects_by_uuid and not found_project_linkage:
        print(
            "warn: projects.json present but no conversation had a recognizable "
            "project-linkage field; everything was filed under sessions/claude-ai/. "
            "Check the export's actual field names (project_uuid vs. something else) "
            "and update project_uuid_of() if you want project grouping.",
            file=sys.stderr,
        )

    print(
        f"Conversations: {len(conversations)} total, "
        f"written={written} updated={updated} unchanged={unchanged} skipped={skipped}"
    )


def main() -> None:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <path-to-export.zip-or-dir>", file=sys.stderr)
        sys.exit(1)

    export_path = Path(sys.argv[1]).expanduser().resolve()
    if not export_path.exists():
        print(f"error: {export_path} does not exist", file=sys.stderr)
        sys.exit(1)

    if export_path.is_dir():
        process(export_path)
    else:
        with TemporaryDirectory() as tmp, zipfile.ZipFile(export_path) as zf:
            zf.extractall(tmp)
            process(Path(tmp))


if __name__ == "__main__":
    main()
