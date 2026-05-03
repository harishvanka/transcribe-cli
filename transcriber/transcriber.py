import logging
from pathlib import Path
from typing import Callable

from faster_whisper import WhisperModel

from transcriber.config import DEFAULT_COMPUTE_TYPE

logger = logging.getLogger("transcriber")


class Transcriber:
    def __init__(self, model_size: str, compute_type: str = DEFAULT_COMPUTE_TYPE) -> None:
        logger.info(f"Loading model: {model_size} (compute_type={compute_type})")
        self.model = WhisperModel(model_size, compute_type=compute_type)

    def transcribe_file(
        self,
        audio_path: Path,
        language: str | None = None,
        progress_cb: Callable[[float], None] | None = None,
    ) -> list[dict] | None:
        try:
            segments_gen, info = self.model.transcribe(str(audio_path), language=language)
            total_duration = info.duration
            result = []
            for seg in segments_gen:
                result.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
                if progress_cb and total_duration > 0:
                    progress_cb(min(seg.end / total_duration, 1.0))
            return result
        except Exception as e:
            logger.error(f"Transcription failed for {audio_path.name}: {e}")
            return None
