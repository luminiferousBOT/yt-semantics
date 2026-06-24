from datetime import datetime
from xml.etree import ElementTree

import httpx
from sqlalchemy.orm import Session
from youtube_transcript_api import YouTubeTranscriptApi

from app.ai import embed
from app.chunking import chunk_transcript
from app.config import settings
from app.models import Channel, Video
from app.vector_store import upsert_chunk


def _youtube():
    from googleapiclient.discovery import build
    if not settings.youtube_api_key:
        raise RuntimeError("YOUTUBE_API_KEY is required for ingestion")
    return build("youtube", "v3", developerKey=settings.youtube_api_key)


def _parse_date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None) if value else None


def fetch_channel_videos(channel_id: str, max_results: int = 50) -> list[dict]:
    if not settings.youtube_api_key:
        return fetch_channel_rss(channel_id, max_results)
    api = _youtube()
    channel = api.channels().list(part="contentDetails", id=channel_id).execute()
    items = channel.get("items", [])
    if not items:
        raise ValueError(f"YouTube channel {channel_id!r} was not found")
    uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    playlist = api.playlistItems().list(part="snippet,contentDetails", playlistId=uploads_id, maxResults=max_results).execute()
    ids = [item["contentDetails"]["videoId"] for item in playlist.get("items", [])]
    if not ids:
        return []
    details = api.videos().list(part="snippet", id=",".join(ids)).execute()["items"]
    return [
        {
            "youtube_video_id": item["id"],
            "title": item["snippet"]["title"],
            "description": item["snippet"].get("description", ""),
            "thumbnail_url": item["snippet"].get("thumbnails", {}).get("high", {}).get("url"),
            "published_at": _parse_date(item["snippet"].get("publishedAt")),
        }
        for item in details
    ]


def fetch_channel_rss(channel_id: str, max_results: int = 15) -> list[dict]:
    """Free, keyless discovery of the most recent channel uploads."""
    response = httpx.get(
        f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
        headers={"User-Agent": "YouTubeSemantics/0.1"}, timeout=20,
    )
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "media": "http://search.yahoo.com/mrss/"}
    videos = []
    for entry in root.findall("atom:entry", ns)[:max_results]:
        group = entry.find("media:group", ns)
        thumbnail = group.find("media:thumbnail", ns) if group is not None else None
        description = group.findtext("media:description", default="", namespaces=ns) if group is not None else ""
        videos.append({
            "youtube_video_id": entry.findtext("yt:videoId", namespaces=ns),
            "title": entry.findtext("atom:title", default="", namespaces=ns),
            "description": description,
            "thumbnail_url": thumbnail.get("url") if thumbnail is not None else None,
            "published_at": _parse_date(entry.findtext("atom:published", namespaces=ns)),
        })
    return [video for video in videos if video["youtube_video_id"]]


def fetch_transcript(video_id: str) -> list[dict]:
    """Normalise both current and legacy youtube-transcript-api result formats."""
    api = YouTubeTranscriptApi()
    try:
        result = api.fetch(video_id)
    except AttributeError:  # legacy package releases
        result = YouTubeTranscriptApi.get_transcript(video_id)
    return [
        {"text": item["text"], "start": item["start"]} if isinstance(item, dict) else {"text": item.text, "start": item.start}
        for item in result
    ]


def index_video(db: Session, video: Video, channel: Channel) -> int:
    if video.transcript_status == "indexed":
        return 0
    try:
        transcript = fetch_transcript(video.youtube_video_id)
        chunks = chunk_transcript(transcript)
        vectors = embed([chunk.text for chunk in chunks])
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            upsert_chunk(video.youtube_video_id, index, vector, {
                "video_id": video.youtube_video_id,
                "title": video.title,
                "channel": channel.name,
                "timestamp_seconds": chunk.start_seconds,
                "text_segment": chunk.text,
                "thumbnail_url": video.thumbnail_url,
                "database_video_id": video.id,
            })
        video.transcript_status = "indexed"
        db.commit()
        return len(chunks)
    except Exception as error:
        # Keep the video discoverable in SQL and allow a separate Whisper worker to retry it.
        video.transcript_status = "transcript_unavailable"
        db.commit()
        return 0


def ingest_channel(db: Session, channel: Channel, max_results: int = 50) -> dict:
    created = indexed_chunks = 0
    for item in fetch_channel_videos(channel.youtube_channel_id, max_results):
        video = db.query(Video).filter_by(youtube_video_id=item["youtube_video_id"]).first()
        if not video:
            video = Video(channel_id=channel.id, **item)
            db.add(video)
            db.commit()
            db.refresh(video)
            created += 1
        indexed_chunks += index_video(db, video, channel)
    return {"videos_created": created, "chunks_indexed": indexed_chunks}
