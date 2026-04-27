# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`transcribe-cli` is a Python CLI tool that transcribes audio/video files to text using `faster-whisper` (a CTranslate2-based Whisper implementation). It accepts a single file or a directory of media files and writes transcripts to an output directory in one or more formats (`.txt`, `.srt`, `.json`).

External runtime dependency: **ffmpeg** must be installed and on `PATH`.

## Running the CLI

```bash
# Single file
python -m transcriber transcribe <file> [--model small|medium|large] [--output-dir ./outputs] [--language en] [--workers 2] [--chunk 600] [--output txt,srt,json] [-v]

# Directory of media files
python -m transcriber transcribe <directory>

# Resume pending/failed jobs from the job database
python -m transcriber resume
```

Supported input formats: `.mp4`, `.mkv`, `.mp3`, `.wav`.

## Architecture

The CLI exposes two subcommands (`transcribe` and `resume`) via a Typer multi-command app.

### `transcribe` pipeline (per file, run in parallel workers)

1. `cli.py` — Validates args, collects media files, registers jobs in the SQLite DB, then dispatches a `multiprocessing.Pool`.
2. `worker.process_job()` — Entry point for each worker process. Orchestrates the per-file pipeline.
3. `ffmpeg_utils.extract_audio()` — Converts the input file to a 16 kHz mono WAV in a temp directory.
4. `chunker.split_audio()` — Splits the WAV into fixed-length segments (default 600 s) using ffmpeg's segment muxer.
5. `transcriber.Transcriber.transcribe_file()` — Transcribes each chunk; returns `list[dict]` with `start`, `end`, `text` per segment. The `WhisperModel` is loaded once per worker process and reused across all chunks.
6. `merger.merge_chunks()` — Reassembles chunk segments into a single timeline by applying a per-chunk time offset.
7. Format writers (`formats/txt.py`, `formats/srt.py`, `formats/json.py`) — Write the merged segments to the requested output formats.
8. `db.mark_completed()` / `db.mark_failed()` — Records final job status and output paths.

### `resume` subcommand

Calls `db.get_pending_jobs(include_failed=True)` and dispatches the same `_dispatch()` pool without re-scanning the filesystem.

### Job database

`db.py` manages a SQLite database at `~/.transcriber/jobs.db`. Schema:

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | auto-increment |
| `file_path` | TEXT | absolute path to the source file |
| `status` | TEXT | `pending` / `in_progress` / `completed` / `failed` |
| `progress` | INTEGER | 0–100, updated after each chunk |
| `output_path` | TEXT | comma-separated output file paths on success |
| `error` | TEXT | error message on failure |
| `created_at` | TEXT | UTC ISO-8601 timestamp |

`add_job()` is idempotent in the sense that re-running `transcribe` over the same directory will insert new rows, but `get_pending_jobs()` only returns `pending` (or `failed` when `--resume` is set), so already-completed files are naturally skipped.

## Module map

| File | Responsibility |
|---|---|
| `config.py` | Single source of truth for all constants (models, formats, defaults, DB path) |
| `cli.py` | Typer entrypoint; argument validation; job registration; pool dispatch |
| `worker.py` | Per-job pipeline orchestration inside a worker process |
| `db.py` | SQLite job persistence |
| `chunker.py` | ffmpeg-based audio splitting |
| `merger.py` | Timestamp-corrected segment reassembly |
| `transcriber.py` | `WhisperModel` wrapper; returns `list[dict]` per audio file |
| `ffmpeg_utils.py` | Audio extraction to 16 kHz mono WAV |
| `formats/txt.py` | Plain-text writer |
| `formats/srt.py` | SubRip writer |
| `formats/json.py` | JSON writer |
| `utils.py` | `collect_media_files()`, `setup_logging()` |

## No build system

There is no `pyproject.toml`, `setup.py`, or `requirements.txt` committed yet. Install dependencies manually:

```bash
pip install typer faster-whisper
```
