import logging
from pathlib import Path

from transcribe_cli.config import SUPPORTED_FORMATS


def setup_logging(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger("transcribe_cli")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter("[%(levelname)s] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def collect_media_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() in SUPPORTED_FORMATS:
            return [input_path]
        return []

    if input_path.is_dir():
        return sorted(
            f for f in input_path.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS
        )

    return []
