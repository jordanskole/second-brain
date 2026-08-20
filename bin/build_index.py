#!/usr/bin/env python3
"""Incrementally embed session .jsonl files into the local semantic search index.

Skips source files whose mtime hasn't changed since they were last embedded.
Changed/new files have their old chunks (if any) replaced with a fresh re-embed
of the whole file (session files are append-only archival snapshots, so this is
cheap and avoids per-line diffing).
"""

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
MODEL_NAME = "mlx-community/all-MiniLM-L6-v2-4bit"
BATCH_SIZE = 32


def batched(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def embed_texts(model, tokenizer, texts) -> np.ndarray:
    inputs = tokenizer.batch_encode_plus(
        texts, return_tensors="mlx", padding=True, truncation=True, max_length=512
    )
    outputs = model(inputs["input_ids"], attention_mask=inputs["attention_mask"])
    return np.asarray(outputs.text_embeds, dtype=np.float32)


def main() -> None:
    if not SESSIONS_DIR.exists():
        print(f"No sessions directory at {SESSIONS_DIR}, nothing to do.")
        return

    print(f"Loading model {MODEL_NAME} ...")
    from mlx_embeddings.utils import load

    model, tokenizer = load(MODEL_NAME)

    conn = storage.open_db(DB_PATH)

    files_skipped = 0
    files_processed = 0
    files_failed = 0
    chunks_added = 0
    current_rel_paths = set()

    project_dirs = sorted(p for p in SESSIONS_DIR.iterdir() if p.is_dir())
    for project_dir in project_dirs:
        project = project_dir.name
        for jsonl_file in sorted(project_dir.glob("*.jsonl")):
            rel_path = str(jsonl_file.relative_to(DATA_DIR))
            current_rel_paths.add(rel_path)
            current_mtime = jsonl_file.stat().st_mtime
            last_mtime = storage.get_source_mtime(conn, rel_path)

            if last_mtime is not None and last_mtime == current_mtime:
                files_skipped += 1
                continue

            file_chunks = list(extract.iter_chunks(jsonl_file, project))
            # The session id used to delete a file's previous chunks must match what's
            # actually stored on those rows -- not always the filename stem. Plan files
            # (bin/import_plans.py) name the file after the plan's slug but stamp each
            # record's sessionId as "plan-<slug>", so deriving the delete key from the
            # filename silently deletes nothing and the reinsert collides with the rows
            # from the previous embed. Deriving it from the chunks' own session_id keeps
            # the delete and the insert operating on the same identity.
            session_id = file_chunks[0].session_id if file_chunks else jsonl_file.stem
            print(f"Embedding session {session_id}: {len(file_chunks)} chunks")

            conn.begin()
            try:
                storage.delete_chunks_for_source(conn, project, session_id)

                for batch in batched(file_chunks, BATCH_SIZE):
                    texts = [c.text for c in batch]
                    embs = embed_texts(model, tokenizer, texts)
                    for chunk, vec in zip(batch, embs):
                        storage.insert_chunk(conn, chunk, vec)

                embedded_at = datetime.now(timezone.utc).isoformat()
                storage.upsert_source_file(
                    conn, rel_path, current_mtime, len(file_chunks), embedded_at, session_id
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"WARNING: skipping {rel_path}, failed to embed: {exc}", file=sys.stderr)
                files_failed += 1
                continue

            files_processed += 1
            chunks_added += len(file_chunks)

    files_pruned = 0
    orphaned_paths = [p for p in storage.list_source_paths(conn) if p not in current_rel_paths]
    if orphaned_paths:
        conn.begin()
        for rel_path in orphaned_paths:
            path = Path(rel_path)
            # Prefer the session_id stored alongside the source file (derived from the
            # file's actual content when it was embedded -- see the comment above the
            # embed loop's session_id derivation). The file no longer exists on disk to
            # re-derive it from, so fall back to the filename stem for rows written
            # before this column existed / before they've been re-embedded.
            session_id = storage.get_source_session_id(conn, rel_path) or path.stem
            project = path.parent.name
            print(f"Pruning orphaned source file: {rel_path}")
            storage.delete_chunks_for_source(conn, project, session_id)
            storage.delete_source_file(conn, rel_path)
        conn.commit()
        files_pruned = len(orphaned_paths)

    conn.close()
    print(
        f"Done. {files_processed} file(s) embedded ({chunks_added} chunk(s)), "
        f"{files_skipped} file(s) unchanged/skipped, {files_pruned} file(s) pruned, "
        f"{files_failed} file(s) failed."
    )

    if files_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
