"""Phase 1 — load the five allowlisted Groww pages and write document records.

Usage (from repo root):
    python -m code.ingest.load
    python -m code.ingest.load --from-dump
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from code.ingest.allowlist import ALLOWED_URLS, FUNDS, assert_allowed_url, fund_keys
from code.ingest.extract import extract_document
from code.paths import EXTRACTED_DIR, RAW_HTML_DIR, ROOT

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT_SEC = 30


def html_dump_path(fund_key: str) -> Path:
    return RAW_HTML_DIR / f"{fund_key}.html"


def extracted_path(fund_key: str) -> Path:
    return EXTRACTED_DIR / f"{fund_key}.json"


def fetch_html(url: str) -> str:
    assert_allowed_url(url)
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        },
        method="GET",
    )
    with urlopen(request, timeout=TIMEOUT_SEC) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def load_dump(fund_key: str) -> str:
    path = html_dump_path(fund_key)
    if not path.is_file():
        raise FileNotFoundError(f"No HTML dump at {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def save_dump(fund_key: str, html: str) -> None:
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    html_dump_path(fund_key).write_text(html, encoding="utf-8")


def load_html(fund_key: str, from_dump: bool) -> Tuple[str, str]:
    """Return (html, source) where source is 'fetch' or 'dump'."""
    url = FUNDS[fund_key]["url"]
    if from_dump:
        return load_dump(fund_key), "dump"
    try:
        html = fetch_html(url)
        save_dump(fund_key, html)
        return html, "fetch"
    except (HTTPError, URLError, TimeoutError, RuntimeError, OSError) as exc:
        print(f"  fetch failed ({exc}); trying dump", file=sys.stderr)
        return load_dump(fund_key), "dump"


def write_document(doc: dict) -> Path:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    path = extracted_path(doc["fund_key"])
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run_ingest(from_dump: bool) -> List[dict]:
    ingested_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    documents: List[dict] = []
    errors: List[str] = []

    for fund_key in fund_keys():
        url = FUNDS[fund_key]["url"]
        print(f"[{fund_key}] {url}")
        try:
            html, source = load_html(fund_key, from_dump=from_dump)
            print(f"  loaded via {source} ({len(html)} chars)")
            doc = extract_document(html, fund_key, ingested_at)
            if doc["url"] not in ALLOWED_URLS:
                raise ValueError("extracted URL escaped allowlist")
            path = write_document(doc)
            print(
                f"  wrote {path.relative_to(ROOT)} "
                f"({len(doc['text'])} chars, {len(doc['factsheet_links'])} factsheet links)"
            )
            documents.append(doc)
        except Exception as exc:  # noqa: BLE001 — fail the fund, then fail ingest
            errors.append(f"{fund_key}: {exc}")
            print(f"  ERROR: {exc}", file=sys.stderr)

    if len(documents) != len(FUNDS):
        detail = "; ".join(errors) if errors else "unknown"
        raise SystemExit(f"Ingest failed: expected {len(FUNDS)} documents, got {len(documents)}. {detail}")

    manifest = {
        "ingested_at": ingested_at,
        "documents": [
            {
                "fund_key": d["fund_key"],
                "fund_name": d["fund_name"],
                "url": d["url"],
                "path": str(extracted_path(d["fund_key"]).relative_to(ROOT)),
            }
            for d in documents
        ],
    }
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = EXTRACTED_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: {len(documents)} documents. Last updated from sources: {ingested_at}")
    print(f"Manifest: {manifest_path.relative_to(ROOT)}")
    return documents


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Phase 1 data loading (5 Groww URLs only).")
    parser.add_argument(
        "--from-dump",
        action="store_true",
        help="Read data/raw/html/{fund_key}.html only; do not fetch.",
    )
    args = parser.parse_args(argv)
    run_ingest(from_dump=args.from_dump)


if __name__ == "__main__":
    main()
