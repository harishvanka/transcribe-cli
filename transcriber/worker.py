import logging
import shutil
import tempfile
import time
from pathlib import Path

from transcriber import db
from transcriber.chunker import split_audio
from transcriber.ffmpeg_utils import extract_audio
from transcriber.formats import json as fmt_json
from transcriber.formats import srt as fmt_srt
from transcriber.formats import txt as fmt_txt
from transcriber.merger import merge_chunks
from transcriber.transcriber import Transcriber
from transcriber.utils import make_bar

logger = logging.getLogger("transcriber")


def process_file(
    job_id: int,
    file_path: Path,
    language: str | None,
    chunk_seconds: int,
    output_formats: list[str],
    output_dir: Path,
    transcriber: Transcriber,
) -> dict[str, float] | None:
    """
    Run the full pipeline for one file.
    Returns a stage-times dict on success, None on failure.
    """
    db.update_status(job_id, "in_progress")
    t_job = time.perf_counter()
    stage_times: dict[str, float] = {}

    temp_dir = Path(tempfile.mkdtemp())
    try:
        # ── Extract audio ──────────────────────────────────────────────────────
        t0 = time.perf_counter()
        with make_bar("Extracting audio") as bar:
            def extract_cb(pct: float) -> None:
                bar.n = int(pct)
                bar.refresh()
            audio_path = extract_audio(file_path, output_dir=temp_dir, progress_cb=extract_cb)
            bar.n = 100
            bar.refresh()
        stage_times["extract"] = time.perf_counter() - t0

        if audio_path is None:
            db.mark_failed(job_id, "ffmpeg audio extraction failed")
            return None

        # ── Split into chunks ──────────────────────────────────────────────────
        t0 = time.perf_counter()
        with make_bar("Splitting into chunks") as bar:
            chunks = split_audio(audio_path, chunk_seconds)
            bar.n = 100
            bar.refresh()
        stage_times["split"] = time.perf_counter() - t0

        if not chunks:
            db.mark_failed(job_id, "no chunks produced by ffmpeg")
            return None

        # ── Transcribe (one bar, all chunks) ───────────────────────────────────
        n_chunks = len(chunks)
        t0 = time.perf_counter()
        chunk_segments: list[tuple[int, list[dict]]] = []

        with make_bar(f"Transcribing  ({n_chunks} chunk(s))") as bar:
            for i, chunk_path in enumerate(chunks):
                chunk_lo = int(i * 100 / n_chunks)
                chunk_hi = int((i + 1) * 100 / n_chunks)
                chunk_w  = chunk_hi - chunk_lo
                bar.set_postfix_str(f"chunk {i + 1}/{n_chunks}")

                def transcribe_cb(
                    fraction: float,
                    _bar=bar, _lo=chunk_lo, _w=chunk_w,
                ) -> None:
                    _bar.n = _lo + int(fraction * _w)
                    _bar.refresh()

                segs = transcriber.transcribe_file(chunk_path, language=language, progress_cb=transcribe_cb)
                if segs is None:
                    db.mark_failed(job_id, f"transcription failed on chunk {i + 1}")
                    return None

                chunk_segments.append((i, segs))
                db.update_progress(job_id, int((i + 1) / n_chunks * 100))
                bar.n = chunk_hi
                bar.refresh()

        stage_times["transcribe"] = time.perf_counter() - t0

        # ── Merge and write ────────────────────────────────────────────────────
        t0 = time.perf_counter()
        with make_bar("Writing output") as bar:
            segments = merge_chunks(chunk_segments, chunk_seconds)
            stem = file_path.stem
            file_output_dir = output_dir / stem
            file_output_dir.mkdir(parents=True, exist_ok=True)
            written: list[str] = []

            for fmt in output_formats:
                if fmt == "txt":
                    out = file_output_dir / f"{stem}.txt"
                    fmt_txt.write_txt(segments, out)
                    written.append(str(out))
                elif fmt == "srt":
                    out = file_output_dir / f"{stem}.srt"
                    fmt_srt.write_srt(segments, out)
                    written.append(str(out))
                elif fmt == "json":
                    out = file_output_dir / f"{stem}.json"
                    fmt_json.write_json(segments, out)
                    written.append(str(out))

            bar.n = 100
            bar.refresh()
        stage_times["write"] = time.perf_counter() - t0

        stage_times["total"] = time.perf_counter() - t_job
        db.mark_completed(job_id, ",".join(written))
        logger.info(f"Output: {', '.join(written)}")
        return stage_times

    except Exception as e:
        logger.error(f"Error processing {file_path.name}: {e}")
        db.mark_failed(job_id, str(e))
        return None

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
