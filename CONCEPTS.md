# Python CLI Tool — Reusable Concepts

Patterns and techniques used in `transcribe-cli` that apply to any
data-processing CLI tool built in Python.

---

## 1. CLI Framework — Typer with Subcommands

**What:** Typer wraps Python type annotations into a fully featured CLI with
`--help`, validation, and tab-completion.

**Pattern:**
```python
import typer
from pathlib import Path

app = typer.Typer(help="One-line description of the tool.")

@app.command()
def process(
    input_path: Path = typer.Argument(..., help="Input file or directory."),
    model: str  = typer.Option("small", help="Model size: small|medium|large"),
    force: bool = typer.Option(False, "--force", help="Re-run completed jobs."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    ...

@app.command()
def resume(...) -> None:   # second subcommand
    ...

if __name__ == "__main__":
    app()
```

**Key rules:**
- `typer.Argument` = positional; `typer.Option` = flag.
- Use `Path` type — Typer converts the string automatically.
- Raise `typer.Exit(code=1)` on validation errors instead of `sys.exit`.
- Keep validation (model name, format list) in the command handler, before
  any expensive work starts.

---

## 2. Progress Bar Factory — `make_bar()`

**What:** Define one factory function that returns a consistently-styled `tqdm`
bar. Call it everywhere instead of repeating tqdm kwargs.

**Pattern (`utils.py`):**
```python
from tqdm import tqdm

_BAR_ASCII = "-█"
_BAR_FMT   = "  {desc:<34} [{bar}] {percentage:3.0f}%  [{elapsed}]"

def make_bar(desc: str, total: int = 100) -> tqdm:
    return tqdm(
        total=total,
        desc=desc[:34],
        ascii=_BAR_ASCII,
        bar_format=_BAR_FMT,
        dynamic_ncols=True,
        leave=True,
    )
```

**Usage as a context manager:**
```python
with make_bar("Extracting audio") as bar:
    for chunk in stream:
        process(chunk)
        bar.n = percent_done
        bar.refresh()
    bar.n = 100          # ensure 100% on exit
    bar.refresh()
# bar.close() is called automatically; bar stays on screen (leave=True)
```

**Key rules:**
- `leave=True` → bar stays visible after completion (acts as a log line).
- `leave=False` → bar disappears (use for sub-tasks inside a larger bar).
- Always end with `bar.n = 100; bar.refresh()` so the bar closes at 100%.
- Never mix tqdm bars and regular `print()` — use `tqdm.write()` for any
  text output while bars are active.

---

## 3. Logging That Doesn't Break Progress Bars

**What:** Python's default `logging.StreamHandler` writes to stderr, which
conflicts with tqdm bars and produces garbled output. Route log lines through
`tqdm.write()` instead.

**Pattern (`utils.py`):**
```python
import logging
from tqdm import tqdm

class _TqdmHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            tqdm.write(self.format(record))
        except Exception:
            self.handleError(record)

def setup_logging(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger("mytool")
    logger.setLevel(level)
    if not logger.handlers:
        handler = _TqdmHandler()
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    return logger
```

Call `setup_logging(verbose)` once at the start of each CLI command.

---

## 4. Stage-Based Pipeline

**What:** Break a multi-step job into named stages. Each stage owns a progress
bar and records its elapsed time. Return a timing dict for the summary line.

**Pattern:**
```python
import time

def process_file(...) -> dict[str, float] | None:
    t_job = time.perf_counter()
    stage_times: dict[str, float] = {}

    # Stage 1
    t0 = time.perf_counter()
    with make_bar("Stage 1: Extract") as bar:
        result = run_stage_1(progress_cb=lambda pct: setbar(bar, pct))
        bar.n = 100; bar.refresh()
    stage_times["extract"] = time.perf_counter() - t0
    if result is None:
        return None   # early exit on failure

    # Stage 2
    t0 = time.perf_counter()
    with make_bar("Stage 2: Transform") as bar:
        ...
    stage_times["transform"] = time.perf_counter() - t0

    stage_times["total"] = time.perf_counter() - t_job
    return stage_times

def _fmt_summary(filename: str, times: dict) -> str:
    parts = [f"{k}={_fmt_sec(v)}" for k, v in times.items() if k != "total"]
    return f"[done] {filename}  {' | '.join(parts)}  total={_fmt_sec(times['total'])}"
```

**Key rules:**
- Return `None` on failure so the caller can count successes.
- Separate "did it work" (`None` vs dict) from "what went wrong" (logged inside).
- Print the timing summary after `process_file` returns — not inside it.

---

## 5. SQLite Job Persistence

**What:** Track every file as a job in a local SQLite database. This gives
you resume-on-crash, skip-completed, and progress history for free.

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY,
    file_path   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending|in_progress|completed|failed
    progress    INTEGER NOT NULL DEFAULT 0,        -- 0-100
    output_path TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL
);
```

**Lifecycle:**
```
add_job()          → status = pending
update_status()    → status = in_progress   (job starts)
update_progress()  → progress = 0..100      (each chunk)
mark_completed()   → status = completed     (success)
mark_failed()      → status = failed        (error message stored)
```

**Crash recovery** — call this on startup so stale `in_progress` rows
(from a previous crash) are reset to `pending`:
```python
conn.execute("UPDATE jobs SET status = 'pending' WHERE status = 'in_progress'")
```

**Scoping to current input** — `get_pending_jobs()` returns ALL pending rows
globally. When a CLI command operates on a specific directory, filter to only
those files; otherwise stale jobs from previous runs on other directories
bleed in:
```python
scoped = {str(f) for f in files}
pending = [r for r in db.get_pending_jobs() if r["file_path"] in scoped]
```

The `resume` subcommand intentionally skips this filter — it replays the full
global history.

---

## 6. Subprocess Progress Reporting

**What:** Long-running subprocess tools (ffmpeg, ffprobe, etc.) can stream
progress back to Python if you pass `-progress pipe:1`. Parse `out_time_ms=`
lines to get a percentage.

**Pattern:**
```python
import re, subprocess, threading

def run_with_progress(cmd: list[str], duration_sec: float,
                      progress_cb) -> bool:
    # Append -progress pipe:1 to cmd before the output path
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    # Drain stderr in background to prevent buffer deadlock
    def _drain():
        for _ in proc.stderr:
            pass
    threading.Thread(target=_drain, daemon=True).start()

    for line in proc.stdout:
        m = re.match(r"out_time_ms=(\d+)", line.strip())
        if m:
            pct = min(int(m.group(1)) / (duration_sec * 1_000_000) * 100, 99.0)
            progress_cb(pct)
    proc.wait()
    return proc.returncode == 0
```

**Getting duration without ffprobe:**  
`ffmpeg -i file` always exits with code 1 (no output file) but prints file
info to stderr, including the `Duration:` field:
```python
result = subprocess.run(["ffmpeg", "-i", str(path)], capture_output=True, text=True)
m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", result.stderr)
```

---

## 7. Streaming / Lazy Generator Progress

**What:** Some libraries return a lazy generator (e.g., `faster-whisper`
returns transcription segments one at a time). Consuming the generator eagerly
with a list comprehension loses the ability to report mid-stream progress.

**Anti-pattern (no progress):**
```python
segments = list(model.transcribe(audio))   # blocks until 100% done
```

**Correct pattern (progress per segment):**
```python
segments_gen, info = model.transcribe(audio)
total = info.duration          # available immediately
result = []
for seg in segments_gen:       # generator is evaluated lazily
    result.append(seg)
    if progress_cb:
        progress_cb(seg.end / total)   # call after each segment
```

Apply to any library that uses generators for streaming results.

---

## 8. Incremental Output Writing

**What:** Write output files chunk-by-chunk so that partial content is saved
if the job is interrupted. Requires append-mode writers for each format.

**Pattern — create files empty before the loop:**
```python
output_path.write_text("", encoding="utf-8")   # file exists even on crash
```

**Text (TXT) — append with separator:**
```python
def append_txt(segments, path, first=False):
    text = " ".join(s["text"] for s in segments)
    with path.open("a", encoding="utf-8") as f:
        if not first:
            f.write(" ")
        f.write(text)
```

**Subtitle (SRT) — append with running index:**
```python
def append_srt(segments, path, start_index=1) -> int:
    lines = []
    idx = start_index
    for seg in segments:
        lines += [str(idx), f"{ts(seg['start'])} --> {ts(seg['end'])}", seg["text"], ""]
        idx += 1
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return idx    # caller threads this through the loop
```

**JSON — checkpoint-write (full overwrite of accumulated list):**
```python
all_segs = []
for chunk in chunks:
    segs = transcribe(chunk)
    all_segs.extend(apply_offset(segs, chunk_offset))
    json_path.write_text(json.dumps(all_segs, indent=2), encoding="utf-8")
    # JSON file is always valid and grows after each chunk
```

---

## 9. Load-Once Expensive Resources

**What:** Models, database connections, and compiled objects are expensive to
initialise. Load them once before the processing loop and reuse across all
files.

**Anti-pattern:**
```python
for file in files:
    model = load_model()          # reloaded every iteration
    transcribe(file, model)
```

**Correct pattern:**
```python
model = load_model()              # once
for file in files:
    transcribe(file, model)
```

In a CLI tool, do this in the `_dispatch()` function, before iterating jobs.

---

## 10. GPU / Hardware Auto-Detection

**What:** Detect the fastest available hardware and configure the library
accordingly, with an explicit CPU fallback.

**Pattern:**
```python
def _detect_device() -> tuple[str, str]:
    """Return (device, compute_type)."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"
```

Use in the resource constructor:
```python
device, compute_type = _detect_device()
model = WhisperModel(size, device=device, compute_type=compute_type, cpu_threads=0)
```

`cpu_threads=0` tells CTranslate2 to use all available CPU cores.

Log what was selected so the user knows what hardware is in use:
```python
logger.info(f"device={device} compute={compute_type}")
```

---

## 11. Chunking Large Inputs

**What:** Split a large file into fixed-size segments so that memory usage is
bounded and progress can be reported after each segment.

**Why:** A 3-hour audio file as one unit gives a single, opaque progress
update at the end. 45 × 5-minute chunks give 45 progress ticks and a
recoverable partial result if interrupted.

**Pattern:**
```python
# Use ffmpeg's segment muxer
cmd = [
    "ffmpeg", "-i", str(input_wav),
    "-f", "segment",
    "-segment_time", str(chunk_seconds),
    "-c", "copy",
    str(out_pattern),
    "-y",
]
subprocess.run(cmd, check=True, capture_output=True)
chunks = sorted(input_wav.parent.glob("part_*.wav"))
```

**Applying time offset after reassembly:**
```python
def apply_offset(segments, chunk_index, chunk_seconds):
    offset = chunk_index * chunk_seconds
    return [{"start": s["start"] + offset, "end": s["end"] + offset, "text": s["text"]}
            for s in segments]
```

---

## 12. Multiple Output Formats from One Pipeline

**What:** Run the pipeline once and write results in N formats. Separate
format writers into their own modules so each can be independently tested
and extended.

**Structure:**
```
formats/
    txt.py    write_txt(segments, path), append_txt(segments, path, first)
    srt.py    write_srt(segments, path), append_srt(segments, path, start_idx) -> int
    json.py   write_json(segments, path)
```

**Dispatch in the pipeline:**
```python
FORMAT_WRITERS = {
    "txt":  lambda segs, p: append_txt(segs, p),
    "srt":  lambda segs, p: append_srt(segs, p, srt_idx),
    "json": lambda segs, p: write_json(all_segs, p),
}
for fmt in output_formats:
    FORMAT_WRITERS[fmt](offset_segs, output_paths[fmt])
```

**Key rules:**
- Validate format names against `VALID_FORMATS` in the CLI handler, before
  any processing starts.
- Create output files empty (`path.write_text("")`) before the loop so they
  exist even on failure.
- For formats that cannot be appended (JSON), accumulate in memory and
  checkpoint-write the whole file after each chunk.

---

## 13. Media Info Probing

**What:** Show the user key metadata (duration, resolution, codec, bitrate)
before processing starts, so they can confirm the right file is being used.

**Pattern — parse `ffmpeg -i` stderr (no ffprobe needed):**
```python
import re, subprocess
from dataclasses import dataclass
from pathlib import Path

@dataclass
class MediaInfo:
    duration_sec: float | None = None
    resolution: str | None = None
    fps: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    bitrate_kbps: int | None = None
    file_size_bytes: int = 0

def probe_media_info(file_path: Path) -> MediaInfo:
    info = MediaInfo(file_size_bytes=file_path.stat().st_size)
    result = subprocess.run(
        ["ffmpeg", "-i", str(file_path)],
        capture_output=True, text=True, timeout=30,
    )
    s = result.stderr
    if m := re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", s):
        h, mn, sec = int(m[1]), int(m[2]), float(m[3])
        info.duration_sec = h * 3600 + mn * 60 + sec
    if m := re.search(r"Video:\s*(\w+).*?(\d{2,4})x(\d{2,4}).*?([\d.]+)\s+fps", s):
        info.video_codec, info.resolution = m[1], f"{m[2]}x{m[3]}"
        info.fps = float(m[4])
    if m := re.search(r"Audio:\s*(\w+)", s):
        info.audio_codec = m[1]
    if m := re.search(r"bitrate:\s*(\d+)\s*kb/s", s):
        info.bitrate_kbps = int(m[1])
    return info
```

---

## Summary Table

| Concept | Key file(s) | Reuse effort |
|---|---|---|
| Typer CLI + subcommands | `cli.py` | Copy `app`, replace commands |
| `make_bar()` factory | `utils.py` | Drop-in, adjust `_BAR_FMT` |
| Tqdm-safe logging | `utils.py` | Drop-in `_TqdmHandler` |
| Stage pipeline + timing | `worker.py` | Adapt stage names |
| SQLite job DB | `db.py` | Copy schema + helpers |
| Subprocess progress | `ffmpeg_utils.py` | Adapt for any CLI tool |
| Lazy generator progress | `transcriber.py` | Pattern applies to any generator |
| Incremental writes | `formats/*.py` | Adapt per format |
| Load-once resources | `cli.py` `_dispatch` | Move init before loop |
| GPU auto-detection | `transcriber.py` | Adapt import for your library |
| Fixed-size chunking | `chunker.py` | ffmpeg-specific; adapt for others |
| Multi-format output | `formats/` | Add new `formats/xxx.py` |
| Media probing | `ffmpeg_utils.py` | Copy `probe_media_info` |
