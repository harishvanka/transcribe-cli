import logging
from pathlib import Path

from faster_whisper import WhisperModel

from transcriber.config import DEFAULT_COMPUTE_TYPE

logger = logging.getLogger("transcriber")


class Transcriber:
    def __init__(self, model_size: str, compute_type: str = DEFAULT_COMPUTE_TYPE) -> None:
        logger.info(f"Loading model: {model_size} (compute_type={compute_type})")
        self.model = WhisperModel(model_size, compute_type=compute_type)

    def transcribe_file(self, audio_path: Path, language: str | None = None) -> str | None:
        try:
            segments, _info = self.model.transcribe(
                str(audio_path),
                language=language,
            )
            return " ".join(segment.text.strip() for segment in segments)
        except Exception as e:
            logger.error(f"Transcription failed for {audio_path.name}: {e}")
            return None
