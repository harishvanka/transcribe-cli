import logging
import os
from pathlib import Path
from typing import Callable

from faster_whisper import WhisperModel

from transcriber.config import DEFAULT_BEAM_SIZE, DEFAULT_COMPUTE_TYPE

logger = logging.getLogger("transcriber")


def _detect_device() -> tuple[str, str]:
    """Return (device, compute_type) based on what's available."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


class Transcriber:
    def __init__(
        self,
        model_size: str,
        device: str = "auto",
        compute_type: str = DEFAULT_COMPUTE_TYPE,
        cpu_threads: int = 0,
        beam_size: int = DEFAULT_BEAM_SIZE,
        vad_filter: bool = False,
    ) -> None:
        if device == "auto":
            device, compute_type = _detect_device()

        n_threads = cpu_threads or os.cpu_count() or 4
        logger.info(
            f"Loading model '{model_size}' | device={device} compute={compute_type}"
            + (f" threads={n_threads}" if device == "cpu" else "")
        )

        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
            num_workers=1,
        )
        self.beam_size = beam_size
        self.vad_filter = vad_filter

    def transcribe_file(
        self,
        audio_path: Path,
        language: str | None = None,
        progress_cb: Callable[[float], None] | None = None,
    ) -> list[dict] | None:
        try:
            segments_gen, info = self.model.transcribe(
                str(audio_path),
                language=language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
            )
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
