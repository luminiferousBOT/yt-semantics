from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TranscriptChunk:
    text: str
    start_seconds: int


def chunk_transcript(entries: Iterable[dict], size_words: int = 220, overlap_words: int = 40) -> list[TranscriptChunk]:
    """Preserve the timestamp belonging to the first word of each window."""
    if not 0 <= overlap_words < size_words:
        raise ValueError("overlap_words must be smaller than size_words")
    words: list[tuple[str, int]] = []
    for entry in entries:
        start = int(float(entry.get("start", 0)))
        words.extend((word, start) for word in entry.get("text", "").split())
    if not words:
        return []
    chunks = []
    step = size_words - overlap_words
    for offset in range(0, len(words), step):
        window = words[offset : offset + size_words]
        if not window:
            break
        chunks.append(TranscriptChunk(" ".join(word for word, _ in window), window[0][1]))
        if offset + size_words >= len(words):
            break
    return chunks
