from pathlib import Path

SUPPORTED_FORMATS: set[str] = {".mp4", ".mkv", ".mp3", ".wav"}

VALID_MODELS: list[str] = ["tiny", "base", "small", "medium", "large"]
VALID_FORMATS: list[str] = ["txt", "srt", "json"]
VALID_BACKENDS: list[str] = ["cpu", "directml"]

DEFAULT_MODEL: str = "small"
DEFAULT_OUTPUT_DIR: Path = Path("./outputs")
DEFAULT_COMPUTE_TYPE: str = "auto"   # CTranslate2 picks best for device
DEFAULT_WORKERS: int = 2
DEFAULT_CHUNK_SECONDS: int = 600
DEFAULT_BEAM_SIZE: int = 5
DEFAULT_BACKEND: str = "directml"

FFMPEG_SAMPLE_RATE: int = 16000
FFMPEG_CHANNELS: int = 1

DB_PATH: Path = Path.home() / ".transcriber" / "jobs.db"
