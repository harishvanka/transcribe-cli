import json
from pathlib import Path


def write_json(segments: list[dict], output_path: Path) -> None:
    output_path.write_text(
        json.dumps(segments, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
