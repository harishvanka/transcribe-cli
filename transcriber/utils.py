import logging
from pathlib import Path

from tqdm import tqdm

from transcriber.config import SUPPORTED_FORMATS


class _TqdmHandler(logging.StreamHandler):
    """Logging handler that writes through tqdm so log lines don't break the progress bar."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            tqdm.write(self.format(record))
        except Exception:
            self.handleError(record)


def setup_logging(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger("transcriber")
    logger.setLevel(level)

    if not logger.handlers:
        handler = _TqdmHandler()
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
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
