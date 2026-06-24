from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.ai import embed, expand_query, mean_vector
from app.database import Base, engine, get_db
from app.models import Channel, Interaction, Video
from app.schemas import ChannelCreate, InteractionCreate, SearchRequest, SearchResult
from app.ingestion import ingest_channel
from app.vector_store import search, video_vector


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="YouTube Semantics API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse("app/static/index.html")


@app.post("/channels", status_code=201)
def create_channel(payload: ChannelCreate, db: Session = Depends(get_db)):
    if db.query(Channel).filter_by(youtube_channel_id=payload.youtube_channel_id).first():
        raise HTTPException(status_code=409, detail="Channel already exists")
    channel = Channel(**payload.model_dump())
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return {"id": channel.id, "name": channel.name, "youtube_channel_id": channel.youtube_channel_id}


@app.get("/channels")
def list_channels(db: Session = Depends(get_db)):
    return [{"id": item.id, "name": item.name, "youtube_channel_id": item.youtube_channel_id} for item in db.query(Channel).all()]


@app.post("/ingestion/channels/{channel_id}")
def ingest(channel_id: int, db: Session = Depends(get_db)):
    channel = db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ingest_channel(db, channel)


@app.post("/search", response_model=list[SearchResult])
def semantic_search(payload: SearchRequest):
    expanded = expand_query(payload.query)
    hits = search(embed([expanded])[0], payload.limit)
    return [
        SearchResult(
            video_id=hit.payload["video_id"], title=hit.payload["title"], channel=hit.payload["channel"],
            timestamp_seconds=hit.payload["timestamp_seconds"], text_segment=hit.payload["text_segment"],
            thumbnail_url=hit.payload.get("thumbnail_url"), score=hit.score,
        )
        for hit in hits
    ]


@app.post("/interactions", status_code=201)
def record_interaction(payload: InteractionCreate, db: Session = Depends(get_db)):
    if not db.get(Video, payload.video_id):
        raise HTTPException(status_code=404, detail="Video not found")
    item = Interaction(**payload.model_dump())
    db.add(item)
    db.commit()
    return {"status": "recorded"}


@app.get("/feed/{user_id}", response_model=list[SearchResult])
def discovery_feed(user_id: str, db: Session = Depends(get_db)):
    """18 relevance slots + 6 exploration slots, deduplicated by video."""
    interactions = db.query(Interaction).filter_by(user_id=user_id).all()
    weighted_vectors: list[list[float]] = []
    for interaction in interactions:
        vector = video_vector(interaction.video_id)
        if not vector:
            continue
        weight = 1.0 if interaction.kind == "watched" and interaction.watch_seconds >= 60 else -0.5
        weighted_vectors.append([weight * value for value in vector])
    if not weighted_vectors:
        raise HTTPException(status_code=404, detail="No indexed engagement history for this user")
    hits = search(mean_vector(weighted_vectors), 24)
    seen = set()
    results = []
    for hit in hits:
        video_id = hit.payload["video_id"]
        if video_id in seen:
            continue
        seen.add(video_id)
        results.append(SearchResult(video_id=video_id, title=hit.payload["title"], channel=hit.payload["channel"], timestamp_seconds=hit.payload["timestamp_seconds"], text_segment=hit.payload["text_segment"], thumbnail_url=hit.payload.get("thumbnail_url"), score=hit.score))
    return results
