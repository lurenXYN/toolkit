"""Inspect WebP / image metadata with Pillow and ffprobe."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageSequence


@dataclass
class MediaInfo:
    """Basic facts about an input media file."""

    path: Path
    width: int
    height: int
    frame_count: int
    is_animated: bool
    duration_sec: float | None = None


def require_ffmpeg() -> str:
    """Locate the ffmpeg executable.

    Returns:
        Absolute path to ffmpeg.

    Raises:
        RuntimeError: When ffmpeg is not installed.
    """
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not found in PATH; install ffmpeg first")
    return path


def require_ffprobe() -> str:
    """Locate the ffprobe executable.

    Returns:
        Absolute path to ffprobe.

    Raises:
        RuntimeError: When ffprobe is not installed.
    """
    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError("ffprobe not found in PATH; install ffmpeg (includes ffprobe)")
    return path


def inspect_media(path: Path) -> MediaInfo:
    """Inspect an image/WebP file for size and animation.

    Parameters:
        path: Local media file.

    Returns:
        MediaInfo describing dimensions and frame count.
    """
    with Image.open(path) as image:
        width, height = image.size
        frames = list(ImageSequence.Iterator(image))
        frame_count = max(1, len(frames))
        is_animated = frame_count > 1 or bool(getattr(image, "is_animated", False))

    duration = _probe_duration(path)
    return MediaInfo(
        path=path,
        width=width,
        height=height,
        frame_count=frame_count,
        is_animated=is_animated,
        duration_sec=duration,
    )


def _probe_duration(path: Path) -> float | None:
    """Read media duration via ffprobe when available.

    Parameters:
        path: Local media file.

    Returns:
        Duration in seconds, or None when unavailable.
    """
    try:
        ffprobe = require_ffprobe()
    except RuntimeError:
        return None

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return None
    if completed.returncode != 0:
        return None

    try:
        payload = json.loads(completed.stdout or "{}")
        duration = payload.get("format", {}).get("duration")
        return float(duration) if duration is not None else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
