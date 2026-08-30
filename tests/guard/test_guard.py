import unittest

from code.guard.guard import classify_question


class FundDetectionTests(unittest.TestCase):
    def test_detects_named_funds(self) -> None:
        cases = {
            "HDFC Large Cap Fund Direct Growth": ["large_cap"],
            "hdfc flexi cap fund": ["flexi_cap"],
            "hdfc equity fund": ["flexi_cap"],
            "HDFC ELSS Tax Saver": ["elss"],
            "HDFC Small Cap Fund": ["small_cap"],
            "HDFC Balanced Advantage Fund": ["hybrid"],
            "exit load for HDFC Small Cap and HDFC Large Cap": ["large_cap", "small_cap"],
        }
        for question, expected in cases.items():
            self.assertEqual(classify_question(question).named_funds, expected, question)

    def test_no_fund_named_is_ok_for_retrieval_decision(self) -> None:
        result = classify_question("expense ratio?")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.named_funds, [])


class RefusalTests(unittest.TestCase):
    def test_advice_refused(self) -> None:
        for q in ("Is this a good time to invest?", "Should I buy HDFC Small Cap?",
                  "Which fund is better?", "Best fund to invest in", "Recommend a fund"):
            self.assertEqual(classify_question(q).status, "refused_advice", q)

    def test_returns_math_refused(self) -> None:
        for q in ("Which fund has higher returns?", "What is the XIRR of HDFC Large Cap?",
                  "Compare returns of these funds", "How much would 5 years of SIP earn?"):
            self.assertEqual(classify_question(q).status, "refused_returns", q)

    def test_pii_refused(self) -> None:
        for q in ("My PAN is ABCDE1234F", "Call 9876543210", "mail me at a@b.com",
                  "My account is 123456789012345, please use it", "send OTP 1234"):
            self.assertEqual(classify_question(q).status, "refused_pii", q)

    def test_out_of_corpus_refused(self) -> None:
        self.assertEqual(classify_question("SBI Small Cap fund?").status, "out_of_corpus")
        self.assertEqual(classify_question("HDFC Mid Cap Fund?").status, "out_of_corpus")
        self.assertEqual(classify_question("Axis ELSS?").status, "out_of_corpus")

    def test_out_of_corpus_misspellings_refused(self) -> None:
        for q in (
            "What is the expense ratio of Parag Parikh Flexi Cap Fund?",
            "What is the expense ratio of Parag Parekh Flexi Cap Fund?",
            "Parag Parekh Flexi Cap Fund Direct Growth?",
            "PPFAS Flexi Cap?",
        ):
            self.assertEqual(classify_question(q).status, "out_of_corpus", q)


if __name__ == "__main__":
    unittest.main()