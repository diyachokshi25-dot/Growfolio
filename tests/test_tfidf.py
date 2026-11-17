import unittest

from tfidf import cosine_similarity, fit_tfidf, vectorize_query


class TfidfTests(unittest.TestCase):
    def test_query_ranks_matching_scheme_fact_above_other_scheme(self) -> None:
        documents = [
            "HDFC Flexi Cap minimum SIP investment",
            "HDFC Mid Cap exit load",
        ]
        idf, vectors = fit_tfidf(documents)
        query = vectorize_query("What is the minimum SIP for HDFC Flexi Cap?", idf)

        self.assertGreater(
            cosine_similarity(query, vectors[0]),
            cosine_similarity(query, vectors[1]),
        )

    def test_unknown_terms_produce_no_query_vector(self) -> None:
        idf, _ = fit_tfidf(["HDFC Flexi Cap minimum SIP"])

        self.assertEqual(vectorize_query("unseenword", idf), {})

    def test_empty_corpus_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one document"):
            fit_tfidf([])


if __name__ == "__main__":
    unittest.main()
