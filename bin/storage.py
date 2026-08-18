"""DuckDB metadata + vector store for the embedding index.

Chunk metadata and embedding vectors live together on one row (a FLOAT[384]
array column) -- no separate vectors file, no vector_row join.
"""

from pathlib import Path

import duckdb
import numpy as np

EMBED_DIM = 384

SCHEMA_STATEMENTS = [
    f"""
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id    TEXT PRIMARY KEY,
        session_id  TEXT NOT NULL,
        project     TEXT NOT NULL,
        role        TEXT NOT NULL CHECK (role IN ('user','assistant')),
        timestamp   TEXT NOT NULL,
        text        TEXT NOT NULL,
        char_len    INTEGER NOT NULL,
        embedding   FLOAT[{EMBED_DIM}] NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chunks_session ON chunks(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_project ON chunks(project)",
    """
    CREATE TABLE IF NOT EXISTS source_files (
        path        TEXT PRIMARY KEY,
        mtime       DOUBLE NOT NULL,
        chunk_count INTEGER NOT NULL,
        embedded_at TEXT NOT NULL
    )
    """,
]


def open_db(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    for stmt in SCHEMA_STATEMENTS:
        conn.execute(stmt)
    return conn


def get_source_mtime(conn: duckdb.DuckDBPyConnection, rel_path: str) -> float | None:
    row = conn.execute("SELECT mtime FROM source_files WHERE path = ?", [rel_path]).fetchone()
    return row[0] if row else None


def upsert_source_file(
    conn: duckdb.DuckDBPyConnection, rel_path: str, mtime: float, chunk_count: int, embedded_at: str
) -> None:
    conn.execute(
        """INSERT INTO source_files (path, mtime, chunk_count, embedded_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT (path) DO UPDATE SET
               mtime = excluded.mtime,
               chunk_count = excluded.chunk_count,
               embedded_at = excluded.embedded_at""",
        [rel_path, mtime, chunk_count, embedded_at],
    )


def delete_chunks_for_session(conn: duckdb.DuckDBPyConnection, session_id: str) -> None:
    conn.execute("DELETE FROM chunks WHERE session_id = ?", [session_id])


def list_source_paths(conn: duckdb.DuckDBPyConnection) -> list[str]:
    return [row[0] for row in conn.execute("SELECT path FROM source_files").fetchall()]


def delete_source_file(conn: duckdb.DuckDBPyConnection, rel_path: str) -> None:
    conn.execute("DELETE FROM source_files WHERE path = ?", [rel_path])


def insert_chunk(conn: duckdb.DuckDBPyConnection, chunk, vector: np.ndarray) -> None:
    conn.execute(
        """INSERT INTO chunks
               (chunk_id, session_id, project, role, timestamp, text, char_len, embedding)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            chunk.chunk_id, chunk.session_id, chunk.project, chunk.role,
            chunk.timestamp, chunk.text, chunk.char_len, vector.tolist(),
        ],
    )


def fetch_all_chunks(conn: duckdb.DuckDBPyConnection):
    return conn.execute(
        "SELECT chunk_id, session_id, project, role, timestamp, text FROM chunks"
    ).fetchall()


def search(conn: duckdb.DuckDBPyConnection, query_vector: np.ndarray, k: int):
    return conn.execute(
        f"""SELECT chunk_id, session_id, project, role, timestamp, text,
                   array_cosine_similarity(embedding, ?::FLOAT[{EMBED_DIM}]) AS score
            FROM chunks
            ORDER BY score DESC
            LIMIT ?""",
        [query_vector.tolist(), k],
    ).fetchall()
