"""Phase 3 — embed Phase 2 chunks once per ingest job.

Usage (from repo root):
    python -m code.embedding.run
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np

from code.embedding.embed import MODEL_NAME, embed_texts, load_model, model_dimension
from code.ingest.allowlist import FUNDS, fund_keys
from code.ingest.extract import redact_pii
from code.paths import CHUNKS_DIR, EMBEDDINGS_DIR, ROOT


def _load_chunk_rows() -> Dict[str, List[Dict]]:
    rows: Dict[str, List[Dict]] = {}
    for key in fund_keys():
        path = CHUNKS_DIR / f"{key}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"Phase 2 chunks missing: {path}")
        rows[key] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if not rows[key]:
            raise ValueError(f"No chunks in {path}")
    return rows


def _assert_no_pii(rows: Dict[str, List[Dict]]) -> None:
    # Corpus only; refuse to embed anything that still looks like PII.
    for key, chunks in rows.items():
        for chunk in chunks:
            text = chunk.get("text") or ""
            if redact_pii(text) != text:
                raise ValueError(f"Refusing to embed PII-like text in {key} {chunk['chunk_id']}")


def run_embedding() -> Dict[str, str]:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

    rows = _load_chunk_rows()
    _assert_no_pii(rows)

    model = load_model()
    dim = model_dimension(model)

    funds: Dict[str, Dict[str, object]] = {}
    vectors: List[np.ndarray] = []
    for key in fund_keys():
        texts = [chunk["text"] for chunk in rows[key]]
        emb = embed_texts(texts, model=model)
        npy_path = EMBEDDINGS_DIR / f"{key}.npy"
        np.save(npy_path, emb)
        vectors.append(emb)
        funds[key] = {
            "chunks": len(rows[key]),
            "jsonl": str((CHUNKS_DIR / f"{key}.jsonl").relative_to(ROOT)),
            "npy": str(npy_path.relative_to(ROOT)),
        }
        print(f"[{key}] wrote {npy_path.relative_to(ROOT)} "
              f"({emb.shape[0]} x {emb.shape[1]})")

    all_vec = np.concatenate(vectors, axis=0)
    all_npy = EMBEDDINGS_DIR / "all.npy"
    np.save(all_npy, all_vec)

    manifest = {
        "model": MODEL_NAME,
        "dimension": dim,
        "chunk_count": int(all_vec.shape[0]),
        "funds": funds,
        "all_npy": str(all_npy.relative_to(ROOT)),
        "chunks_path": str((CHUNKS_DIR / "all.json").relative_to(ROOT)),
        "embedded_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = EMBEDDINGS_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print(f"OK: {manifest['chunk_count']} vectors, dim {dim}, model {MODEL_NAME}")
    print(f"Manifest: {manifest_path.relative_to(ROOT)}")
    return {key: str(meta["npy"]) for key, meta in funds.items()}


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Phase 3 embedding (all-MiniLM-L6-v2).")
    parser.parse_args(argv)
    run_embedding()


if __name__ == "__main__":
    main()