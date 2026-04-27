import shutil
from pathlib import Path
from typing import Optional

import typer

from transcriber.config import DEFAULT_MODEL, DEFAULT_OUTPUT_DIR, VALID_MODELS
from transcriber.ffmpeg_utils import extract_audio
from transcriber.transcriber import Transcriber
from transcriber.utils import collect_media_files, setup_logging

app = typer.Typer(help="Transcribe audio/video files to text using faster-whisper.")


@app.command()
def transcribe(
    input_path: Path = typer.Argument(..., help="Path to a media file or directory."),
    model: str = typer.Option(DEFAULT_MODEL, help=f"Whisper model size: {VALID_MODELS}"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, help="Directory to save transcripts."),
    language: Optional[str] = typer.Option(None, help="Language code (e.g. en). Default: auto-detect."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    logger = setup_logging(verbose=verbose)

    if model not in VALID_MODELS:
        logger.error(f"Invalid model: {model}. Choose from {VALID_MODELS}")
        raise typer.Exit(code=1)

    if not input_path.exists():
        logger.error(f"Input path does not exist: {input_path}")
        raise typer.Exit(code=1)

    files = collect_media_files(input_path)
    if not files:
        logger.error(f"No supported media files found in: {input_path}")
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Found {len(files)} file(s) to process")

    transcriber = Transcriber(model_size=model)

    for file_path in files:
        logger.info(f"Processing file: {file_path.name}")

        logger.info("Extracting audio...")
        audio_path = extract_audio(file_path)
        if audio_path is None:
            continue

        try:
            logger.info("Transcribing...")
            text = transcriber.transcribe_file(audio_path, language=language)
            if text is None:
                continue

            out_file = output_dir / f"{file_path.stem}.txt"
            out_file.write_text(text, encoding="utf-8")
            logger.info(f"Saved: {out_file}")
        finally:
            temp_dir = audio_path.parent
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"Cleaned up temp dir: {temp_dir}")

    logger.info("Done.")


if __name__ == "__main__":
    app()
