"""Phase 4 — persist chunk vectors + metadata in local ChromaDB.

Usage (from repo root):
    python -m code.vector_store.run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np

from code.ingest.allowlist import ALLOWED_URLS, fund_keys
from code.paths import CHUNKS_DIR, EMBEDDINGS_DIR, ROOT
from code.vector_store.store import COLLECTION_NAME, get_client, replace_collection


def _load_chunk_rows() -> Dict[str, List[Dict]]:
    rows: Dict[str, List[Dict]] = {}
    for key in fund_keys():
        path = CHUNKS_DIR / f"{key}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"Phase 2 chunks missing: {path}")
        rows[key] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return rows


def _load_vectors() -> Dict[str, np.ndarray]:
    vectors: Dict[str, np.ndarray] = {}
    for key in fund_keys():
        path = EMBEDDINGS_DIR / f"{key}.npy"
        if not path.is_file():
            raise FileNotFoundError(f"Phase 3 embeddings missing: {path}")
        vectors[key] = np.load(path)
    return vectors


def run_vector_store() -> int:
    rows = _load_chunk_rows()
    vectors = _load_vectors()
    for key in fund_keys():
        if vectors[key].shape[0] != len(rows[key]):
            raise ValueError(
                f"{key}: {len(rows[key])} chunks but {vectors[key].shape[0]} vectors"
            )

    client = get_client()
    collection = replace_collection(client)
    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, str]] = []
    embeddings: List[np.ndarray] = []
    per_fund: Dict[str, int] = {}
    for key in fund_keys():
        for chunk, vec in zip(rows[key], vectors[key]):
            ids.append(chunk["chunk_id"])
            documents.append(chunk["text"])
            metadatas.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "url": chunk["url"],
                    "fund_key": chunk["fund_key"],
                    "ingested_at": chunk["ingested_at"],
                }
            )
            embeddings.append(vec)
        per_fund[key] = len(rows[key])

    collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    count = collection.count()
    if count != len(ids):
        raise ValueError(f"Expected {len(ids)} items in {COLLECTION_NAME}, got {count}")

    stored = collection.get(include=["metadatas"])
    stored_urls = {item["url"] for item in stored["metadatas"]}
    if stored_urls != set(ALLOWED_URLS):
        raise ValueError(
            f"Vector store lacks all five pages: {set(ALLOWED_URLS) - stored_urls}"
        )

    manifest = {
        "collection": COLLECTION_NAME,
        "distance": "cosine",
        "chunk_count": count,
        "funds": per_fund,
        "chroma_path": "data/vector_db",
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = ROOT / "data" / "vector_db" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print(f"OK: {count} items in collection '{COLLECTION_NAME}' ({len(stored_urls)} URLs)")
    print(f"Manifest: {manifest_path.relative_to(ROOT)}")
    return count


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Phase 4 vector store (local ChromaDB).")
    parser.parse_args(argv)
    run_vector_store()


if __name__ == "__main__":
    main()