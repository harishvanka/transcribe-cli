def merge_chunks(chunk_segments: list[tuple[int, list[dict]]], chunk_seconds: int) -> list[dict]:
    merged = []
    for chunk_index, segments in chunk_segments:
        offset = chunk_index * chunk_seconds
        for seg in segments:
            merged.append({
                "start": seg["start"] + offset,
                "end": seg["end"] + offset,
                "text": seg["text"],
            })
    return merged
