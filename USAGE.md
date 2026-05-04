# Usage Guide

## 1. Choose a backend

The tool supports two inference backends, selected with `--backend`:

| Backend | Flag | Hardware used | Requires |
|---|---|---|---|
| **DirectML** (default) | `--backend directml` | GPU on Windows (Qualcomm Adreno, AMD, Intel) via DirectML | `onnxruntime-directml`, `optimum`, `transformers` |
| **CPU** | `--backend cpu` | All CPU cores via CTranslate2 | `faster-whisper` |

---

## 2. Install packages

### DirectML backend (GPU on Windows)

```bash
# Remove onnxruntime if already installed — it conflicts with the DirectML build
pip uninstall onnxruntime -y

pip install onnxruntime-directml
pip install "optimum[exporters]" transformers soundfile

# torch is only needed on the first run to export the model to ONNX;
# after that the cached ONNX files are reused without torch.
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### CPU backend (faster-whisper)

```bash
pip install faster-whisper
```

---

## 3. Download / cache models

### DirectML backend

Models are downloaded from [Hugging Face](https://huggingface.co/openai) and automatically exported to ONNX on first use. The ONNX files are cached at:

| OS | Cache location |
|---|---|
| Windows | `C:\Users\<you>\.cache\huggingface\hub\` |
| macOS / Linux | `~/.cache/huggingface/hub/` |

The first run for a given model size will take a few extra minutes for the export step. Subsequent runs reuse the cached ONNX files instantly.

### CPU backend

`faster-whisper` downloads CTranslate2 models from [Hugging Face (Systran)](https://huggingface.co/Systran) and caches them in the same location. Pre-download to avoid delays:

```bash
pip install huggingface-hub

huggingface-cli download Systran/faster-whisper-small   # ~460 MB
huggingface-cli download Systran/faster-whisper-medium  # ~1.5 GB
huggingface-cli download Systran/faster-whisper-large-v3  # ~3 GB
```

---

## 4. Transcribe files

### Single file (DirectML backend, default)

```bash
python -m transcriber transcribe path/to/video.mp4
```

### Single file — CPU backend

```bash
python -m transcriber transcribe path/to/video.mp4 --backend cpu
```

### All media files in a directory

```bash
python -m transcriber transcribe path/to/folder/
```

Transcripts are written to `./outputs/<filename>/` by default.  
Supported input formats: `.mp4`, `.mkv`, `.mp3`, `.wav`.

---

## 5. Common examples

**Use a larger model for better accuracy:**

```bash
python -m transcriber transcribe lecture.mp4 --model medium
```

**Export SRT and JSON only (no plain text):**

```bash
python -m transcriber transcribe meeting.mp4 --output srt,json
```

**Force the language (skips auto-detection, slightly faster):**

```bash
python -m transcriber transcribe interview.mp3 --language en
```

**Speed up CPU transcription with greedy decoding (beam-size 1):**

```bash
python -m transcriber transcribe video.mp4 --backend cpu --beam-size 1
```

**Skip silent regions (useful for recordings with long pauses):**

```bash
python -m transcriber transcribe podcast.mp3 --backend cpu --vad
```

> `--vad` is only supported by the `cpu` backend; it is silently ignored with `--backend directml`.

**Smaller chunks for very long files (reduces peak memory):**

```bash
python -m transcriber transcribe documentary.mp4 --chunk 300
```

**Save transcripts to a custom directory:**

```bash
python -m transcriber transcribe video.mp4 --output-dir ./transcripts
```

**Re-transcribe a file that already completed:**

```bash
python -m transcriber transcribe video.mp4 --force
```

**Also retry previously failed jobs in the same directory:**

```bash
python -m transcriber transcribe recordings/ --resume
```

**Full example — DirectML, medium model, English, SRT + JSON:**

```bash
python -m transcriber transcribe recordings/ \
  --backend directml \
  --model medium \
  --language en \
  --output srt,json \
  --output-dir ./transcripts \
  --verbose
```

**Full example — CPU, fastest settings:**

```bash
python -m transcriber transcribe recordings/ \
  --backend cpu \
  --model small \
  --beam-size 1 \
  --vad \
  --language en \
  --output txt,srt \
  --output-dir ./transcripts
```

---

## 6. Resume interrupted or failed jobs

If a run is interrupted or some files fail, resume without re-processing completed files:

```bash
python -m transcriber resume
```

Specify the backend to use for resuming:

```bash
python -m transcriber resume --backend directml
python -m transcriber resume --backend cpu --model medium
```

The job database lives at `~/.transcriber/jobs.db`. Each run of `transcribe` registers new entries; already-completed files are skipped automatically.

---

## 7. All options

### `transcribe` command

| Option | Default | Description |
|---|---|---|
| `--backend` | `directml` | Inference backend: `directml` or `cpu` |
| `--model` | `small` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large` |
| `--output` | `txt,srt,json` | Comma-separated output formats |
| `--output-dir` | `./outputs` | Directory to write transcripts |
| `--language` | auto-detect | Language code, e.g. `en`, `fr`, `de` |
| `--chunk` | `600` | Chunk size in seconds |
| `--beam-size` | `5` | Beam size (`1` = greedy/fastest, `5` = default). CPU backend only. |
| `--vad` / `--no-vad` | off | Skip silent regions. CPU backend only. |
| `--force` | off | Re-transcribe already completed files |
| `--resume` | off | Also retry previously failed jobs |
| `-v` / `--verbose` | off | Enable debug logging |

### `resume` command

| Option | Default | Description |
|---|---|---|
| `--backend` | `directml` | Inference backend: `directml` or `cpu` |
| `--model` | `small` | Whisper model size |
| `--output` | `txt,srt,json` | Output formats |
| `--output-dir` | `./outputs` | Output directory |
| `--language` | auto-detect | Language code |
| `--chunk` | `600` | Chunk size in seconds |
| `-v` / `--verbose` | off | Enable debug logging |

---

## 8. Choosing a model

| Model | Size | Speed | Best for |
|---|---|---|---|
| `tiny` | ~75 MB | Fastest | Quick drafts, very clear speech |
| `base` | ~145 MB | Very fast | Clear recordings, low-resource environments |
| `small` | ~460 MB | Fast | Good default for most use cases |
| `medium` | ~1.5 GB | Moderate | Better accuracy for accented or noisy audio |
| `large` | ~3 GB | Slowest | Best accuracy, challenging audio |
