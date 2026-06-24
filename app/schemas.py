from datetime import datetime
from pydantic import BaseModel, Field


class ChannelCreate(BaseModel):
    youtube_channel_id: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=255)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=12, ge=1, le=30)


class SearchResult(BaseModel):
    video_id: str
    title: str
    channel: str
    timestamp_seconds: int
    text_segment: str
    score: float
    thumbnail_url: str | None = None


class InteractionCreate(BaseModel):
    user_id: str
    video_id: int
    kind: str = Field(pattern="^(watched|not_interested)$")
    watch_seconds: int = Field(default=0, ge=0)

