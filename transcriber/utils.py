import logging
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from transcriber.config import SUPPORTED_FORMATS

_BAR_ASCII = "-|"
_BAR_FMT   = "  [{bar:100}] {percentage:3.0f}%  [{elapsed}]"


def make_bar(desc: str, total: int = 100) -> tqdm:
    """Print a timestamped header line, then return the bar on the next line."""
    ts = datetime.now().strftime("%H:%M:%S")
    tqdm.write(f"  [INFO] [{ts}]  {desc}")
    return tqdm(
        total=total,
        desc="",
        ascii=_BAR_ASCII,
        bar_format=_BAR_FMT,
        leave=True,
    )


class _TqdmHandler(logging.StreamHandler):
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
