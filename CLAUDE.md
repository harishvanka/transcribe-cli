# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`transcribe-cli` is a Python CLI tool that transcribes audio/video files to text using `faster-whisper` (a CTranslate2-based Whisper implementation). It accepts a single file or a directory of media files and writes `.txt` transcripts to an output directory.

External runtime dependency: **ffmpeg** must be installed and on `PATH`.

## Running the CLI

```bash
# Single file
python -m transcribe_cli <file> [--model small|medium|large] [--output-dir ./outputs] [--language en] [-v]

# Directory of media files
python -m transcribe_cli <directory>
```

Supported input formats: `.mp4`, `.mkv`, `.mp3`, `.wav`.

## Architecture

The pipeline runs sequentially per file:

1. `cli.py` — Typer entrypoint; validates args, iterates files, orchestrates the pipeline.
2. `ffmpeg_utils.extract_audio()` — Shells out to ffmpeg to convert each input file to a 16 kHz mono WAV in a temporary directory.
3. `transcriber.Transcriber.transcribe_file()` — Loads a `WhisperModel` once (reused across files) and transcribes the WAV; segments are joined into a single string.
4. `cli.py` — Writes `<stem>.txt` to `output_dir`, then deletes the temp directory.

`config.py` is the single source of truth for all constants: supported formats, valid model names, ffmpeg parameters, and default paths.

## No build system

There is no `pyproject.toml`, `setup.py`, or `requirements.txt` committed yet. Install dependencies manually:

```bash
pip install typer faster-whisper
```
