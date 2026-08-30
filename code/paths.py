"""Repo-relative data paths (Phase 1 artifacts)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
RAW_HTML_DIR = DATA_DIR / "raw" / "html"
EXTRACTED_DIR = DATA_DIR / "raw" / "extracted"
CHUNKS_DIR = DATA_DIR / "chunks"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
VECTOR_DB_DIR = DATA_DIR / "vector_db"
