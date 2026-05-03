import logging
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from transcriber.config import FFMPEG_CHANNELS, FFMPEG_SAMPLE_RATE

logger = logging.getLogger("transcriber")


@dataclass
class MediaInfo:
    duration_sec: float | None = None
    resolution: str | None = None        # "1920x1080"
    fps: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    bitrate_kbps: int | None = None
    file_size_bytes: int = 0

    @property
    def duration_str(self) -> str:
        if self.duration_sec is None:
            return "unknown"
        total = int(self.duration_sec)
        h, remainder = divmod(total, 3600)
        m, s = divmod(remainder, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    @property
    def file_size_str(self) -> str:
        b = self.file_size_bytes
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"


def probe_media_info(file_path: Path) -> MediaInfo:
    """Run ffmpeg -i and parse metadata. ffmpeg always exits 1 here; that is expected."""
    info = MediaInfo(file_size_bytes=file_path.stat().st_size if file_path.exists() else 0)
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", str(file_path)],
            capture_output=True, text=True, timeout=30,
        )
        stderr = result.stderr

        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", stderr)
        if m:
            h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            info.duration_sec = h * 3600 + mn * 60 + s

        m = re.search(r"bitrate:\s*(\d+)\s*kb/s", stderr)
        if m:
            info.bitrate_kbps = int(m.group(1))

        # Video stream — codec, resolution, fps (order matters: codec before dimensions)
        m = re.search(
            r"Stream\s+#\S+:\s+Video:\s+(\w+).*?(\d{2,4})x(\d{2,4}).*?([\d.]+)\s+fps",
            stderr,
        )
        if m:
            info.video_codec = m.group(1)
            info.resolution = f"{m.group(2)}x{m.group(3)}"
            info.fps = float(m.group(4))

        m = re.search(r"Stream\s+#\S+:\s+Audio:\s+(\w+)", stderr)
        if m:
            info.audio_codec = m.group(1)

    except Exception:
        pass
    return info


def _probe_duration(file_path: Path) -> float | None:
    return probe_media_info(file_path).duration_sec


def extract_audio(
    input_path: Path,
    output_dir: Path | None = None,
    progress_cb: Callable[[float], None] | None = None,
) -> Path | None:
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp())
    output_path = output_dir / f"{input_path.stem}.wav"

    duration = _probe_duration(input_path) if progress_cb else None

    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-ar", str(FFMPEG_SAMPLE_RATE),
        "-ac", str(FFMPEG_CHANNELS),
    ]
    if progress_cb and duration:
        cmd += ["-progress", "pipe:1"]
    cmd += [str(output_path), "-y"]

    try:
        if progress_cb and duration:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            stderr_lines: list[str] = []
            def _drain() -> None:
                for line in proc.stderr:
                    stderr_lines.append(line)
            threading.Thread(target=_drain, daemon=True).start()

            for line in proc.stdout:
                m = re.match(r"out_time_ms=(\d+)", line.strip())
                if m:
                    pct = min(int(m.group(1)) / (duration * 1_000_000) * 100, 99.0)
                    progress_cb(pct)

            proc.wait()
            if proc.returncode != 0:
                logger.error(f"FFmpeg failed for {input_path.name}: {''.join(stderr_lines).strip()}")
                return None
        else:
            subprocess.run(cmd, check=True, capture_output=True, text=True)

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed for {input_path.name}: {e.stderr.strip()}")
        return None
    except FileNotFoundError:
        logger.error("FFmpeg not found. Please install FFmpeg and ensure it's on PATH.")
        return None

    return output_path if output_path.exists() else None
