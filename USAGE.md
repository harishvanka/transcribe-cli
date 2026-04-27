# Usage Guide

## 1. Download the Whisper model

`faster-whisper` downloads models from [Hugging Face Hub](https://huggingface.co/Systran) and caches them locally. You can let the first run trigger the download automatically, or pre-download to avoid delays when transcribing.

### Option A — pre-download with the Hugging Face CLI (recommended)

```bash
pip install huggingface-hub
```

Then download whichever model size you plan to use:

```bash
# small  (~460 MB) — fast, good for clear speech
huggingface-cli download Systran/faster-whisper-small

# medium (~1.5 GB) — better accuracy
huggingface-cli download Systran/faster-whisper-medium

# large  (~3 GB)   — best accuracy, slowest
huggingface-cli download Systran/faster-whisper-large-v3
```

Models are cached at:

| OS | Cache location |
|---|---|
| Windows | `C:\Users\<you>\.cache\huggingface\hub\` |
| macOS / Linux | `~/.cache/huggingface/hub/` |

### Option B — let the tool download on first use

Just run a transcription command (see below). The model will be downloaded automatically before transcription starts. Subsequent runs reuse the cached model.

### Option C — use a local model directory

If you have a model saved to a local folder (e.g. from a private mirror), pass its path as `--model`:

```bash
python -m transcriber transcribe video.mp4 --model /path/to/faster-whisper-small
```

---

## 2. Transcribe files

### Single file

```bash
python -m transcriber transcribe path/to/video.mp4
```

### All media files in a directory

```bash
python -m transcriber transcribe path/to/folder/
```

Transcripts are written to `./outputs/` by default. Supported input formats: `.mp4`, `.mkv`, `.mp3`, `.wav`.

---

## 3. Common examples

**Use a larger model for better accuracy:**

```bash
python -m transcriber transcribe lecture.mp4 --model medium
```

**Transcribe in parallel with 4 workers:**

```bash
python -m transcriber transcribe recordings/ --workers 4
```

**Export to SRT and JSON in addition to plain text:**

```bash
python -m transcriber transcribe meeting.mp4 --output txt,srt,json
```

**Force the language (skips auto-detection, slightly faster):**

```bash
python -m transcriber transcribe interview.mp3 --language en
```

**Smaller chunks for very long files (reduces peak memory):**

```bash
python -m transcriber transcribe documentary.mp4 --chunk 300
```

**Save transcripts to a custom directory:**

```bash
python -m transcriber transcribe video.mp4 --output-dir ./transcripts
```

**Combine options:**

```bash
python -m transcriber transcribe recordings/ \
  --model medium \
  --workers 4 \
  --chunk 300 \
  --output txt,srt \
  --language en \
  --output-dir ./transcripts \
  --verbose
```

---

## 4. Resume interrupted or failed jobs

If a run is interrupted or some files fail, resume without re-processing completed files:

```bash
python -m transcriber resume
```

To resume with different settings (e.g. more workers):

```bash
python -m transcriber resume --workers 4 --output txt,srt
```

The job database lives at `~/.transcriber/jobs.db`. Each run of `transcribe` adds new entries; already-completed files are skipped automatically.

---

## 5. Choosing a model

| Model | Size | Speed | Best for |
|---|---|---|---|
| `small` | ~460 MB | Fast | Quick drafts, clear recordings |
| `medium` | ~1.5 GB | Moderate | Good balance of speed and accuracy |
| `large` | ~3 GB | Slow | Noisy audio, accented speech, high accuracy |

On a CPU-only machine, `small` is the practical default. Use `medium` or `large` if you have a GPU or can wait longer.
