import subprocess
from pathlib import Path


def split_audio(input_wav: Path, chunk_seconds: int) -> list[Path]:
    out_pattern = input_wav.parent / "part_%03d.wav"
    cmd = [
        "ffmpeg",
        "-i", str(input_wav),
        "-f", "segment",
        "-segment_time", str(chunk_seconds),
        "-c", "copy",
        str(out_pattern),
        "-y",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return sorted(input_wav.parent.glob("part_*.wav"))
