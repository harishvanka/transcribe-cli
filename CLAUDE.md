# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`transcribe-cli` is a Python CLI tool that transcribes audio/video files to text using `faster-whisper` (a CTranslate2-based Whisper implementation). It accepts a single file or a directory of media files and writes transcripts to an output directory in one or more formats (`.txt`, `.srt`, `.json`).

External runtime dependency: **ffmpeg** must be installed and on `PATH`.

## Running the CLI

```bash
# Single file
python -m transcriber transcribe <file>

# Directory of media files
python -m transcriber transcribe <directory>

# Common options
python -m transcriber transcribe <file> \
  --model small|medium|large|base|tiny \
  --output-dir ./outputs \
  --language en \
  --chunk 600 \
  --output txt,srt,json \
  --beam-size 5 \
  --vad \
  --force \
  --resume \
  -v

# Resume pending/failed jobs from the job database
python -m transcriber resume
```

Supported input formats: `.mp4`, `.mkv`, `.mp3`, `.wav`.

## Architecture

The CLI exposes two subcommands (`transcribe` and `resume`) via a Typer multi-command app. Processing is **sequential** — one file at a time in the main process. This eliminates the complexity of multiprocessing and allows tqdm progress bars and logging to coexist cleanly.

### `transcribe` pipeline (sequential, per file)

1. `cli.py` — Validates args, collects media files, registers jobs in the SQLite DB, then calls `_dispatch()`.
2. `_dispatch()` in `cli.py` — Loads the `Transcriber` model once, then iterates jobs sequentially. Prints media info before each file. Prints a timing summary after each file.
3. `worker.process_file()` — Orchestrates the full per-file pipeline with stage-level tqdm progress bars.
4. `ffmpeg_utils.extract_audio()` — Converts the input file to a 16 kHz mono WAV in a temp directory. Streams `-progress pipe:1` output for per-stage progress reporting.
5. `chunker.split_audio()` — Splits the WAV into fixed-length segments (default 600 s) using ffmpeg's segment muxer.
6. `transcriber.Transcriber.transcribe_file()` — Transcribes each chunk lazily (generator), calling `progress_cb` after each segment. Returns `list[dict]` with `start`, `end`, `text` per segment.
7. **Inline offset** in `worker.py` — Applies the per-chunk time offset immediately after transcription (`_offset_segments()`). No separate merge step.
8. **Incremental writers** (`formats/txt.py`, `formats/srt.py`, `formats/json.py`) — Write output after each chunk so partial content is preserved on interruption. TXT and SRT append; JSON checkpoint-rewrites the full accumulated list.
9. `db.mark_completed()` / `db.mark_failed()` — Records final job status and output paths.

### `resume` subcommand

Calls `db.get_pending_jobs(include_failed=True)` and dispatches the same `_dispatch()` function without re-scanning the filesystem.

### Job scoping

`get_pending_jobs()` returns all pending rows globally. The `transcribe` command filters these to only files in the current input path:

```python
scoped = {str(f) for f in files}
pending = [r for r in db.get_pending_jobs(include_failed=resume) if r["file_path"] in scoped]
```

This prevents stale rows from previous runs on other directories from leaking into the current run. The `resume` subcommand intentionally skips this filter.

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

On startup, `in_progress` rows left over from a previous crash are reset to `pending`.

### Progress bars

`utils.make_bar(desc, total=100)` is a factory that returns a consistently-styled tqdm bar. All three pipeline stages (extract, split, transcribe) use it as a context manager. Logging is routed through `tqdm.write()` via `_TqdmHandler` so log lines never corrupt the bars.

### Hardware auto-detection

`Transcriber.__init__` calls `_detect_device()` which checks `ctranslate2.get_cuda_device_count()`. If a CUDA GPU is present it returns `("cuda", "float16")`; otherwise `("cpu", "int8")`. `cpu_threads=0` lets CTranslate2 use all available cores.

## Module map

| File | Responsibility |
|---|---|
| `config.py` | Single source of truth for all constants (models, formats, defaults, DB path) |
| `cli.py` | Typer entrypoint; argument validation; job registration; sequential dispatch |
| `worker.py` | Per-file pipeline orchestration with stage tqdm bars and incremental writes |
| `db.py` | SQLite job persistence |
| `chunker.py` | ffmpeg-based audio splitting |
| `merger.py` | Vestigial — no longer called; time offset is applied inline in `worker.py` |
| `transcriber.py` | `WhisperModel` wrapper with GPU auto-detection, lazy generator transcription |
| `ffmpeg_utils.py` | Audio extraction; `MediaInfo` dataclass; `probe_media_info()` (parses `ffmpeg -i` stderr) |
| `formats/txt.py` | Plain-text writer (`write_txt`, `append_txt`) |
| `formats/srt.py` | SubRip writer (`write_srt`, `append_srt`) |
| `formats/json.py` | JSON writer (`write_json`, checkpoint-writes after each chunk) |
| `utils.py` | `make_bar()` factory, `_TqdmHandler`, `setup_logging()`, `collect_media_files()` |

## Key constants (`config.py`)

| Constant | Value | Notes |
|---|---|---|
| `VALID_MODELS` | `["tiny","base","small","medium","large"]` | |
| `VALID_FORMATS` | `["txt","srt","json"]` | |
| `DEFAULT_MODEL` | `"small"` | |
| `DEFAULT_COMPUTE_TYPE` | `"auto"` | CTranslate2 picks best for device |
| `DEFAULT_BEAM_SIZE` | `5` | Reduce to 1–2 for ~2× CPU speedup |
| `DEFAULT_CHUNK_SECONDS` | `600` | 10-minute chunks |
| `DB_PATH` | `~/.transcriber/jobs.db` | |

## IDE / type checking

`pyrightconfig.json` at the project root points Pylance to the `.venv` virtual environment:

```json
{
  "venvPath": ".",
  "venv": ".venv",
  "pythonVersion": "3.11",
  "typeCheckingMode": "basic"
}
```

## No build system

There is no `pyproject.toml`, `setup.py`, or `requirements.txt` committed yet. Install dependencies manually:

```bash
pip install typer faster-whisper
```

## Reference

`CONCEPTS.md` at the project root documents the reusable patterns in this codebase (progress bar factory, tqdm-safe logging, stage pipeline, SQLite job persistence, subprocess progress, lazy generator progress, incremental writes, GPU auto-detection, chunking, multi-format output, media probing).
