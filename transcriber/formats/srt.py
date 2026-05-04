from pathlib import Path


def _ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments: list[dict], output_path: Path) -> None:
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_ts(seg['start'])} --> {_ts(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def append_srt(segments: list[dict], output_path: Path, start_index: int = 1) -> int:
    """Append segments to an existing SRT file. Returns the next subtitle index."""
    if not segments:
        return start_index
    lines: list[str] = []
    idx = start_index
    for seg in segments:
        lines.append(str(idx))
        lines.append(f"{_ts(seg['start'])} --> {_ts(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")
        idx += 1
    with output_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return idx
