import logging
import multiprocessing
import os
import shutil
import tempfile
from pathlib import Path

from transcriber import db
from transcriber.chunker import split_audio
from transcriber.config import DEFAULT_COMPUTE_TYPE
from transcriber.ffmpeg_utils import extract_audio
from transcriber.formats import json as fmt_json
from transcriber.formats import srt as fmt_srt
from transcriber.formats import txt as fmt_txt
from transcriber.merger import merge_chunks
from transcriber.transcriber import Transcriber
from transcriber.utils import setup_logging

_transcriber: Transcriber | None = None
_worker_label: str = "WORKER"


def _init_worker(model_size: str, compute_type: str, verbose: bool) -> None:
    global _transcriber, _worker_label
    name = multiprocessing.current_process().name  # e.g. "SpawnPoolWorker-1"
    num = name.split("-")[-1]
    _worker_label = f"WORKER-{num}"
    setup_logging(verbose=verbose)
    _transcriber = Transcriber(model_size=model_size, compute_type=compute_type)


def process_job(args: tuple) -> None:
    position, total, job_id, file_path_str, language, chunk_seconds, output_formats, output_dir_str = args

    file_path = Path(file_path_str)
    output_dir = Path(output_dir_str)
    logger = logging.getLogger("transcriber")
    prefix = f"[{_worker_label}]"

    logger.info(f"{prefix} [{position}/{total}] Processing {file_path.name}")
    db.update_status(job_id, "in_progress")

    temp_dir = Path(tempfile.mkdtemp())
    try:
        audio_path = extract_audio(file_path, output_dir=temp_dir)
        if audio_path is None:
            db.mark_failed(job_id, "ffmpeg audio extraction failed")
            return

        chunks = split_audio(audio_path, chunk_seconds)
        if not chunks:
            db.mark_failed(job_id, "no chunks produced by ffmpeg")
            return

        chunk_segments: list[tuple[int, list[dict]]] = []
        for i, chunk_path in enumerate(chunks):
            segs = _transcriber.transcribe_file(chunk_path, language=language)
            if segs is None:
                db.mark_failed(job_id, f"transcription failed on {chunk_path.name}")
                return
            chunk_segments.append((i, segs))
            logger.info(f"[CHUNK] {chunk_path.name} done")
            db.update_progress(job_id, int((i + 1) / len(chunks) * 100))

        segments = merge_chunks(chunk_segments, chunk_seconds)
        logger.info("[MERGE] completed")

        output_dir.mkdir(parents=True, exist_ok=True)
        stem = file_path.stem
        written: list[str] = []

        for fmt in output_formats:
            if fmt == "txt":
                out = output_dir / f"{stem}.txt"
                fmt_txt.write_txt(segments, out)
                written.append(str(out))
            elif fmt == "srt":
                out = output_dir / f"{stem}.srt"
                fmt_srt.write_srt(segments, out)
                written.append(str(out))
            elif fmt == "json":
                out = output_dir / f"{stem}.json"
                fmt_json.write_json(segments, out)
                written.append(str(out))

        db.mark_completed(job_id, ",".join(written))
        logger.info(f"[SUCCESS] {file_path.name}")

    except Exception as e:
        logger.error(f"{prefix} Error processing {file_path.name}: {e}")
        db.mark_failed(job_id, str(e))

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
