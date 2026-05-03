import logging
import sqlite3
import time
from pathlib import Path

import typer

from transcriber import db
from transcriber.config import (
    DEFAULT_CHUNK_SECONDS,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_WORKERS,
    VALID_FORMATS,
    VALID_MODELS,
)
from transcriber.ffmpeg_utils import MediaInfo, probe_media_info
from transcriber.transcriber import Transcriber
from transcriber.utils import collect_media_files, setup_logging
from transcriber.worker import process_file

app = typer.Typer(help="Transcribe audio/video files to text using faster-whisper.")


def _fmt_sec(s: float) -> str:
    if s < 60:
        return f"{s:.1f}s"
    m, rem = divmod(int(s), 60)
    return f"{m}m{rem:02d}s"


def _fmt_done(filename: str, times: dict[str, float]) -> str:
    labels = [("extract", "demux"), ("split", "split"), ("transcribe", "transcribe"), ("write", "write")]
    parts = [f"{lbl}={_fmt_sec(times[k])}" for k, lbl in labels if k in times]
    return f"  [done] {filename}  {' | '.join(parts)}  total={_fmt_sec(times.get('total', 0))}"


def _print_media_info(file_path: Path, info: MediaInfo) -> None:
    sep = "─" * 48
    lines = [
        sep,
        f"  File:        {file_path.name}",
        f"  Size:        {info.file_size_str}",
        f"  Duration:    {info.duration_str}",
    ]
    if info.resolution:
        fps_str = f"  @  {info.fps:.3f} fps" if info.fps else ""
        lines.append(f"  Resolution:  {info.resolution}{fps_str}")
    if info.video_codec:
        lines.append(f"  Video:       {info.video_codec.upper()}")
    if info.audio_codec:
        lines.append(f"  Audio:       {info.audio_codec.upper()}")
    if info.bitrate_kbps:
        lines.append(f"  Bitrate:     {info.bitrate_kbps:,} kb/s")
    lines.append(sep)
    print("\n".join(lines))


def _parse_output_formats(output: str, logger: logging.Logger) -> list[str]:
    formats = [f.strip() for f in output.split(",")]
    invalid = [f for f in formats if f not in VALID_FORMATS]
    if invalid:
        logger.error(f"Invalid output format(s): {invalid}. Choose from {VALID_FORMATS}")
        raise typer.Exit(code=1)
    return formats


def _dispatch(
    jobs: list[sqlite3.Row],
    model: str,
    language: str | None,
    chunk_seconds: int,
    output_formats: list[str],
    output_dir: Path,
) -> None:
    logger = logging.getLogger("transcriber")
    total = len(jobs)

    transcriber = Transcriber(model_size=model, compute_type="int8")

    t_all = time.perf_counter()
    succeeded = 0

    for idx, row in enumerate(jobs, 1):
        file_path = Path(row["file_path"])

        if total > 1:
            print(f"\n── {idx}/{total}: {file_path.name} ──")

        info = probe_media_info(file_path)
        _print_media_info(file_path, info)
        print()

        times = process_file(
            job_id=row["id"],
            file_path=file_path,
            language=language,
            chunk_seconds=chunk_seconds,
            output_formats=output_formats,
            output_dir=output_dir,
            transcriber=transcriber,
        )

        if times is not None:
            print(_fmt_done(file_path.name, times))
            succeeded += 1
        else:
            logger.error(f"Failed: {file_path.name}")

        print()

    if total > 1:
        elapsed = time.perf_counter() - t_all
        print(f"Finished {succeeded}/{total} file(s) in {_fmt_sec(elapsed)}")


@app.command()
def transcribe(
    input_path: Path = typer.Argument(..., help="Path to a media file or directory."),
    model: str = typer.Option(DEFAULT_MODEL, help=f"Whisper model size: {VALID_MODELS}"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Directory to save transcripts."),
    language: str | None = typer.Option(None, help="Language code (e.g. en). Default: auto-detect."),
    workers: int = typer.Option(DEFAULT_WORKERS, help="(Unused — processing is sequential)"),
    chunk: int = typer.Option(DEFAULT_CHUNK_SECONDS, "--chunk", help="Chunk size in seconds."),
    output: str = typer.Option("txt,srt,json", help="Comma-separated output formats: txt,srt,json"),
    resume: bool = typer.Option(False, "--resume", help="Also re-run previously failed jobs."),
    force: bool = typer.Option(False, "--force", help="Re-transcribe already completed files."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    logger = setup_logging(verbose=verbose)

    if model not in VALID_MODELS:
        logger.error(f"Invalid model '{model}'. Choose from {VALID_MODELS}")
        raise typer.Exit(code=1)

    if not input_path.exists():
        logger.error(f"Input path does not exist: {input_path}")
        raise typer.Exit(code=1)

    output_formats = _parse_output_formats(output, logger)

    files = collect_media_files(input_path)
    if not files:
        logger.error(f"No supported media files found in: {input_path}")
        raise typer.Exit(code=1)

    db.init_db()

    if force:
        reset = db.force_reset([str(f) for f in files])
        logger.info(f"Force-reset {reset} existing job(s) to pending")

    new_count = sum(1 for f in files if db.add_job(str(f)) is not None)
    skipped = len(files) - new_count
    logger.info(f"Queued {new_count} new file(s), skipped {skipped} already in queue")

    scoped = {str(f) for f in files}
    pending = [r for r in db.get_pending_jobs(include_failed=resume) if r["file_path"] in scoped]
    if not pending:
        logger.info("No pending jobs.")
        raise typer.Exit()

    _dispatch(pending, model, language, chunk, output_formats, output_dir)


@app.command()
def resume(
    model: str = typer.Option(DEFAULT_MODEL, help=f"Whisper model size: {VALID_MODELS}"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Directory to save transcripts."),
    language: str | None = typer.Option(None, help="Language code (e.g. en). Default: auto-detect."),
    chunk: int = typer.Option(DEFAULT_CHUNK_SECONDS, "--chunk", help="Chunk size in seconds."),
    output: str = typer.Option("txt,srt,json", help="Comma-separated output formats: txt,srt,json"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    logger = setup_logging(verbose=verbose)

    db.init_db()
    output_formats = _parse_output_formats(output, logger)

    pending = db.get_pending_jobs(include_failed=True)
    if not pending:
        logger.info("No pending or failed jobs to resume.")
        raise typer.Exit()

    logger.info(f"Resuming {len(pending)} job(s)")
    _dispatch(pending, DEFAULT_MODEL, None, DEFAULT_CHUNK_SECONDS, output_formats, output_dir)
