"""Configuration: API clients, FFmpeg checks, path validation."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from openai import OpenAI

# Load .env from project root
load_dotenv()

# --- Constants ---

DEFAULT_VOICE_ID = "sDh3eviBhiuHKi0MjTNq"
SCRIBE_MODEL = "scribe_v1"
TTS_MODEL = "eleven_multilingual_v2"
TRANSLATION_MODEL = "o3"
SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}

PLACEHOLDER_VALUES = {
    "your-elevenlabs-api-key-here",
    "your-openai-api-key-here",
    "sk-...",
    "",
}


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def get_api_keys() -> tuple[str, str]:
    """Load and validate API keys from environment variables.

    Returns (elevenlabs_key, openai_key).
    """
    el_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    oa_key = os.environ.get("OPENAI_API_KEY", "").strip()

    errors = []
    if not el_key or el_key in PLACEHOLDER_VALUES:
        errors.append("ELEVENLABS_API_KEY is missing or still a placeholder")
    if not oa_key or oa_key in PLACEHOLDER_VALUES:
        errors.append("OPENAI_API_KEY is missing or still a placeholder")

    if errors:
        raise ConfigError(
            "API key errors:\n  - " + "\n  - ".join(errors)
            + "\n\nSet them in a .env file or as environment variables."
        )

    return el_key, oa_key


def create_clients() -> tuple[ElevenLabs, OpenAI]:
    """Create and return ElevenLabs and OpenAI clients."""
    el_key, oa_key = get_api_keys()
    return ElevenLabs(api_key=el_key), OpenAI(api_key=oa_key)


def check_ffmpeg() -> Path:
    """Verify FFmpeg is installed and return its path.

    Raises ConfigError with install instructions if not found.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ConfigError(
            "FFmpeg not found on PATH.\n"
            "Install it with: winget install Gyan.FFmpeg\n"
            "Then restart your terminal."
        )
    # Quick sanity check
    try:
        subprocess.run(
            [ffmpeg, "-version"],
            capture_output=True,
            timeout=10,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise ConfigError(f"FFmpeg found but not working: {exc}") from exc

    return Path(ffmpeg)


def check_ffprobe() -> Path:
    """Verify FFprobe is installed and return its path."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise ConfigError(
            "FFprobe not found on PATH (usually installed with FFmpeg).\n"
            "Install FFmpeg with: winget install Gyan.FFmpeg"
        )
    return Path(ffprobe)


def validate_path(path: Path, must_exist: bool = True) -> Path:
    """Validate a path is safe (no traversal) and optionally exists.

    Returns the resolved path.
    """
    resolved = path.resolve()

    # Basic traversal check: the resolved path should not escape expected areas
    # by containing .. components in the original
    if ".." in path.parts:
        raise ConfigError(f"Path traversal not allowed: {path}")

    if must_exist and not resolved.exists():
        raise ConfigError(f"Path does not exist: {resolved}")

    return resolved
