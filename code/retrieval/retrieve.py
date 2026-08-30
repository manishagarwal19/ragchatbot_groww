"""Phase 5 — retrieval logic (search only, feeds the generator).

Refusals are applied before retrieve (guard). Empty retrieval is a first-class
outcome. Output: top chunk texts + exactly one citation_url + last_updated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from code.embedding.embed import embed_query
from code.guard.guard import classify_question
from code.ingest.allowlist import FUNDS
from code.vector_store.store import get_collection

# Cosine distance above this is not a useful match (1 - cos_sim).
_WEAK_DISTANCE = 0.80

_REFUSED = frozenset({"refused_pii", "refused_advice", "refused_returns", "out_of_corpus"})


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    url: str
    fund_key: str
    ingested_at: str
    distance: float


@dataclass
class RetrievalResult:
    status: str  # ok | empty | needs_clarification | empty_question | refused_*
    reason: str = ""
    named_funds: List[str] = field(default_factory=list)
    chunks: List[RetrievedChunk] = field(default_factory=list)
    citation_url: Optional[str] = None
    last_updated: Optional[str] = None


def _last_updated_for(fund_key: str, collection=None) -> Optional[str]:
    try:
        collection = collection if collection is not None else get_collection()
    except Exception:
        return None
    res = collection.get(where={"fund_key": fund_key}, include=["metadatas"], limit=1)
    for md in res.get("metadatas") or []:
        return md.get("ingested_at")
    return None


def retrieve(
    query: str,
    *,
    top_k: int = 5,
    embed_fn=None,
    collection=None,
) -> RetrievalResult:
    guard = classify_question(query)
    if guard.status == "empty":
        return RetrievalResult(status="empty_question", reason="empty question")
    if guard.status in _REFUSED:
        return RetrievalResult(
            status=guard.status,
            reason=guard.reason,
            named_funds=guard.named_funds,
        )

    named = guard.named_funds
    embedding = (embed_fn or embed_query)(query)
    collection = collection if collection is not None else get_collection()
    kwargs = {
        "query_embeddings": [embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if named:  # restrict to named fund(s); never mix funds from outside the ask
        kwargs["where"] = {"fund_key": {"$in": named}}
    res = collection.query(**kwargs)

    ids = res.get("ids")[0]
    if not ids:
        return RetrievalResult(status="empty", reason="no chunks returned", named_funds=named)

    chunks = [
        RetrievedChunk(
            chunk_id=cid,
            text=doc,
            url=md["url"],
            fund_key=md["fund_key"],
            ingested_at=md["ingested_at"],
            distance=float(dist),
        )
        for cid, doc, md, dist in zip(
            ids, res["documents"][0], res["metadatas"][0], res["distances"][0]
        )
    ]

    best = chunks[0]
    if best.distance > _WEAK_DISTANCE:
        citation_url: Optional[str] = None
        last_updated: Optional[str] = None
        if len(named) == 1:
            citation_url = FUNDS[named[0]]["url"]
            last_updated = _last_updated_for(named[0], collection)
        return RetrievalResult(
            status="empty",
            reason="no relevant chunk above threshold",
            named_funds=named,
            chunks=chunks,
            citation_url=citation_url,
            last_updated=last_updated,
        )

    if not named:
        funds_present = {c.fund_key for c in chunks}
        if len(funds_present) > 1:
            return RetrievalResult(
                status="needs_clarification",
                reason="question names no fund and top chunks span multiple funds",
                named_funds=named,
            )

    return RetrievalResult(
        status="ok",
        named_funds=named,
        chunks=chunks,
        citation_url=best.url,
        last_updated=best.ingested_at,
    )