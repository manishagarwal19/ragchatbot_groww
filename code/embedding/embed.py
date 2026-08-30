"""Phase 3 — map chunk text (and later the user question) into one vector space.

Model (PRD only): Hugging Face `sentence-transformers/all-MiniLM-L6-v2`.
Loaded once per process; the online query path (Phase 5) reuses the same model.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
from numpy.typing import NDArray

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model = None


def load_model():
    """Load the embedding model once; subsequent calls reuse the instance."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def model_dimension(model) -> int:
    return int(model.get_sentence_embedding_dimension())


def embed_texts(texts: Sequence[str], model=None) -> NDArray[np.float32]:
    """Return one float32 row vector per text, same dimensionality as the model."""
    model = model if model is not None else load_model()
    if not texts:
        return np.zeros((0, model_dimension(model)), dtype=np.float32)
    vectors = model.encode(list(texts), convert_to_numpy=True, show_progress_bar=False)
    arr = np.asarray(vectors, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[1] != model_dimension(model):
        raise ValueError(
            f"Embedding dimension mismatch: got {arr.shape}, "
            f"expected (n, {model_dimension(model)})"
        )
    return arr


def embed_query(question: str, model=None) -> NDArray[np.float32]:
    """Embed a single user question (Phase 5 online reuse)."""
    return embed_texts([question], model=model)[0]