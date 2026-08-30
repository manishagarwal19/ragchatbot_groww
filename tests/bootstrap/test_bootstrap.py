import tempfile
import unittest
from pathlib import Path

from code.bootstrap import (
    chunk_count,
    missing_chunks,
    missing_embeddings,
    missing_extracted,
)

KEYS = ("large_cap", "elss")


class BootstrapDecisionTests(unittest.TestCase):
    def _tree(self) -> Path:
        tmp = tempfile.mkdtemp()
        (Path(tmp) / "extracted").mkdir()
        (Path(tmp) / "chunks").mkdir()
        (Path(tmp) / "embeddings").mkdir()
        return Path(tmp)

    def test_missing_extracted_reports_empty_funds(self) -> None:
        root = self._tree()
        self.assertEqual(missing_extracted(root / "extracted", KEYS), list(KEYS))

    def test_empty_file_counts_as_missing(self) -> None:
        root = self._tree()
        empty = root / "extracted" / "elss.json"
        empty.touch()
        self.assertEqual(missing_extracted(root / "extracted", KEYS), ["large_cap", "elss"])
        (root / "extracted" / "large_cap.json").write_text("{}", encoding="utf-8")
        self.assertEqual(missing_extracted(root / "extracted", KEYS), ["elss"])

    def test_chunks_and_embeddings_presence(self) -> None:
        root = self._tree()
        (root / "chunks" / "large_cap.jsonl").write_text('{"a": 1}\n', encoding="utf-8")
        (root / "embeddings" / "elss.npy").write_bytes(b"fake")
        self.assertEqual(missing_chunks(root / "chunks", KEYS), ["elss"])
        self.assertEqual(missing_embeddings(root / "embeddings", KEYS), ["large_cap"])

    def test_chunk_count_sums_lines(self) -> None:
        root = self._tree()
        for key, n in (("large_cap", 3), ("elss", 2)):
            with (root / "chunks" / f"{key}.jsonl").open("w", encoding="utf-8") as handle:
                for _ in range(n):
                    handle.write("{}\n")
        self.assertEqual(chunk_count(root / "chunks", KEYS), 5)
        self.assertEqual(chunk_count(root / "chunks", ("absent",)), 0)


if __name__ == "__main__":
    unittest.main()