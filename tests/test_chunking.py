from app.chunking import chunk_transcript


def test_chunking_preserves_start_and_overlap():
    source = [
        {"text": "one two three", "start": 4},
        {"text": "four five six", "start": 8},
        {"text": "seven eight nine", "start": 12},
    ]
    chunks = chunk_transcript(source, size_words=5, overlap_words=2)
    assert [chunk.start_seconds for chunk in chunks] == [4, 8, 12]
    assert chunks[0].text == "one two three four five"
    assert chunks[1].text == "four five six seven eight"


def test_chunking_rejects_invalid_overlap():
    try:
        chunk_transcript([], size_words=4, overlap_words=4)
    except ValueError:
        return
    assert False, "expected a ValueError"
