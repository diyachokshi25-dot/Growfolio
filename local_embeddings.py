from functools import lru_cache
from pathlib import Path
from tempfile import gettempdir


@lru_cache(maxsize=1)
def _load_model(model_name: str):
    from fastembed import TextEmbedding

    cache_dir = Path(gettempdir()) / "growfolio-fastembed"
    return TextEmbedding(
        model_name=model_name,
        cache_dir=str(cache_dir),
        threads=1,
    )


def embed_passages(model_name: str, passages: list[str]) -> list[list[float]]:
    model = _load_model(model_name)
    return [
        [float(value) for value in vector.tolist()]
        for vector in model.passage_embed(passages)
    ]


def embed_query(model_name: str, query: str) -> list[float]:
    model = _load_model(model_name)
    vector = next(iter(model.query_embed(query)), None)
    if vector is None:
        raise RuntimeError("FastEmbed returned no query embedding.")
    return [float(value) for value in vector.tolist()]
