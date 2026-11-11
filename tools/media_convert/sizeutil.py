"""Parse and format file-size strings such as 5m / 512kb."""

from __future__ import annotations

import re

_UNITS = {
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "m": 1024**2,
    "mb": 1024**2,
    "g": 1024**3,
    "gb": 1024**3,
}


def parse_size(text: str) -> int:
    """Parse a human size string into bytes.

    Parameters:
        text: Size like ``5m``, ``512kb``, or ``1048576``.

    Returns:
        Size in bytes.
    """
    raw = text.strip().lower().replace(" ", "")
    if not raw:
        raise ValueError("empty size string")

    match = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]*)", raw)
    if not match:
        raise ValueError(f"invalid size: {text!r}")

    value = float(match.group(1))
    unit = match.group(2) or "b"
    if unit not in _UNITS:
        raise ValueError(f"unknown size unit: {unit!r}")
    return int(value * _UNITS[unit])


def format_size(num_bytes: int) -> str:
    """Format a byte count into a short human-readable string.

    Parameters:
        num_bytes: File size in bytes.

    Returns:
        Human-readable size string.
    """
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)}{unit}"
            return f"{value:.2f}{unit}"
        value /= 1024
    return f"{num_bytes}B"
