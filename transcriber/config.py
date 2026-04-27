from pathlib import Path

SUPPORTED_FORMATS: set[str] = {".mp4", ".mkv", ".mp3", ".wav"}

VALID_MODELS: list[str] = ["small", "medium", "large"]
VALID_FORMATS: list[str] = ["txt", "srt", "json"]

DEFAULT_MODEL: str = "small"
DEFAULT_OUTPUT_DIR: Path = Path("./outputs")
DEFAULT_COMPUTE_TYPE: str = "int8"
DEFAULT_WORKERS: int = 2
DEFAULT_CHUNK_SECONDS: int = 600

FFMPEG_SAMPLE_RATE: int = 16000
FFMPEG_CHANNELS: int = 1

DB_PATH: Path = Path.home() / ".transcriber" / "jobs.db"
