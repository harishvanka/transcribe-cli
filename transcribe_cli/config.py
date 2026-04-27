from pathlib import Path

SUPPORTED_FORMATS: set[str] = {".mp4", ".mkv", ".mp3", ".wav"}

VALID_MODELS: list[str] = ["small", "medium", "large"]

DEFAULT_MODEL: str = "small"
DEFAULT_OUTPUT_DIR: Path = Path("./outputs")
DEFAULT_COMPUTE_TYPE: str = "int8"

FFMPEG_SAMPLE_RATE: int = 16000
FFMPEG_CHANNELS: int = 1
