import unittest
from unittest.mock import Mock, patch

import requests
from fastapi import HTTPException
from pydantic import ValidationError

from app import (
    AskRequest,
    blocked_reason,
    call_llm,
    embed_query,
    load_index,
    refusal_source,
    retrieve,
)


class ApiGuardrailTests(unittest.TestCase):
    def test_groq_is_the_only_answer_provider(self) -> None:
        request = AskRequest(question="What is the exit load?")
        self.assertEqual(request.provider, "groq")
        for provider in ("gemini", "openai"):
            with self.subTest(provider=provider):
                with self.assertRaises(ValidationError):
                    AskRequest(question="What is the exit load?", provider=provider)

    def test_groq_uses_bearer_key_and_parses_answer(self) -> None:
        response = Mock()
        response.json.return_value = {
            "choices": [
                {"message": {"content": "A factual answer."}}
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
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            with patch("app.requests.post", return_value=response) as post:
                answer = call_llm("What is the exit load?", matches, "groq")

        self.assertEqual(answer, "A factual answer.")
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer test-key",
        )
        self.assertEqual(
            post.call_args.kwargs["json"]["model"],
            "openai/gpt-oss-20b",
        )
        self.assertFalse(post.call_args.kwargs["json"]["include_reasoning"])

    def test_groq_daily_rate_limit_is_distinguished_from_temporary_limit(self) -> None:
        matches = [
            {
                "text": "Exit load information.",
                "metadata": {
                    "source_url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
                    "section": "Exit load",
                },
            }
        ]
        cases = (
            (
                {"x-ratelimit-remaining-requests": "0"},
                "Limit for the day reached. Please try again after the daily quota resets.",
            ),
            (
                {
                    "x-ratelimit-remaining-requests": "20",
                    "x-ratelimit-remaining-tokens": "0",
                },
                "Groq is temporarily rate-limited. Please try again shortly.",
            ),
        )
        for headers, expected_detail in cases:
            with self.subTest(expected_detail=expected_detail):
                response = Mock(status_code=429, headers=headers)
                response.raise_for_status.side_effect = requests.HTTPError(
                    response=response
                )
                with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
                    with patch("app.requests.post", return_value=response):
                        with self.assertRaises(HTTPException) as raised:
                            call_llm(
                                "What is the exit load?",
                                matches,
                                "groq",
                            )
                self.assertEqual(raised.exception.status_code, 429)
                self.assertEqual(raised.exception.detail, expected_detail)

    def test_query_vector_uses_the_bundled_idf_vocabulary(self) -> None:
        index = {"idf": {"minimum": 1.5, "sip": 1.2}}
        with patch("app.load_index", return_value=index):
            vector = embed_query("What is the minimum SIP?")

        self.assertEqual(set(vector), {"minimum", "sip"})
        self.assertAlmostEqual(
            sum(weight * weight for weight in vector.values()),
            1.0,
        )

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

    def test_retrieval_filters_by_scheme_and_returns_citation_metadata(self) -> None:
        query = {"exit": 0.8, "load": 0.6}
        index = {
            "items": [
                {
                    "text": "Exit load details.",
                    "metadata": {
                        "source_id": "hdfc_large_cap",
                        "source_title": "HDFC Large Cap Fund Direct Growth",
                        "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
                        "fetched_at": "2026-01-15",
                        "section": "Exit load",
                    },
                    "vector": query,
                },
                {
                    "text": "Minimum SIP details.",
                    "metadata": {
                        "source_id": "hdfc_flexi_cap",
                        "source_title": "HDFC Flexi Cap Direct Plan Growth",
                        "source_url": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
                        "fetched_at": "2026-01-15",
                        "section": "Minimum SIP",
                    },
                    "vector": {"minimum": 1.0},
                },
            ]
        }
        with patch("app.embed_query", return_value=query):
            with patch("app.load_index", return_value=index):
                matches = retrieve("What is the HDFC large cap exit load?")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["metadata"]["source_id"], "hdfc_large_cap")
        self.assertEqual(matches[0]["metadata"]["fetched_at"], "2026-01-15")
        self.assertEqual(matches[0]["metadata"]["source_url"], index["items"][0]["metadata"]["source_url"])

    def test_empty_query_vector_returns_no_matches(self) -> None:
        with patch("app.embed_query", return_value={}):
            matches = retrieve("What is this unrelated fact?")

        self.assertEqual(matches, [])

    def test_invalid_bundled_index_returns_setup_message(self) -> None:
        load_index.cache_clear()
        self.addCleanup(load_index.cache_clear)
        invalid_index = {
            "provider": "bundled_index",
            "embedding_model": "tfidf-v1",
            "idf": {},
            "items": [],
            "count": 0,
        }
        with patch("app.INDEX", invalid_index):
            with self.assertRaises(HTTPException) as raised:
                load_index()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("run python ingest.py", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
