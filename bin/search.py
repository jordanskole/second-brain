#!/usr/bin/env python3
"""Semantic search over the embedded session index."""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import storage

REPO_DIR = Path(__file__).resolve().parent.parent
DB_PATH = REPO_DIR / "embeddings" / "index.duckdb"
MODEL_NAME = "mlx-community/all-MiniLM-L6-v2-4bit"


def embed_query(model, tokenizer, query: str) -> np.ndarray:
    inputs = tokenizer.batch_encode_plus(
        [query], return_tensors="mlx", padding=True, truncation=True, max_length=512
    )
    outputs = model(inputs["input_ids"], attention_mask=inputs["attention_mask"])
    vec = np.asarray(outputs.text_embeds, dtype=np.float32)[0]
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic search over archived Claude Code sessions.")
    parser.add_argument("query", help="search query text")
    parser.add_argument("--k", type=int, default=10, help="number of results to return (default 10)")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print("No index found. Run bin/build_index.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading model {MODEL_NAME} ...", file=sys.stderr)
    from mlx_embeddings.utils import load

    model, tokenizer = load(MODEL_NAME)
    query_vec = embed_query(model, tokenizer, args.query)

    conn = storage.open_db(DB_PATH)
    results = storage.search(conn, query_vec, args.k)
    conn.close()

    if not results:
        print("Index is empty. Run bin/build_index.py first.")
        return

    for chunk_id, session_id, project, role, timestamp, text, score in results:
        snippet = text[:200].replace("\n", " ")
        if len(text) > 200:
            snippet += "..."
        print(f"{score:.3f}  [{project}] {role}  {timestamp}  session={session_id[:8]}")
        print(f"    {snippet}")
        print()


if __name__ == "__main__":
    main()
