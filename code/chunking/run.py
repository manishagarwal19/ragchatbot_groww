"""Phase 2 — chunk Phase 1 documents per source URL.

Usage (from repo root):
    python -m code.chunking.run
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List

from code.chunking.split import chunk_document
from code.ingest.allowlist import ALLOWED_URLS, FUNDS, fund_keys
from code.paths import CHUNKS_DIR, EXTRACTED_DIR, ROOT


def _load_document(fund_key: str) -> Dict:
    path = EXTRACTED_DIR / f"{fund_key}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Phase 1 document missing: {path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("fund_key") != fund_key:
        raise ValueError(f"{path} fund_key mismatch")
    if doc.get("url") not in ALLOWED_URLS:
        raise ValueError(f"{path} URL is not on the allowlist")
    return doc


def run_chunking() -> List[Dict[str, str]]:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    all_chunks: List[Dict[str, str]] = []
    errors: List[str] = []
    per_fund: Dict[str, int] = {}

    for fund_key in fund_keys():
        print(f"[{fund_key}]")
        try:
            doc = _load_document(fund_key)
            chunks = chunk_document(doc)
            for chunk in chunks:
                if chunk["url"] != FUNDS[fund_key]["url"]:
                    raise ValueError("chunk URL mixed across funds")
                if chunk["fund_key"] != fund_key:
                    raise ValueError("chunk fund_key mixed across funds")
            out_path = CHUNKS_DIR / f"{fund_key}.jsonl"
            with out_path.open("w", encoding="utf-8") as handle:
                for chunk in chunks:
                    handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            per_fund[fund_key] = len(chunks)
            all_chunks.extend(chunks)
            print(f"  wrote {out_path.relative_to(ROOT)} ({len(chunks)} chunks)")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fund_key}: {exc}")
            print(f"  ERROR: {exc}", file=sys.stderr)

    if len(per_fund) != len(FUNDS):
        detail = "; ".join(errors) if errors else "unknown"
        raise SystemExit(
            f"Chunking failed: expected chunks for {len(FUNDS)} pages, "
            f"got {len(per_fund)}. {detail}"
        )

    all_path = CHUNKS_DIR / "all.json"
    all_path.write_text(json.dumps(all_chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "chunk_count": len(all_chunks),
        "funds": {key: per_fund[key] for key in fund_keys()},
        "path": str(all_path.relative_to(ROOT)),
    }
    manifest_path = CHUNKS_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: {len(all_chunks)} chunks across {len(FUNDS)} pages")
    print(f"Manifest: {manifest_path.relative_to(ROOT)}")
    return all_chunks


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Phase 2 chunking (per source URL).")
    parser.parse_args(argv)
    run_chunking()


if __name__ == "__main__":
    main()
