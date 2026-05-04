# Copilot Instructions

## Project Overview

`transcribe-cli` is a Python CLI tool that transcribes audio/video files using `faster-whisper` (CTranslate2-based Whisper). It processes files sequentially — one at a time in the main process — using ffmpeg for audio extraction and chunking.

**Runtime dependency:** `ffmpeg` must be installed and on `PATH`.

## Running the Tool

```bash
# Single file
python -m transcriber transcribe <file>

# Directory of media files
python -m transcriber transcribe <directory>

# Resume pending/failed jobs from the job database
python -m transcriber resume
```

Supported input formats: `.mp4`, `.mkv`, `.mp3`, `.wav`

## Architecture

### Pipeline (per file, sequential)

```
cli.py → _dispatch() → worker.process_file()
                           ├── ffmpeg_utils.extract_audio()   → 16kHz mono WAV in temp dir
                           ├── chunker.split_audio()           → fixed-length segments (default 600s)
                           ├── transcriber.Transcriber.transcribe_file()  → list[dict] per chunk
                           ├── _offset_segments()              → apply per-chunk time offset inline
                           └── formats/{txt,srt,json}          → incremental writes after each chunk
```

The `Transcriber` model is loaded **once** in `_dispatch()` and reused across all files. Temp files live in `tempfile.mkdtemp()` and are always cleaned up in a `finally` block.

### Job Persistence

Every file is registered in a SQLite DB at `~/.transcriber/jobs.db` before processing begins. On startup, any `in_progress` rows from previous crashes are reset to `pending`. `get_pending_jobs()` returns all pending rows globally; the `transcribe` command scopes them to the current input path.

```python
# Job scoping pattern in cli.py — prevents stale rows from other directories leaking in
scoped = {str(f) for f in files}
pending = [r for r in db.get_pending_jobs(include_failed=resume) if r["file_path"] in scoped]
```

The `resume` subcommand intentionally skips this filter to re-run all pending/failed jobs globally.

### Output Files

Each file gets its own subdirectory under `output_dir`:
```
outputs/
  <stem>/
    <stem>.txt
    <stem>.srt
    <stem>.json
```

TXT and SRT are **appended** chunk by chunk. JSON is **checkpoint-rewritten** (full accumulated list) after each chunk. This preserves partial output on interruption.

## Key Conventions

### Constants live in `config.py`
All defaults and valid values are defined there. Import from `config.py`; never hardcode values elsewhere.

```python
VALID_MODELS = ["tiny", "base", "small", "medium", "large"]
VALID_FORMATS = ["txt", "srt", "json"]
DEFAULT_MODEL = "small"
DEFAULT_CHUNK_SECONDS = 600
DEFAULT_BEAM_SIZE = 5
DB_PATH = Path.home() / ".transcriber" / "jobs.db"
```

### Progress bars via `make_bar()`

All pipeline stages use `utils.make_bar(desc)` — it prints a timestamped header line then returns a tqdm bar. **All logging must go through `tqdm.write()`** (handled automatically by `_TqdmHandler`) to avoid corrupting progress bars. Never use `print()` for log output inside pipeline stages.

```python
with make_bar("Stage description") as bar:
    # update bar.n directly, then bar.refresh()
    bar.n = int(pct)
    bar.refresh()
```

### GPU auto-detection

`Transcriber.__init__` calls `_detect_device()` which checks `ctranslate2.get_cuda_device_count()`. Result: `("cuda", "float16")` if GPU found, else `("cpu", "int8")`. Pass `device="auto"` (default) to use this.

### `merger.py` is vestigial
Time offset is applied inline in `worker.py` via `_offset_segments()`. Do not add calls to `merger.py`.

### ffmpeg progress reporting
`extract_audio()` uses `-progress pipe:1` to stream `out_time_ms=<N>` lines from stdout, while draining stderr on a daemon thread to prevent pipe blocking. This pattern is required for progress callbacks.

## Format Writers (`formats/`)

Each format has a `write_*` (full rewrite) and `append_*` (incremental) variant. `worker.py` always uses the `append_*` variants during the chunk loop.

| Format | Write strategy | Key detail |
|--------|---------------|------------|
| `txt`  | Append per chunk | Segments joined with a single space. `append_txt(..., first=True)` omits the leading space for the first chunk. |
| `srt`  | Append per chunk | `append_srt()` takes and returns a `start_index` counter so subtitle numbers are globally contiguous across chunks. |
| `json` | Full rewrite per chunk | `write_json()` serializes the entire `all_segs` list accumulated so far — no append variant. Always up-to-date on disk but rewrites grow with each chunk. |

**Segment dict shape** (shared across all formats):
```python
{"start": float, "end": float, "text": str}  # times in seconds, text already stripped
```

SRT timestamps use `,` as the millisecond separator (per spec): `HH:MM:SS,mmm`.

All output files are **created empty** before the chunk loop starts so partial content exists on disk even if the first chunk fails.

## DB Schema (`~/.transcriber/jobs.db`)

```sql
CREATE TABLE jobs (
    id          INTEGER PRIMARY KEY,
    file_path   TEXT    NOT NULL,        -- absolute path to source file
    status      TEXT    NOT NULL DEFAULT 'pending',  -- pending|in_progress|completed|failed
    progress    INTEGER NOT NULL DEFAULT 0,          -- 0–100, updated after each chunk
    output_path TEXT,                    -- comma-separated output file paths on success
    error       TEXT,                    -- error message on failure
    created_at  TEXT    NOT NULL         -- UTC ISO-8601 timestamp
)
```

**Invariants maintained by `init_db()`** (called on every startup):
1. Duplicate rows per `file_path` are pruned — only the latest `id` is kept.
2. Any `in_progress` row is reset to `pending` (crash recovery).

**`add_job()` skips** files whose status is anything other than `failed` — so `completed` and `pending` files are never re-queued unless `--force` is passed (which calls `force_reset()` first).

`output_path` stores multiple paths as a comma-separated string (e.g. `outputs/foo/foo.txt,outputs/foo/foo.srt`).

## Chunker Internals

`chunker.split_audio()` uses ffmpeg's **segment muxer** (`-f segment`) with `-c copy` (no re-encoding) to split the extracted WAV into `part_000.wav`, `part_001.wav`, etc. in the same temp directory.

```python
# Output pattern: <temp_dir>/part_%03d.wav
# Returns: sorted list of Paths matching part_*.wav
```

Key implications:
- Chunks are named `part_000.wav`, `part_001.wav`, … — the sort order of the glob is the processing order.
- `-c copy` means splitting is nearly instant regardless of file size.
- The per-chunk time offset applied in `worker._offset_segments()` is `i * chunk_seconds` (simple multiplication, not derived from the actual chunk file duration). This works correctly because the segment muxer produces exact-length chunks except possibly the last one — the last chunk's final segment will have a slightly off `end` time, but this is acceptable.
- All chunk files live in the same `tempfile.mkdtemp()` temp dir as the extracted WAV and are cleaned up together in the `finally` block of `process_file()`.

## Type Checking

`pyrightconfig.json` points Pylance to `.venv` with `typeCheckingMode: "basic"`. Python 3.10+ union syntax (`X | Y`) is used throughout.
