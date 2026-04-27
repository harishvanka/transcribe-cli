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
python -m transcriber path/to/file.mp4

# Transcribe all media files in a directory
python -m transcriber path/to/directory/
```

Transcripts are saved as `.txt` files in `./outputs/` by default.

## Options

| Option | Default | Description |
|---|---|---|
| `--model` | `small` | Whisper model size: `small`, `medium`, `large` |
| `--output-dir` | `./outputs` | Directory to save transcripts |
| `--language` | auto-detect | Language code (e.g. `en`, `fr`) |
| `-v`, `--verbose` | off | Enable verbose logging |

## Supported Formats

`.mp4`, `.mkv`, `.mp3`, `.wav`
