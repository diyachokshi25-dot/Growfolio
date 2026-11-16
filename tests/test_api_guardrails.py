import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError

from app import AskRequest, blocked_reason, call_llm, refusal_source


class ApiGuardrailTests(unittest.TestCase):
    def test_gemini_is_the_only_answer_provider(self) -> None:
        request = AskRequest(question="What is the exit load?")
        self.assertEqual(request.provider, "gemini")
        with self.assertRaises(ValidationError):
            AskRequest(question="What is the exit load?", provider="openai")

    def test_gemini_uses_api_key_header_and_parses_answer(self) -> None:
        response = Mock()
        response.json.return_value = {
            "candidates": [
                {"content": {"parts": [{"text": "A factual answer."}]}}
            ]
        }
        matches = [
            {
                "text": "Exit load information.",
                "metadata": {
                    "source_url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
                    "section": "Exit load",
                },
            }
        ]
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("app.requests.post", return_value=response) as post:
                answer = call_llm("What is the exit load?", matches, "gemini")

        self.assertEqual(answer, "A factual answer.")
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "test-key")
        self.assertNotIn("key=", post.call_args.args[0])

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
