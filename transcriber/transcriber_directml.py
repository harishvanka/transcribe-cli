"""
Whisper transcription backend using ONNX Runtime with DirectML.

On Windows with a Qualcomm / AMD / Intel GPU this uses the DirectML execution
provider (GPU-accelerated). Falls back to CPU automatically if DirectML is not
available.

Required packages (install once):
    pip uninstall onnxruntime           # remove if present — conflicts with dml build
    pip install onnxruntime-directml
    pip install "optimum[exporters]" transformers soundfile
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    # torch is only needed the first time a model is exported to ONNX;
    # after that the cached ONNX files are reused without torch.

Note: vad_filter is not supported by this backend (silently ignored).
"""

import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger("transcriber")

_MODEL_MAP: dict[str, str] = {
    "tiny":   "openai/whisper-tiny",
    "base":   "openai/whisper-base",
    "small":  "openai/whisper-small",
    "medium": "openai/whisper-medium",
    "large":  "openai/whisper-large-v3",
}


def _select_provider() -> str:
    """Return the best available ONNX Runtime execution provider."""
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        if "DmlExecutionProvider" in available:
            return "DmlExecutionProvider"
    except Exception:
        pass
    return "CPUExecutionProvider"


class DirectMLTranscriber:
    """
    Drop-in replacement for Transcriber that runs inference via ONNX Runtime.

    Uses DirectML on Windows (Qualcomm Adreno / AMD / Intel GPU via WDDM);
    falls back to CPUExecutionProvider on any other platform or if DirectML
    is unavailable.

    The interface mirrors Transcriber.transcribe_file() exactly so worker.py
    needs no changes.
    """

    def __init__(
        self,
        model_size: str = "small",
        beam_size: int = 5,
        vad_filter: bool = False,
    ) -> None:
        try:
            from optimum.onnxruntime import ORTModelForSpeechSeq2Seq
            from transformers import AutoProcessor
            from transformers import pipeline as hf_pipeline
        except ImportError as exc:
            raise ImportError(
                "DirectML backend requires additional packages.\n"
                "Run: pip install onnxruntime-directml \"optimum[exporters]\" "
                "transformers soundfile torch"
            ) from exc

        model_id = _MODEL_MAP.get(model_size, "openai/whisper-small")
        provider = _select_provider()

        logger.info(f"Loading model '{model_id}' | provider={provider}")
        logger.info(
            "First run: model will be downloaded and exported to ONNX "
            "(cached afterward — may take a few minutes)."
        )

        processor = AutoProcessor.from_pretrained(model_id)
        ort_model = ORTModelForSpeechSeq2Seq.from_pretrained(
            model_id,
            export=True,      # downloads PyTorch weights, converts → ONNX, caches
            provider=provider,
        )

        # Build the pipeline once; reuse across all transcribe_file() calls.
        self._pipe = hf_pipeline(
            "automatic-speech-recognition",
            model=ort_model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            chunk_length_s=30,       # Whisper's 30-second attention window
            return_timestamps=True,  # needed for segment-level start/end times
        )
        self._beam_size = beam_size

        if vad_filter:
            logger.warning("vad_filter is not supported by DirectMLTranscriber; ignored.")

    def transcribe_file(
        self,
        audio_path: Path,
        language: str | None = None,
        progress_cb: Callable[[float], None] | None = None,
    ) -> list[dict] | None:
        """
        Transcribe one audio file.  Returns a list of segment dicts
        {"start": float, "end": float, "text": str} or None on failure.

        progress_cb is called with 0.0 before inference and 1.0 after.
        Mid-inference progress is not available from the ONNX pipeline.
        """
        try:
            if progress_cb:
                progress_cb(0.0)

            generate_kwargs: dict = {"num_beams": self._beam_size}
            if language:
                generate_kwargs["language"] = language

            result = self._pipe(str(audio_path), generate_kwargs=generate_kwargs)

            if progress_cb:
                progress_cb(1.0)

            segments: list[dict] = []
            for chunk in result.get("chunks") or []:
                ts = chunk.get("timestamp") or (None, None)
                if len(ts) < 2 or ts[0] is None:
                    continue
                start = float(ts[0])
                end   = float(ts[1]) if ts[1] is not None else start
                text  = chunk["text"].strip()
                if text:
                    segments.append({"start": start, "end": end, "text": text})

            return segments

        except Exception as exc:
            logger.error(f"DirectML transcription failed for {audio_path.name}: {exc}")
            return None
