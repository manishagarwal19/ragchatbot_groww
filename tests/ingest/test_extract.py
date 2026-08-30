import json
import unittest
from pathlib import Path

from code.ingest.allowlist import ALLOWED_URLS, FUNDS, assert_allowed_url
from code.ingest.extract import extract_document, redact_pii


FIXTURE = """<!DOCTYPE html><html><head><title>HDFC Large Cap Fund Direct Growth</title></head>
<body>
<a href="https://www.hdfcfund.com/statdocs/large-cap-factsheet.pdf">Factsheet</a>
<p>Expense ratio shown on page.</p>
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"mfServerSideData":{
  "scheme_name": "HDFC LARGE CAP FUND - DIRECT PLAN - GROWTH OPTION",
  "expense_ratio": "1.02",
  "exit_load": "Exit load of 1% if redeemed within 1 year",
  "min_sip_investment": 100,
  "benchmark": "NIFTY 100 TRI",
  "nfo_risk": "Very High",
  "lock_in": {"years": null, "months": null, "days": null},
  "sid_url": "https://www.hdfcfund.com/sid.pdf",
  "brochure_link": null,
  "category_info": {"tax_impact": "If you redeem within one year, returns are taxed at 20%."}
}}}}</script>
</body></html>
"""


class AllowlistTests(unittest.TestCase):
    def test_exactly_five_urls(self) -> None:
        self.assertEqual(len(FUNDS), 5)
        self.assertEqual(len(ALLOWED_URLS), 5)

    def test_rejects_other_urls(self) -> None:
        with self.assertRaises(ValueError):
            assert_allowed_url("https://groww.in/mutual-funds/other-fund")


class ExtractTests(unittest.TestCase):
    def test_extracts_facts_and_factsheet_links(self) -> None:
        doc = extract_document(FIXTURE, "large_cap", "2026-08-30T06:00:00+00:00")
        self.assertEqual(doc["fund_key"], "large_cap")
        self.assertEqual(doc["url"], FUNDS["large_cap"]["url"])
        self.assertIn("Expense ratio: 1.02", doc["text"])
        self.assertIn("Minimum SIP: 100", doc["text"])
        self.assertIn("Lock-in:", doc["text"])
        self.assertTrue(any("factsheet.pdf" in u or "sid.pdf" in u for u in doc["factsheet_links"]))
        self.assertNotIn("https://groww.in/mutual-funds/other", "\n".join(doc["factsheet_links"]))

    def test_unknown_fund_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            extract_document(FIXTURE, "not_a_fund", "2026-08-30T06:00:00+00:00")

    def test_redacts_pii(self) -> None:
        self.assertIn("[REDACTED]", redact_pii("PAN ABCDE1234F and mail a@b.com"))


if __name__ == "__main__":
    unittest.main()
