import unittest
from unittest.mock import Mock, patch

from local_embeddings import embed_passages, embed_query


class LocalEmbeddingTests(unittest.TestCase):
    def test_passages_use_fastembed_passage_embeddings(self) -> None:
        vector = Mock()
        vector.tolist.return_value = [0.1, 0.2]
        model = Mock()
        model.passage_embed.return_value = [vector]

        with patch("local_embeddings._load_model", return_value=model):
            embeddings = embed_passages("BAAI/bge-small-en-v1.5", ["scheme facts"])

        self.assertEqual(embeddings, [[0.1, 0.2]])
        model.passage_embed.assert_called_once_with(["scheme facts"])

    def test_queries_use_fastembed_query_embeddings(self) -> None:
        vector = Mock()
        vector.tolist.return_value = [0.3, 0.4]
        model = Mock()
        model.query_embed.return_value = iter([vector])

        with patch("local_embeddings._load_model", return_value=model):
            embedding = embed_query("BAAI/bge-small-en-v1.5", "minimum SIP")

        self.assertEqual(embedding, [0.3, 0.4])
        model.query_embed.assert_called_once_with("minimum SIP")


if __name__ == "__main__":
    unittest.main()
