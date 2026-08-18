"""Parse a Claude Code session .jsonl file into clean, embeddable text chunks."""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class Chunk:
    chunk_id: str
    session_id: str
    project: str
    role: str
    timestamp: str
    text: str
    char_len: int


def iter_chunks(jsonl_path: Path, project: str) -> Iterator[Chunk]:
    with jsonl_path.open() as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                print(f"warn: {jsonl_path}:{lineno}: skipping malformed JSON", file=sys.stderr)
                continue

            rtype = rec.get("type")
            if rtype not in ("user", "assistant"):
                continue
            if rec.get("isMeta"):
                continue

            uuid = rec.get("uuid")
            session_id = rec.get("sessionId")
            timestamp = rec.get("timestamp")
            message = rec.get("message") or {}
            content = message.get("content")
            if not uuid or not session_id or not timestamp:
                continue

            if rtype == "user":
                if not isinstance(content, str):
                    continue
                text = content.strip()
                if not text or text.startswith("<local-command"):
                    continue
                yield Chunk(uuid, session_id, project, "user", timestamp, text, len(text))

            elif rtype == "assistant":
                if not isinstance(content, list):
                    continue
                text_parts = [
                    block["text"]
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
                ]
                if not text_parts:
                    continue
                text = "\n".join(text_parts).strip()
                if not text:
                    continue
                yield Chunk(uuid, session_id, project, "assistant", timestamp, text, len(text))
