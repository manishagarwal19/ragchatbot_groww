"""Phase 5 — retrieval CLI. Prints the retrieval result for one or more questions.

Usage (from repo root):
    python -m code.retrieval.run "What is the expense ratio of HDFC Large Cap Fund Direct Growth?"
    python -m code.retrieval.run --q1 --q2 ...   (or read from stdin, one per line)
"""

from __future__ import annotations

import argparse
import sys
from typing import List

from code.retrieval.retrieve import RetrievalResult, retrieve

_REFUSED_LABEL = {
    "refused_pii": "Refused: PII detected (not stored, not embedded)",
    "refused_advice": "Refused: advice/portfolio question (facts-only assistant)",
    "refused_returns": "Refused: returns computation is out of scope",
    "out_of_corpus": "Out of corpus: I can only answer from the five listed HDFC fund pages",
}


def _print_result(question: str, result: RetrievalResult) -> None:
    print(f"Q: {question}")
    print(f"  status      : {result.status}")
    print(f"  named funds : {result.named_funds}")
    print(f"  reason      : {result.reason or '-'}")
    if result.status in _REFUSED_LABEL:
        print(f"  -> {_REFUSED_LABEL[result.status]}")
    if result.status == "ok":
        print(f"  citation    : {result.citation_url}")
        print(f"  last updated: {result.last_updated}")
        for i, chunk in enumerate(result.chunks, start=1):
            text = " ".join(chunk.text.split())[:160]
            print(f"  [{i}] {chunk.chunk_id} dist={chunk.distance:.3f} "
                  f"fund={chunk.fund_key}\n      {text}")
    elif result.status == "empty" and result.citation_url:
        print(f"  citation    : {result.citation_url}")
        print(f"  last updated: {result.last_updated}")
    print()


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Phase 5 retrieval test CLI.")
    parser.add_argument("questions", nargs="*", help="one or more questions to test")
    parser.add_argument("--top-k", type=int, default=5, help="chunks per query (default 5)")
    args = parser.parse_args(argv)

    questions = list(args.questions)
    if not questions and not sys.stdin.isatty():
        questions = [line.strip() for line in sys.stdin if line.strip()]

    if not questions:
        parser.print_help()
        return

    for question in questions:
        _print_result(question, retrieve(question, top_k=args.top_k))


if __name__ == "__main__":
    main()