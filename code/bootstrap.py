"""Build-or-verify the retrieval corpus so the app boots from a fresh clone
(e.g. Render cold start) or after a partial run.

Each phase is skipped when its artifacts already exist and are consistent;
missing or stale phases run in dependency order (chunks -> embeddings ->
vector store). The pure decision helpers take explicit directories so they
can be unit-tested without numpy/chromadb; the heavy phase runners and
numpy/chromadb are imported lazily inside ensure_corpus.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

from code.ingest.allowlist import fund_keys
from code.paths import CHUNKS_DIR, EMBEDDINGS_DIR, EXTRACTED_DIR


def missing_extracted(directory: Path, keys: Sequence[str]) -> List[str]:
    return _missing_nonempty(directory, keys, ".json")


def missing_chunks(directory: Path, keys: Sequence[str]) -> List[str]:
    return _missing_nonempty(directory, keys, ".jsonl")


def missing_embeddings(directory: Path, keys: Sequence[str]) -> List[str]:
    return _missing_nonempty(directory, keys, ".npy")


def _missing_nonempty(directory: Path, keys: Sequence[str], suffix: str) -> List[str]:
    missing: List[str] = []
    for key in keys:
        path = directory / f"{key}{suffix}"
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(key)
    return missing


def chunk_count(directory: Path, keys: Sequence[str]) -> int:
    total = 0
    for key in keys:
        path = directory / f"{key}.jsonl"
        if path.is_file():
            with path.open(encoding="utf-8") as handle:
                total += sum(1 for _ in handle)
    return total


def embedding_count(directory: Path, keys: Sequence[str]) -> int:
    import numpy as np

    total = 0
    for key in keys:
        path = directory / f"{key}.npy"
        if path.is_file():
            total += int(np.load(path).shape[0])
    return total


def _log(message: str) -> None:
    print(f"[bootstrap] {message}", flush=True)


def ensure_corpus() -> None:
    """Make chunks, embeddings and the Chroma collection present and current."""
    keys = list(fund_keys())

    missing = missing_extracted(EXTRACTED_DIR, keys)
    if missing:
        raise RuntimeError(
            "Phase 1 documents missing for: " + ", ".join(missing)
            + ". Run `python -m code.ingest.load` first."
        )

    if missing_chunks(CHUNKS_DIR, keys):
        from code.chunking.run import run_chunking

        _log("building chunk corpus (Phase 2) ...")
        run_chunking()

    expected = chunk_count(CHUNKS_DIR, keys)
    if expected == 0:
        raise RuntimeError("Chunk corpus is empty after Phase 2")

    if missing_embeddings(EMBEDDINGS_DIR, keys) or embedding_count(EMBEDDINGS_DIR, keys) != expected:
        from code.embedding.run import run_embedding

        _log("embedding corpus (Phase 3; downloads the model on first boot) ...")
        run_embedding()

    from code.vector_store.store import COLLECTION_NAME, get_collection
    from code.vector_store.run import run_vector_store

    try:
        ready = get_collection().count() == expected
    except Exception:  # noqa: BLE001 - collection not created yet
        ready = False
    if not ready:
        _log(f"building vector store '{COLLECTION_NAME}' (Phase 4) ...")
        run_vector_store()