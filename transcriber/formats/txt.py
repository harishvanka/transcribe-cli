from pathlib import Path


def write_txt(segments: list[dict], output_path: Path) -> None:
    output_path.write_text(
        " ".join(seg["text"] for seg in segments),
        encoding="utf-8",
    )
