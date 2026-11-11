"""Automatic cleanup for converted output files."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

# Dual retention policy for data/outputs.
MAX_AGE_SECONDS = 24 * 60 * 60
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_FILE_COUNT = 50


@dataclass
class CleanupReport:
    """Summary of a cleanup pass."""

    deleted: int = 0
    freed_bytes: int = 0
    remaining: int = 0
    remaining_bytes: int = 0


def cleanup_outputs(
    output_dir: Path,
    *,
    max_age_seconds: int = MAX_AGE_SECONDS,
    max_total_bytes: int = MAX_TOTAL_BYTES,
    max_file_count: int = MAX_FILE_COUNT,
    now: float | None = None,
) -> CleanupReport:
    """Delete stale or excess converted files under *output_dir*.

    Policy (both enforced):
      1. Remove files older than *max_age_seconds* (default 24h).
      2. If total size > *max_total_bytes* or file count > *max_file_count*,
         delete oldest files until both limits are satisfied.

    Parameters:
        output_dir: Directory that stores converted outputs.
        max_age_seconds: Age threshold in seconds.
        max_total_bytes: Maximum total bytes to keep.
        max_file_count: Maximum number of files to keep.
        now: Optional unix timestamp override for tests.

    Returns:
        CleanupReport describing deleted and remaining files.
    """
    report = CleanupReport()
    if not output_dir.is_dir():
        return report

    current = time.time() if now is None else now
    files = [path for path in output_dir.iterdir() if path.is_file()]

    survivors: list[tuple[Path, float, int]] = []
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue

        age = current - stat.st_mtime
        if age > max_age_seconds:
            freed = _safe_unlink(path)
            if freed is not None:
                report.deleted += 1
                report.freed_bytes += freed
            continue

        survivors.append((path, stat.st_mtime, stat.st_size))

    # Oldest first so quota trimming removes the oldest survivors.
    survivors.sort(key=lambda item: item[1])
    total_bytes = sum(size for _, _, size in survivors)

    while len(survivors) > 1 and (
        len(survivors) > max_file_count or total_bytes > max_total_bytes
    ):
        # Keep at least the newest file so the just-converted result remains downloadable.
        path, _, size = survivors.pop(0)
        freed = _safe_unlink(path)
        if freed is None:
            continue
        report.deleted += 1
        report.freed_bytes += freed
        total_bytes = max(0, total_bytes - size)

    report.remaining = len(survivors)
    report.remaining_bytes = total_bytes
    return report


def _safe_unlink(path: Path) -> int | None:
    """Delete a file and return its size, ignoring lock/race errors.

    Parameters:
        path: File to delete.

    Returns:
        Freed byte count, or None when deletion failed.
    """
    try:
        size = path.stat().st_size
        path.unlink()
        return size
    except OSError:
        return None
