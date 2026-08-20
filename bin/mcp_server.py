#!/usr/bin/env python3
"""MCP server exposing semantic search over archived Claude Code session transcripts.

Model and DB connection are loaded lazily on first tool call, not at import
time, so the server can start and respond to capability negotiation instantly
even before the (multi-second) model load has happened.
"""

import os
import sys
from pathlib import Path

from mcp.server import MCPServer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import storage

DATA_DIR = Path(os.environ.get("SECOND_BRAIN_DATA_DIR", str(Path.home() / "second-brain-data")))
DB_PATH = DATA_DIR / "embeddings" / "index.duckdb"
MODEL_NAME = "mlx-community/all-MiniLM-L6-v2-4bit"
MAX_TEXT_CHARS = 1500

mcp = MCPServer(
    "second-brain-search",
    instructions=(
        "Semantic search over the user's archived Claude Code session transcripts "
        "(past conversations with Claude, across all their projects). Use "
        "search_conversations to find prior discussions, decisions, or context "
        "by meaning rather than exact keywords."
    ),
)

_model = None
_tokenizer = None


def _ensure_loaded():
    global _model, _tokenizer
    if _model is None:
        from mlx_embeddings.utils import load

        _model, _tokenizer = load(MODEL_NAME)


def _embed_query(query: str):
    import numpy as np

    inputs = _tokenizer.batch_encode_plus(
        [query], return_tensors="mlx", padding=True, truncation=True, max_length=512
    )
    outputs = _model(inputs["input_ids"], attention_mask=inputs["attention_mask"])
    vec = np.asarray(outputs.text_embeds, dtype=np.float32)[0]
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


@mcp.tool()
def search_conversations(query: str, k: int = 10) -> list[dict]:
    """Semantically search archived Claude Code session transcripts.

    Returns the top-k most relevant past conversation turns (human or
    assistant) across all archived projects, ranked by similarity to the
    query. Use this to recall prior discussions, decisions, or context that
    may not be in the current session.
    """
    if not DB_PATH.exists():
        return []

    _ensure_loaded()
    query_vec = _embed_query(query)
    conn = storage.open_db(DB_PATH)
    try:
        results = storage.search(conn, query_vec, k)
    finally:
        conn.close()

    output = []
    for chunk_id, session_id, project, role, timestamp, text, score in results:
        truncated = len(text) > MAX_TEXT_CHARS
        output.append(
            {
                "score": round(float(score), 3),
                "project": project,
                "role": role,
                "timestamp": timestamp,
                "session_id": session_id,
                "text": text[:MAX_TEXT_CHARS] + ("...[truncated]" if truncated else ""),
            }
        )
    return output


if __name__ == "__main__":
    mcp.run()
