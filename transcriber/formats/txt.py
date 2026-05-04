from pathlib import Path


def write_txt(segments: list[dict], output_path: Path) -> None:
    output_path.write_text(
        " ".join(seg["text"] for seg in segments),
        encoding="utf-8",
    )


def append_txt(segments: list[dict], output_path: Path, first: bool = False) -> None:
    if not segments:
        return
    text = " ".join(seg["text"] for seg in segments)
    with output_path.open("a", encoding="utf-8") as f:
        if not first:
            f.write(" ")
        f.write(text)
