import logging
import multiprocessing
import sqlite3
import threading
from pathlib import Path

import typer
from tqdm import tqdm

from transcriber import db
from transcriber.config import (
    DEFAULT_CHUNK_SECONDS,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_WORKERS,
    VALID_FORMATS,
    VALID_MODELS,
)
from transcriber.utils import collect_media_files, setup_logging
from transcriber.worker import _init_worker, process_job

app = typer.Typer(help="Transcribe audio/video files to text using faster-whisper.")


def _parse_output_formats(output: str, logger: logging.Logger) -> list[str]:
    formats = [f.strip() for f in output.split(",")]
    invalid = [f for f in formats if f not in VALID_FORMATS]
    if invalid:
        logger.error(f"Invalid output format(s): {invalid}. Choose from {VALID_FORMATS}")
        raise typer.Exit(code=1)
    return formats


def _dispatch(
    jobs: list[sqlite3.Row],
    workers: int,
    model: str,
    language: str | None,
    chunk_seconds: int,
    output_formats: list[str],
    output_dir: Path,
    verbose: bool,
) -> None:
    logger = logging.getLogger("transcriber")
    total = len(jobs)
    effective_workers = min(workers, total)
    logger.info(f"Dispatching {total} job(s) across {effective_workers} worker(s)")

    with multiprocessing.Manager() as manager:
        progress_queue = manager.Queue()

        job_args = [
            (i, total, row["id"], row["file_path"], language, chunk_seconds, output_formats, str(output_dir), progress_queue)
            for i, row in enumerate(jobs, start=1)
        ]

        with multiprocessing.Pool(
            processes=effective_workers,
            initializer=_init_worker,
            initargs=(model, "int8", verbose),
        ) as pool:
            with tqdm(total=total, desc="Transcribing", unit="file", dynamic_ncols=True) as pbar:
                stop_event = threading.Event()

                def _drain_progress() -> None:
                    while not stop_event.is_set():
                        try:
                            filename, chunk_idx, n_chunks = progress_queue.get(timeout=0.3)
                            pbar.set_postfix_str(f"{filename} [{chunk_idx}/{n_chunks} chunks]")
                        except Exception:
                            pass

                drainer = threading.Thread(target=_drain_progress, daemon=True)
                drainer.start()
                try:
                    for filename in pool.imap_unordered(process_job, job_args):
                        pbar.set_postfix_str(filename)
                        pbar.update(1)
                finally:
                    stop_event.set()
                    drainer.join(timeout=1)


@app.command()
def transcribe(
    input_path: Path = typer.Argument(..., help="Path to a media file or directory."),
    model: str = typer.Option(DEFAULT_MODEL, help=f"Whisper model size: {VALID_MODELS}"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Directory to save transcripts."),
    language: str | None = typer.Option(None, help="Language code (e.g. en). Default: auto-detect."),
    workers: int = typer.Option(DEFAULT_WORKERS, help="Number of parallel worker processes."),
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

    pending = db.get_pending_jobs(include_failed=resume)
    if not pending:
        logger.info("No pending jobs.")
        raise typer.Exit()

    _dispatch(pending, workers, model, language, chunk, output_formats, output_dir, verbose)


@app.command()
def resume(
    model: str = typer.Option(DEFAULT_MODEL, help=f"Whisper model size: {VALID_MODELS}"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Directory to save transcripts."),
    language: str | None = typer.Option(None, help="Language code (e.g. en). Default: auto-detect."),
    workers: int = typer.Option(DEFAULT_WORKERS, help="Number of parallel worker processes."),
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
    _dispatch(pending, workers, model, language, chunk, output_formats, output_dir, verbose)
