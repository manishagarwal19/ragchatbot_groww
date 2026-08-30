import unittest

from code.chunking.split import chunk_document
from code.ingest.allowlist import FUNDS

LARGE = FUNDS["large_cap"]
ELSS = FUNDS["elss"]


def _doc(fund_key: str, extra_visible: str = "") -> dict:
    meta = FUNDS[fund_key]
    facts = """Facts extracted from the fund page (__NEXT_DATA__):
Scheme name on page: Test Scheme
Category: Equity
Expense ratio: 1.02
Exit load: Exit load of 1% if redeemed within 1 year
Minimum SIP: 100
Lock-in: 3 year(s)
Benchmark: NIFTY 100 TRI
Benchmark name: NIFTY 100 Total Return Index
Riskometer: Very High
Tax impact (as stated on page): LTCG and STCG as stated on page.
"""
    visible = f"""Visible page text:
Stocks
Intraday
IPO
{meta['fund_name']}
Expense ratio 1.02%
Min. for SIP ₹100
{extra_visible}
Vaishnavi Tech Park, South Tower
Download the App
GROWW
"""
    return {
        "url": meta["url"],
        "fund_key": fund_key,
        "fund_name": meta["fund_name"],
        "text": f"Fund: {meta['fund_name']}\nSource URL: {meta['url']}\n\n{facts}\n{visible}",
        "ingested_at": "2026-08-30T06:23:21+00:00",
        "factsheet_links": ["https://www.hdfcfund.com/factsheet.pdf"],
    }


class ChunkingTests(unittest.TestCase):
    def test_never_merges_two_funds(self) -> None:
        a = chunk_document(_doc("large_cap"))
        b = chunk_document(_doc("elss"))
        self.assertTrue(all(c["fund_key"] == "large_cap" and c["url"] == LARGE["url"] for c in a))
        self.assertTrue(all(c["fund_key"] == "elss" and c["url"] == ELSS["url"] for c in b))
        self.assertTrue({c["chunk_id"] for c in a}.isdisjoint({c["chunk_id"] for c in b}))

    def test_faq_topics_are_separate_chunks(self) -> None:
        chunks = {c["chunk_id"]: c["text"] for c in chunk_document(_doc("elss"))}
        self.assertIn("elss__expense", chunks)
        self.assertIn("elss__sip", chunks)
        self.assertIn("elss__lock_in", chunks)
        self.assertIn("elss__exit_load", chunks)
        self.assertIn("elss__riskometer", chunks)
        self.assertIn("elss__benchmark", chunks)
        self.assertIn("Expense ratio: 1.02", chunks["elss__expense"])
        self.assertNotIn("Minimum SIP:", chunks["elss__expense"])
        self.assertIn("Minimum SIP: 100", chunks["elss__sip"])
        self.assertIn("Lock-in: 3 year(s)", chunks["elss__lock_in"])

    def test_chunk_is_understandable_alone(self) -> None:
        expense = next(c for c in chunk_document(_doc("large_cap")) if c["chunk_id"].endswith("__expense"))
        self.assertIn(LARGE["fund_name"], expense["text"])
        self.assertIn(LARGE["url"], expense["text"])

    def test_drops_boilerplate_and_keeps_capital_gains_if_present(self) -> None:
        chunks = chunk_document(
            _doc("large_cap", extra_visible="How to download capital-gains statement from Groww reports.")
        )
        joined = "\n".join(c["text"] for c in chunks)
        self.assertNotIn("Intraday", joined)
        self.assertTrue(any(c["chunk_id"] == "large_cap__capital_gains" for c in chunks))
        ids = [c["chunk_id"] for c in chunks]
        self.assertEqual(len(ids), len(set(ids)))

    def test_required_fields_and_stable_ids(self) -> None:
        first = chunk_document(_doc("small_cap"))
        second = chunk_document(_doc("small_cap"))
        self.assertEqual([c["chunk_id"] for c in first], [c["chunk_id"] for c in second])
        for chunk in first:
            self.assertEqual(
                set(chunk),
                {"chunk_id", "text", "url", "fund_key", "ingested_at"},
            )
            self.assertEqual(chunk["ingested_at"], "2026-08-30T06:23:21+00:00")

    def test_rejects_off_allowlist_url(self) -> None:
        doc = _doc("large_cap")
        doc["url"] = "https://groww.in/mutual-funds/other"
        with self.assertRaises(ValueError):
            chunk_document(doc)


if __name__ == "__main__":
    unittest.main()
