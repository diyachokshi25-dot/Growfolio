from collections import Counter
import math
import re


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "what",
        "when",
        "which",
        "with",
    }
)
_TOKEN_NORMALIZATION = {"managers": "manager"}


def tokenize(text: str) -> list[str]:
    return [
        _TOKEN_NORMALIZATION.get(token, token)
        for token in _TOKEN_PATTERN.findall(text.lower())
        if token not in _STOP_WORDS
    ]


def _normalized_vector(counts: Counter[str], idf: dict[str, float]) -> dict[str, float]:
    weights = {
        token: (1 + math.log(count)) * idf[token]
        for token, count in counts.items()
        if token in idf
    }
    norm = math.sqrt(sum(weight * weight for weight in weights.values()))
    if not norm:
        return {}
    return {token: weight / norm for token, weight in weights.items()}


def fit_tfidf(documents: list[str]) -> tuple[dict[str, float], list[dict[str, float]]]:
    if not documents:
        raise ValueError("TF-IDF requires at least one document.")

    term_counts = [Counter(tokenize(document)) for document in documents]
    document_frequency: Counter[str] = Counter()
    for counts in term_counts:
        document_frequency.update(counts.keys())

    document_count = len(documents)
    idf = {
        token: math.log((document_count + 1) / (frequency + 1)) + 1
        for token, frequency in sorted(document_frequency.items())
    }
    if not idf:
        raise ValueError("TF-IDF could not find indexable terms.")

    vectors = [_normalized_vector(counts, idf) for counts in term_counts]
    return idf, vectors


def vectorize_query(text: str, idf: dict[str, float]) -> dict[str, float]:
    return _normalized_vector(Counter(tokenize(text)), idf)


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    return sum(weight * right.get(token, 0.0) for token, weight in left.items())
