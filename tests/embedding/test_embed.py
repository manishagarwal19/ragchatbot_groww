import unittest

try:
    import numpy as np
    from code.embedding.embed import MODEL_NAME, embed_query, embed_texts, model_dimension
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False


class _FakeModel:
    def __init__(self, dim: int = 4) -> None:
        self._dim = dim

    def encode(self, texts, convert_to_numpy=False, show_progress_bar=False):
        arr = np.zeros((len(list(texts)), self._dim), dtype=np.float32)
        for i, text in enumerate(list(texts)):
            arr[i] = [float(len(text))] * self._dim
        return arr

    def get_sentence_embedding_dimension(self) -> int:
        return self._dim


@unittest.skipUnless(_HAS_DEPS, "numpy/sentence-transformers not installed")
class EmbedTests(unittest.TestCase):
    def test_embed_texts_rows_and_dtype(self) -> None:
        emb = embed_texts(["a", "bb", "ccc"], model=_FakeModel())
        self.assertEqual(emb.shape, (3, 4))
        self.assertEqual(emb.dtype, np.float32)
        self.assertTrue(np.all(emb > 0))

    def test_embed_query_returns_one_1d_vector(self) -> None:
        q = embed_query("expense ratio", model=_FakeModel())
        self.assertEqual(q.shape, (4,))
        self.assertEqual(q.ndim, 1)

    def _mismatched(self):
        # encode() is inconsistent with get_sentence_embedding_dimension().
        f = _FakeModel(dim=4)
        f.encode = lambda texts, convert_to_numpy=False, show_progress_bar=False: np.zeros(
            (len(list(texts)), 8), dtype=np.float32
        )
        return f

    def test_dimension_mismatch_raises(self) -> None:
        with self.assertRaises(ValueError):
            embed_texts(["x"], model=self._mismatched())

    def test_empty_input_produces_empty_rows(self) -> None:
        emb = embed_texts([], model=_FakeModel())
        self.assertEqual(emb.shape, (0, 4))

    def test_reported_model_name(self) -> None:
        self.assertEqual(MODEL_NAME, "sentence-transformers/all-MiniLM-L6-v2")
        self.assertEqual(model_dimension(_FakeModel(384)), 384)


if __name__ == "__main__":
    unittest.main()