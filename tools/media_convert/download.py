"""Resolve local paths or HTTP(S) URLs into a temporary WebP file."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests

_URL_SCHEMES = {"http", "https"}


def is_url(source: str) -> bool:
    """Return whether *source* looks like an HTTP(S) URL.

    Parameters:
        source: Local path or remote URL.

    Returns:
        True when the source uses http/https.
    """
    parsed = urlparse(source)
    return parsed.scheme.lower() in _URL_SCHEMES and bool(parsed.netloc)


def resolve_input(source: str, work_dir: Path) -> Path:
    """Resolve a local path or URL into a local file under *work_dir*.

    Parameters:
        source: Local WebP path or remote URL.
        work_dir: Directory used for downloaded files.

    Returns:
        Path to a local input file.
    """
    if is_url(source):
        return download_url(source, work_dir)

    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"input file not found: {path}")
    return path


def download_url(url: str, work_dir: Path, timeout: int = 60) -> Path:
    """Download a remote resource into *work_dir*.

    Parameters:
        url: Remote media URL.
        work_dir: Destination directory.
        timeout: Request timeout in seconds.

    Returns:
        Path to the downloaded file.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(urlparse(url).path).suffix.lower() or ".webp"
    if suffix not in {".webp", ".gif", ".png", ".jpg", ".jpeg"}:
        suffix = ".webp"

    # mkstemp leaves an open FD; close it immediately or Windows cannot delete the temp file.
    fd, raw_path = tempfile.mkstemp(prefix="media-convert-", suffix=suffix, dir=work_dir)
    os.close(fd)
    dest = Path(raw_path)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/webp,image/*,*/*;q=0.8",
    }
    response = requests.get(url, stream=True, timeout=timeout, headers=headers)
    response.raise_for_status()

    content_type = (response.headers.get("Content-Type") or "").lower()
    if "text/html" in content_type:
        dest.unlink(missing_ok=True)
        raise RuntimeError("URL returned HTML instead of an image (link may have expired)")

    written = 0
    with dest.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if chunk:
                handle.write(chunk)
                written += len(chunk)

    if written < 32:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"downloaded file too small ({written} bytes)")
    return dest
