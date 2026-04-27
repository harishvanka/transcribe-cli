import logging
import multiprocessing
from pathlib import Path
from typing import Optional

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
from transcriber.utils import collect_media_files, setup_logging
from transcriber.worker import _init_worker, process_job

app = typer.Typer(help="Transcribe audio/video files to text using faster-whisper.")


def _dispatch(
    jobs: list,
    workers: int,
    model: str,
    language: Optional[str],
    chunk_seconds: int,
    output_formats: list[str],
    output_dir: Path,
    verbose: bool,
) -> None:
    logger = logging.getLogger("transcriber")
    total = len(jobs)
    logger.info(f"Dispatching {total} job(s) across {workers} worker(s)")

    job_args = [
        (i, total, row["id"], row["file_path"], language, chunk_seconds, output_formats, str(output_dir))
        for i, row in enumerate(jobs, start=1)
    ]

    with multiprocessing.Pool(
        processes=workers,
        initializer=_init_worker,
        initargs=(model, "int8", verbose),
    ) as pool:
        pool.map(process_job, job_args)


@app.command()
def transcribe(
    input_path: Path = typer.Argument(..., help="Path to a media file or directory."),
    model: str = typer.Option(DEFAULT_MODEL, help=f"Whisper model size: {VALID_MODELS}"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Directory to save transcripts."),
    language: Optional[str] = typer.Option(None, help="Language code (e.g. en). Default: auto-detect."),
    workers: int = typer.Option(DEFAULT_WORKERS, help="Number of parallel worker processes."),
    chunk: int = typer.Option(DEFAULT_CHUNK_SECONDS, "--chunk", help="Chunk size in seconds."),
    output: str = typer.Option("txt", help="Comma-separated output formats: txt,srt,json"),
    resume: bool = typer.Option(False, "--resume", help="Also re-run previously failed jobs."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    logger = setup_logging(verbose=verbose)

    if model not in VALID_MODELS:
        logger.error(f"Invalid model '{model}'. Choose from {VALID_MODELS}")
        raise typer.Exit(code=1)

    if not input_path.exists():
        logger.error(f"Input path does not exist: {input_path}")
        raise typer.Exit(code=1)

    output_formats = [f.strip() for f in output.split(",")]
    invalid = [f for f in output_formats if f not in VALID_FORMATS]
    if invalid:
        logger.error(f"Invalid output format(s): {invalid}. Choose from {VALID_FORMATS}")
        raise typer.Exit(code=1)

    files = collect_media_files(input_path)
    if not files:
        logger.error(f"No supported media files found in: {input_path}")
        raise typer.Exit(code=1)

    db.init_db()
    for file_path in files:
        db.add_job(str(file_path))
    logger.info(f"Added {len(files)} file(s) to job queue")

    pending = db.get_pending_jobs(include_failed=resume)
    if not pending:
        logger.info("No pending jobs.")
        raise typer.Exit()

    _dispatch(pending, workers, model, language, chunk, output_formats, output_dir, verbose)


@app.command()
def resume(
    model: str = typer.Option(DEFAULT_MODEL, help=f"Whisper model size: {VALID_MODELS}"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Directory to save transcripts."),
    language: Optional[str] = typer.Option(None, help="Language code (e.g. en). Default: auto-detect."),
    workers: int = typer.Option(DEFAULT_WORKERS, help="Number of parallel worker processes."),
    chunk: int = typer.Option(DEFAULT_CHUNK_SECONDS, "--chunk", help="Chunk size in seconds."),
    output: str = typer.Option("txt", help="Comma-separated output formats: txt,srt,json"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    logger = setup_logging(verbose=verbose)

    db.init_db()
    output_formats = [f.strip() for f in output.split(",")]

    pending = db.get_pending_jobs(include_failed=True)
    if not pending:
        logger.info("No pending or failed jobs to resume.")
        raise typer.Exit()

    logger.info(f"Resuming {len(pending)} job(s)")
    _dispatch(pending, workers, model, language, chunk, output_formats, output_dir, verbose)
