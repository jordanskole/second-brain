#!/usr/bin/env python3
"""Convert an OpenAI/ChatGPT data export into session .jsonl files.

Reuses the existing extract.py/build_index.py pipeline unmodified: each
ChatGPT conversation becomes a sessions/openai/<conversation-id>.jsonl file
in the same minimal schema Claude Code transcripts use (type, uuid,
sessionId, timestamp, message.content).

ChatGPT stores each conversation as a branching tree (to support message
edits/regenerations) rather than a flat list, so messages live in a
`mapping` of node id -> {message, parent, children} and the actively
displayed conversation is reconstructed by walking backward from
`current_node` via `parent` pointers to the root.

Idempotent: each conversation's .jsonl mtime is stamped to the conversation's
update_time, so build_index.py's existing mtime-based skip logic only
re-embeds conversations that actually changed since the last import.

Usage: import_openai_export.py <path-to-export.zip-or-already-unzipped-dir>
"""

import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = REPO_DIR / "sessions"
TARGET_DIR = SESSIONS_DIR / "openai"

ROLE_BY_AUTHOR = {"user": "user", "assistant": "assistant"}
KNOWN_ROLES = {"system", "user", "assistant", "tool"}
TEXT_CONTENT_TYPES = {"text", "multimodal_text"}


def parse_epoch(ts) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def linear_chain(conv: dict, warnings: dict) -> list[dict]:
    mapping = conv.get("mapping") or {}
    current_node = conv.get("current_node")

    if not current_node or current_node not in mapping:
        leaves = [nid for nid, node in mapping.items() if not node.get("children")]
        if not leaves:
            return []

        def depth(nid):
            d, seen = 0, set()
            while nid and nid not in seen:
                seen.add(nid)
                node = mapping.get(nid)
                if not node:
                    break
                nid = node.get("parent")
                d += 1
            return d

        current_node = max(leaves, key=depth)
        warnings["current_node_fallback"] = warnings.get("current_node_fallback", 0) + 1

    chain, node_id, seen = [], current_node, set()
    while node_id and node_id not in seen:
        seen.add(node_id)
        node = mapping.get(node_id)
        if not node:
            break
        chain.append(node)
        node_id = node.get("parent")
    chain.reverse()
    return chain


def message_text(message: dict) -> str | None:
    content = message.get("content") or {}
    if content.get("content_type") not in TEXT_CONTENT_TYPES:
        return None
    parts = content.get("parts") or []
    text = "\n".join(p for p in parts if isinstance(p, str)).strip()
    return text or None


def conversation_to_records(conv: dict, warnings: dict) -> list[dict]:
    conv_id = conv.get("id")
    records = []
    for node in linear_chain(conv, warnings):
        message = node.get("message")
        if not message:
            continue

        author_role = (message.get("author") or {}).get("role")
        if author_role not in KNOWN_ROLES:
            seen = warnings.setdefault("unknown_roles", set())
            seen.add(author_role)
        role = ROLE_BY_AUTHOR.get(author_role)
        if role is None:
            continue

        text = message_text(message)
        if not text:
            continue

        msg_id = message.get("id")
        timestamp = parse_epoch(message.get("create_time")) or parse_epoch(conv.get("create_time"))
        if not msg_id or not timestamp:
            continue

        content = text if role == "user" else [{"type": "text", "text": text}]
        records.append(
            {
                "type": role,
                "uuid": msg_id,
                "sessionId": conv_id,
                "timestamp": timestamp,
                "message": {"role": role, "content": content},
            }
        )
    return records


def process(base: Path) -> None:
    conversations_file = base / "conversations.json"
    if not conversations_file.exists():
        print(f"error: {conversations_file} not found in export", file=sys.stderr)
        sys.exit(1)
    conversations = json.loads(conversations_file.read_text())

    written = updated = unchanged = skipped = 0
    warnings: dict = {}

    for conv in conversations:
        conv_id = conv.get("id")
        if not conv_id:
            skipped += 1
            continue

        records = conversation_to_records(conv, warnings)
        if not records:
            skipped += 1
            continue

        TARGET_DIR.mkdir(parents=True, exist_ok=True)
        target_file = TARGET_DIR / f"{conv_id}.jsonl"

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

        mtime = conv.get("update_time") or conv.get("create_time")
        if isinstance(mtime, (int, float)):
            os.utime(target_file, (mtime, mtime))
        else:
            print(f"warn: no usable timestamp for conversation {conv_id}, mtime left as-is", file=sys.stderr)

    if warnings.get("current_node_fallback"):
        print(
            f"warn: current_node missing/invalid for {warnings['current_node_fallback']} "
            "conversation(s); fell back to picking the deepest leaf. This may mean the "
            "export schema doesn't match what this script assumes -- worth spot-checking.",
            file=sys.stderr,
        )
    if warnings.get("unknown_roles"):
        print(
            f"warn: saw unexpected author.role value(s): {sorted(warnings['unknown_roles'])}. "
            "These were dropped, not imported.",
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
