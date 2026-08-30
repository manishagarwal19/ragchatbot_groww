"""Phase 4 — local ChromaDB accessors shared with retrieval (Phase 5)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from code.paths import VECTOR_DB_DIR

COLLECTION_NAME = "hdfc_faq"
_DISTANCE = "cosine"


def get_client(path: Optional[Path] = None):
    from chromadb import PersistentClient

    return PersistentClient(path=str(path or VECTOR_DB_DIR))


def collection_exists(client, name: str = COLLECTION_NAME) -> bool:
    return any(c.name == name for c in client.list_collections())


def replace_collection(client=None, name: str = COLLECTION_NAME):
    """Drop and recreate the collection so retrieval never mixes old/new pages."""
    client = client if client is not None else get_client()
    if collection_exists(client, name):
        client.delete_collection(name)
    return client.create_collection(name, metadata={"hnsw:space": _DISTANCE})


def get_collection(client=None, name: str = COLLECTION_NAME):
    client = client if client is not None else get_client()
    return client.get_collection(name)