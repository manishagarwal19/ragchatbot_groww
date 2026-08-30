import unittest

try:
    import chromadb
    from code.vector_store.store import (
        COLLECTION_NAME,
        collection_exists,
        get_collection,
        replace_collection,
    )
    _HAS_CHROMADB = True
except ImportError:
    _HAS_CHROMADB = False


@unittest.skipUnless(_HAS_CHROMADB, "chromadb not installed")
class VectorStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        client = chromadb.EphemeralClient()
        for c in client.list_collections():
            client.delete_collection(c.name)
        self.client = client

    def test_replace_collection_starts_empty(self) -> None:
        first = replace_collection(self.client)
        first.add(
            ids=["a"],
            embeddings=[[1.0, 0.0]],
            documents=["old"],
            metadatas=[{"url": "u", "fund_key": "k", "chunk_id": "a", "ingested_at": "t"}],
        )
        self.assertEqual(first.count(), 1)

        second = replace_collection(self.client)
        self.assertEqual(second.count(), 0)

    def test_collection_exists(self) -> None:
        self.assertFalse(collection_exists(self.client))
        replace_collection(self.client)
        self.assertTrue(collection_exists(self.client))
        self.assertEqual(get_collection(self.client).name, COLLECTION_NAME)

    def test_query_returns_nearest(self) -> None:
        col = replace_collection(self.client)
        col.add(
            ids=["a", "b"],
            embeddings=[[1.0, 0.0], [0.0, 1.0]],
            documents=["expense ratio text", "lock-in text"],
            metadatas=[
                {"url": "u1", "fund_key": "large_cap", "chunk_id": "a", "ingested_at": "t"},
                {"url": "u2", "fund_key": "elss", "chunk_id": "b", "ingested_at": "t"},
            ],
        )
        res = col.query(query_embeddings=[[1.0, 0.0]], n_results=1)
        self.assertEqual(res["ids"][0], ["a"])
        self.assertEqual(res["documents"][0], ["expense ratio text"])


if __name__ == "__main__":
    unittest.main()