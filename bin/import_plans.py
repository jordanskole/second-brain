#!/usr/bin/env python3
"""Import Claude Code plan files (~/.claude/plans/*.md) into the search index.

Reuses the existing extract.py/build_index.py pipeline unmodified: each plan
file becomes a sessions/plans/<slug>.jsonl file in the same minimal schema
Claude Code transcripts use (type, uuid, sessionId, timestamp,
message.content). Plans are single-author markdown I wrote myself, so each
one maps to "assistant" records -- no dialogue-role mismatch.

A plan is split into one record per top-level (##) section rather than one
record for the whole file: build_index.py's embedding step truncates any
single chunk at 512 tokens, and most plans run well past that, so a
whole-file chunk would silently drop everything after the first section or
two. Splitting on ## headers keeps each chunk well under that limit without
adding any new truncation/splitting logic to the shared pipeline -- extract.py
already yields one chunk per JSONL record, so multiple records per plan file
is all "chunking" requires here.

Idempotent: each plan's .jsonl mtime is stamped to the source .md file's
mtime, so build_index.py's existing mtime-based skip logic only re-embeds
plans that actually changed since the last import.

Usage: import_plans.py
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SOURCE_DIR = Path.home() / ".claude" / "plans"
REPO_DIR = Path(__file__).resolve().parent.parent
TARGET_DIR = REPO_DIR / "sessions" / "plans"

SECTION_RE = re.compile(r"^## .+$", re.MULTILINE)


def split_sections(text: str) -> list[str]:
    """Split on top-level (##) headers. Any preamble (title + intro before
    the first ##) stays attached to the first section; a plan with no ##
    headers at all comes back as a single section."""
    headers = list(SECTION_RE.finditer(text))
    if not headers:
        return [text]

    preamble = text[: headers[0].start()].strip()
    sections = []
    for i, header in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        section = text[header.start() : end].strip()
        if i == 0 and preamble:
            section = f"{preamble}\n\n{section}"
        sections.append(section)
    return sections


def plan_to_records(slug: str, text: str, timestamp: str) -> list[dict]:
    session_id = f"plan-{slug}"
    return [
        {
            "type": "assistant",
            "uuid": f"{session_id}-{i:03d}",
            "sessionId": session_id,
            "timestamp": timestamp,
            "message": {"role": "assistant", "content": [{"type": "text", "text": section}]},
        }
        for i, section in enumerate(split_sections(text))
        if section
    ]


def process() -> None:
    if not SOURCE_DIR.exists():
        print(f"No plans directory at {SOURCE_DIR}, nothing to do.")
        return

    written = updated = unchanged = skipped = 0

    for plan_file in sorted(SOURCE_DIR.glob("*.md")):
        text = plan_file.read_text().strip()
        if not text:
            skipped += 1
            continue

        slug = plan_file.stem
        mtime = plan_file.stat().st_mtime
        timestamp = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

        records = plan_to_records(slug, text, timestamp)

        TARGET_DIR.mkdir(parents=True, exist_ok=True)
        target_file = TARGET_DIR / f"{slug}.jsonl"

        new_content = "\n".join(json.dumps(r) for r in records) + "\n"
        old_content = target_file.read_text() if target_file.exists() else None
        old_mtime = target_file.stat().st_mtime if target_file.exists() else None

        if old_content == new_content:
            unchanged += 1
            continue

        if target_file.exists():
            updated += 1
        else:
            written += 1
        target_file.write_text(new_content)

        # Normally the source .md's mtime is a fine staleness signal for
        # build_index.py. But if only this script's chunking logic changed
        # (not the plan itself), the source mtime won't have moved -- so
        # force the dest mtime forward past its own previous value to make
        # sure the rewritten content still gets picked up for re-embedding.
        stamp = mtime if old_mtime is None else max(mtime, old_mtime + 1)
        os.utime(target_file, (stamp, stamp))

    print(f"Plans: written={written} updated={updated} unchanged={unchanged} skipped={skipped}")


def main() -> None:
    if len(sys.argv) != 1:
        print(f"usage: {sys.argv[0]}", file=sys.stderr)
        sys.exit(1)
    process()


if __name__ == "__main__":
    main()
