from uuid import UUID, uuid5, NAMESPACE_URL

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.config import settings


def client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def ensure_collection() -> None:
    qdrant = client()
    if not qdrant.collection_exists(settings.qdrant_collection):
        qdrant.create_collection(settings.qdrant_collection, vectors_config=VectorParams(size=settings.embedding_dimensions, distance=Distance.COSINE))


def upsert_chunk(video_id: str, index: int, vector: list[float], payload: dict) -> None:
    ensure_collection()
    point_id = str(uuid5(NAMESPACE_URL, f"youtube:{video_id}:chunk:{index}"))
    client().upsert(settings.qdrant_collection, [PointStruct(id=point_id, vector=vector, payload=payload)])


def search(vector: list[float], limit: int):
    ensure_collection()
    return client().search(collection_name=settings.qdrant_collection, query_vector=vector, limit=limit, with_payload=True)


def video_vector(database_video_id: int) -> list[float] | None:
    """Return one representative chunk vector for an interacted video."""
    ensure_collection()
    points, _ = client().scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(must=[FieldCondition(key="database_video_id", match=MatchValue(value=database_video_id))]),
        limit=1,
        with_vectors=True,
        with_payload=False,
    )
    return list(points[0].vector) if points else None
