# transcribe-cli

A command-line tool for transcribing audio and video files to text using [faster-whisper](https://github.com/SYSTRAN/faster-whisper).

## Requirements

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) installed and on `PATH`

## Installation

**1. Create a virtual environment**

<details>
<summary>Windows</summary>

```bat
python -m venv .venv
.venv\Scripts\Activate.ps1
```
</details>

<details>
<summary>macOS</summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
```
</details>

<details>
<summary>Linux</summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
```
</details>

**2. Install dependencies**

```bash
pip install typer faster-whisper
```

## Usage

```bash
# Transcribe a single file
python -m transcriber transcribe path/to/file.mp4

# Transcribe all media files in a directory
python -m transcriber transcribe path/to/directory/

# Resume any pending or failed jobs from a previous run
python -m transcriber resume
```

Transcripts are saved in `./outputs/` by default.

## Commands

### `transcribe`

Queues and processes media files. Skips files that were already completed in a previous run; pass `--resume` to also retry failed ones.

```bash
python -m transcriber transcribe path/to/directory/ \
  --model medium \
  --workers 4 \
  --chunk 300 \
  --output txt,srt,json \
  --language en \
  --verbose
```

| Option | Default | Description |
|---|---|---|
| `--model` | `small` | Whisper model size: `small`, `medium`, `large` |
| `--output-dir` | `./outputs` | Directory to save transcripts |
| `--language` | auto-detect | Language code (e.g. `en`, `fr`) |
| `--workers` | `2` | Number of parallel worker processes |
| `--chunk` | `600` | Audio chunk size in seconds |
| `--output` | `txt` | Comma-separated output formats: `txt`, `srt`, `json` |
| `--resume` | off | Also retry previously failed jobs |
| `-v`, `--verbose` | off | Enable verbose logging |

### `resume`

Re-runs all pending and failed jobs from the job database without re-scanning the filesystem.

```bash
python -m transcriber resume --workers 4 --output txt,srt
```

Accepts the same options as `transcribe` except `input_path` and `--resume`.

## Output Formats

| Format | Extension | Description |
|---|---|---|
| `txt` | `.txt` | Plain text transcript |
| `srt` | `.srt` | SubRip subtitle file with timestamps |
| `json` | `.json` | Structured JSON with per-segment start/end times and text |

## Job Persistence

Each run records jobs in a SQLite database at `~/.transcriber/jobs.db`. This lets you:

- Skip already-completed files when re-running over the same directory
- Resume interrupted or failed jobs with the `resume` command
- Track per-file progress (0–100 %) and error messages

## Supported Input Formats

`.mp4`, `.mkv`, `.mp3`, `.wav`
