"""FFmpeg audio extraction and video/audio muxing."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import check_ffmpeg, check_ffprobe

TIMEOUT = 600  # 10 minutes


def _run(args: list[str], timeout: int = TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with shell=False and capture output."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )


def extract_audio(video_path: Path, output_path: Path) -> Path:
    """Extract audio from video as WAV (16kHz mono PCM).

    Returns the output path.
    """
    ffmpeg = str(check_ffmpeg())
    _run([
        ffmpeg, "-i", str(video_path),
        "-vn",                    # no video
        "-acodec", "pcm_s16le",   # 16-bit PCM
        "-ar", "16000",           # 16kHz
        "-ac", "1",               # mono
        "-y",                     # overwrite
        str(output_path),
    ])
    return output_path


def get_duration(file_path: Path) -> float:
    """Get duration of an audio or video file in seconds via FFprobe."""
    ffprobe = str(check_ffprobe())
    result = _run([
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(file_path),
    ])
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def has_audio_stream(video_path: Path) -> bool:
    """Check if a video file contains an audio stream."""
    ffprobe = str(check_ffprobe())
    result = _run([
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "a",
        str(video_path),
    ])
    data = json.loads(result.stdout)
    return len(data.get("streams", [])) > 0


def mux_audio(video_path: Path, audio_path: Path, output_path: Path) -> Path:
    """Replace the audio track of a video file.

    Takes the video stream from video_path and the audio from audio_path,
    producing a new file at output_path.
    """
    ffmpeg = str(check_ffmpeg())
    _run([
        ffmpeg,
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",           # copy video stream as-is
        "-map", "0:v:0",          # video from first input
        "-map", "1:a:0",          # audio from second input
        "-shortest",
        "-y",
        str(output_path),
    ])
    return output_path
