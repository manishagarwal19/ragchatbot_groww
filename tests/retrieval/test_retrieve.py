import unittest

try:
    import chromadb
    from code.retrieval.retrieve import retrieve
    from code.vector_store.store import replace_collection
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False

from code.ingest.allowlist import FUNDS

_INGESTED = "2026-08-30T06:23:21+00:00"

# 2-d toy vectors; cosine distance is 0 for equal vectors, 2.0 for opposites.
LARGE_EXP = [1.0, 0.0]
LARGE_SIP = [0.0, 1.0]
SMALL_EXP = [-1.0, 0.0]
ELSS_SIP = [0.0, -1.0]


def _make_collection(client, vectors):
    col = replace_collection(client)
    ids, docs, metas, embs = [], [], [], []
    for fund_key, chunk_id, vector in vectors:
        ids.append(chunk_id)
        docs.append(f"{fund_key} {chunk_id} text")
        metas.append(
            {
                "chunk_id": chunk_id,
                "url": FUNDS[fund_key]["url"],
                "fund_key": fund_key,
                "ingested_at": _INGESTED,
            }
        )
        embs.append(vector)
    col.add(ids=ids, documents=docs, metadatas=metas, embeddings=embs)
    return col


class _Recorder:
    def __init__(self, vector):
        self.vector = vector
        self.calls = 0

    def __call__(self, question):
        self.calls += 1
        return self.vector


@unittest.skipUnless(_HAS_DEPS, "chromadb not installed")
class RetrieveTests(unittest.TestCase):
    def setUp(self) -> None:
        client = chromadb.EphemeralClient()
        for c in client.list_collections():
            client.delete_collection(c.name)
        self.client = client

    def _collection(self):
        return _make_collection(
            self.client,
            [
                ("large_cap", "large_cap__expense", LARGE_EXP),
                ("large_cap", "large_cap__sip", LARGE_SIP),
                ("small_cap", "small_cap__expense", SMALL_EXP),
                ("elss", "elss__sip", ELSS_SIP),
            ],
        )

    def test_refused_pii_never_embeds(self) -> None:
        rec = _Recorder(LARGE_EXP)
        result = retrieve("my PAN is ABCDE1234F", embed_fn=rec)
        self.assertEqual(result.status, "refused_pii")
        self.assertEqual(rec.calls, 0)

    def test_out_of_corpus_never_embeds(self) -> None:
        rec = _Recorder(LARGE_EXP)
        result = retrieve("Axis small cap?", embed_fn=rec)
        self.assertEqual(result.status, "out_of_corpus")
        self.assertEqual(rec.calls, 0)

    def test_ok_single_fund(self) -> None:
        rec = _Recorder(LARGE_EXP)
        result = retrieve(
            "expense ratio of hdfc large cap", embed_fn=rec, collection=self._collection()
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.named_funds, ["large_cap"])
        self.assertEqual(result.citation_url, FUNDS["large_cap"]["url"])
        self.assertEqual(result.last_updated, _INGESTED)
        self.assertEqual(result.chunks[0].chunk_id, "large_cap__expense")

    def test_ambiguous_no_fund_is_clarification(self) -> None:
        rec = _Recorder(LARGE_EXP)
        result = retrieve("expense ratio?", embed_fn=rec, collection=self._collection())
        self.assertEqual(result.status, "needs_clarification")
        self.assertEqual(result.chunks, [])

    def test_multi_fund_restricted_to_named_funds(self) -> None:
        rec = _Recorder(LARGE_EXP)
        result = retrieve(
            "exit load for hdfc small cap and hdfc large cap",
            embed_fn=rec,
            collection=self._collection(),
        )
        self.assertEqual(result.status, "ok")
        self.assertIn("large_cap", result.named_funds)
        self.assertIn("small_cap", result.named_funds)
        funds = {c.fund_key for c in result.chunks}
        self.assertTrue(funds <= {"large_cap", "small_cap"})
        self.assertNotIn("elss", funds)

    def test_weak_match_is_empty(self) -> None:
        col = _make_collection(self.client, [("large_cap", "large_cap__expense", LARGE_EXP)])
        result = retrieve(
            "gibberish out of scope", embed_fn=lambda q: SMALL_EXP, collection=col
        )
        self.assertEqual(result.status, "empty")
        self.assertIsNone(result.citation_url)


if __name__ == "__main__":
    unittest.main()