import unittest

from app import blocked_reason, refusal_source


class ApiGuardrailTests(unittest.TestCase):
    def test_performance_questions_are_refused_and_use_amc_disclosure(self) -> None:
        question = "What are this fund's returns?"

        reason = blocked_reason(question)
        if reason is None:
            self.fail("Performance questions should be refused.")
        self.assertIn("performance", reason.lower())
        self.assertEqual(refusal_source(question), "https://www.hdfcfund.com/")

    def test_personal_identifier_is_refused_before_retrieval(self) -> None:
        reason = blocked_reason("My PAN is ABCDE1234F")
        if reason is None:
            self.fail("PAN-like identifiers should be refused.")
        self.assertIn("personal identifiers", reason.lower())

    def test_fact_question_is_not_blocked(self) -> None:
        self.assertIsNone(blocked_reason("What is the expense ratio for HDFC Large Cap?"))


if __name__ == "__main__":
    unittest.main()
