import math
from functools import lru_cache
import httpx

from app.config import settings


@lru_cache
def _embedder():
    """Loaded only when indexing/searching, so the web server still starts quickly."""
    try:
        from fastembed import TextEmbedding
    except ImportError as error:
        raise RuntimeError("Install dependencies with `pip install -r requirements.txt`.") from error
    return TextEmbedding(model_name=settings.embedding_model)


def embed(texts: list[str]) -> list[list[float]]:
    # BGE is designed for cosine similarity; FastEmbed returns normalized vectors.
    return [vector.tolist() for vector in _embedder().embed(texts)]


def expand_query(query: str) -> str:
    """Use local Ollama when present; search remains useful if it is not running."""
    try:
        response = httpx.post(
            f"{settings.ollama_url.rstrip('/')}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": "Expand this search into 3-4 closely related scientific, psychological, or mechanical concepts. Return a single comma-separated line only. Query: " + query,
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("response", "").strip() or query
    except (httpx.HTTPError, ValueError):
        return query


def mean_vector(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    values = [sum(items) / len(vectors) for items in zip(*vectors)]
    magnitude = math.sqrt(sum(value * value for value in values))
    return [value / magnitude for value in values] if magnitude else values
