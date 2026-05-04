import logging
import shutil
import tempfile
import time
from pathlib import Path

from transcriber import db
from transcriber.chunker import split_audio
from transcriber.ffmpeg_utils import extract_audio
from transcriber.formats.json import write_json
from transcriber.formats.srt import append_srt
from transcriber.formats.txt import append_txt
from transcriber.transcriber import Transcriber
from transcriber.utils import make_bar

logger = logging.getLogger("transcriber")


def _offset_segments(segments: list[dict], offset: float) -> list[dict]:
    return [
        {"start": seg["start"] + offset, "end": seg["end"] + offset, "text": seg["text"]}
        for seg in segments
    ]


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
    Output files are written incrementally after each chunk so partial
    content is preserved if the job is interrupted.
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

        # ── Prepare output files (created empty so they exist on partial runs) ─
        n_chunks = len(chunks)
        stem = file_path.stem
        file_output_dir = output_dir / stem
        file_output_dir.mkdir(parents=True, exist_ok=True)

        txt_path  = (file_output_dir / f"{stem}.txt")  if "txt"  in output_formats else None
        srt_path  = (file_output_dir / f"{stem}.srt")  if "srt"  in output_formats else None
        json_path = (file_output_dir / f"{stem}.json") if "json" in output_formats else None

        for p in (txt_path, srt_path, json_path):
            if p:
                p.write_text("", encoding="utf-8")

        written = [str(p) for p in (txt_path, srt_path, json_path) if p]

        # ── Transcribe + write incrementally ───────────────────────────────────
        t0 = time.perf_counter()
        all_segs: list[dict] = []
        srt_idx = 1

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

                offset_segs = _offset_segments(segs, i * chunk_seconds)

                if txt_path:
                    append_txt(offset_segs, txt_path, first=(i == 0))
                if srt_path:
                    srt_idx = append_srt(offset_segs, srt_path, srt_idx)
                if json_path:
                    all_segs.extend(offset_segs)
                    write_json(all_segs, json_path)

                db.update_progress(job_id, int((i + 1) / n_chunks * 100))
                bar.n = chunk_hi
                bar.refresh()

        stage_times["transcribe"] = time.perf_counter() - t0

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
