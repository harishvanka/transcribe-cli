import logging
import subprocess
import tempfile
from pathlib import Path

from transcriber.config import FFMPEG_CHANNELS, FFMPEG_SAMPLE_RATE

logger = logging.getLogger("transcriber")


def extract_audio(input_path: Path) -> Path | None:
    temp_dir = Path(tempfile.mkdtemp())
    output_path = temp_dir / f"{input_path.stem}.wav"

    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-ar", str(FFMPEG_SAMPLE_RATE),
        "-ac", str(FFMPEG_CHANNELS),
        str(output_path),
        "-y",
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed for {input_path.name}: {e.stderr.strip()}")
        return None
    except FileNotFoundError:
        logger.error("FFmpeg not found. Please install FFmpeg and ensure it's on PATH.")
        return None

    return output_path
