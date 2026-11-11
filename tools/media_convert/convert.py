"""Convert WebP media into GIF / PNG / JPEG with optional size caps."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from tools.media_convert.inspect import MediaInfo, inspect_media, require_ffmpeg
from tools.media_convert.sizeutil import format_size


SUPPORTED_OUTPUTS = {"gif", "png", "jpg", "jpeg"}


@dataclass
class ConvertResult:
    """Result of a conversion attempt."""

    output: Path
    bytes: int
    attempts: int
    scale: float
    fps: float | None
    info: MediaInfo


def convert(
    input_path: Path,
    output_path: Path,
    fmt: str | None = None,
    max_bytes: int | None = None,
) -> ConvertResult:
    """Convert a WebP (or image) file into the requested output format.

    Parameters:
        input_path: Local source file.
        output_path: Destination path.
        fmt: Target format (gif/png/jpg). Defaults from output suffix.
        max_bytes: Optional maximum output size in bytes.

    Returns:
        ConvertResult with output path and compression stats.
    """
    info = inspect_media(input_path)
    target = (fmt or output_path.suffix.lstrip(".")).lower()
    if target == "jpeg":
        target = "jpg"
    if target not in SUPPORTED_OUTPUTS:
        raise ValueError(f"unsupported output format: {target}")

    output_path = output_path.with_suffix(f".{target}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if target == "gif":
        return _convert_to_gif(input_path, output_path, info, max_bytes)

    if info.is_animated and target in {"png", "jpg"}:
        # Keep first frame for static exports of animated sources.
        return _convert_static_frame(input_path, output_path, target, max_bytes, info)

    return _convert_static(input_path, output_path, target, max_bytes, info)


def _convert_to_gif(
    input_path: Path,
    output_path: Path,
    info: MediaInfo,
    max_bytes: int | None,
) -> ConvertResult:
    """Convert (animated) WebP to GIF, optionally iterating down to max_bytes.

    Parameters:
        input_path: Source WebP path.
        output_path: Destination GIF path.
        info: Inspected media info.
        max_bytes: Optional size budget.

    Returns:
        ConvertResult for the final GIF.
    """
    ffmpeg = require_ffmpeg()
    scales = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]
    fps_options = _fps_ladder(info)

    attempt = 0
    last_error = ""
    with tempfile.TemporaryDirectory(prefix="media-convert-gif-", ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        for scale in scales:
            for fps in fps_options:
                attempt += 1
                candidate = tmp_dir / f"try_{attempt}.gif"
                ok, err = _ffmpeg_webp_to_gif(ffmpeg, input_path, candidate, scale, fps)
                if not ok:
                    last_error = err
                    continue

                size = candidate.stat().st_size
                if max_bytes is None or size <= max_bytes:
                    shutil.copyfile(candidate, output_path)
                    return ConvertResult(
                        output=output_path,
                        bytes=size,
                        attempts=attempt,
                        scale=scale,
                        fps=fps,
                        info=info,
                    )

        # Last resort: keep the smallest candidate produced.
        candidates = sorted(tmp_dir.glob("try_*.gif"), key=lambda p: p.stat().st_size)
        if not candidates:
            raise RuntimeError(f"ffmpeg failed to produce GIF: {last_error or 'unknown error'}")

        best = candidates[0]
        shutil.copyfile(best, output_path)
        size = best.stat().st_size
        if max_bytes is not None and size > max_bytes:
            raise RuntimeError(
                f"unable to fit GIF under {format_size(max_bytes)}; "
                f"smallest result is {format_size(size)} after {attempt} attempts"
            )
        return ConvertResult(
            output=output_path,
            bytes=size,
            attempts=attempt,
            scale=scales[-1],
            fps=fps_options[-1],
            info=info,
        )


def _fps_ladder(info: MediaInfo) -> list[float | None]:
    """Build FPS attempts from source duration / frame count.

    Parameters:
        info: Inspected media info.

    Returns:
        Ordered FPS values; ``None`` means keep source timing.
    """
    if not info.is_animated:
        return [None]

    native: float | None = None
    if info.duration_sec and info.duration_sec > 0 and info.frame_count > 1:
        native = info.frame_count / info.duration_sec

    values: list[float | None] = [None]
    for fps in (native, 15.0, 12.0, 10.0, 8.0, 6.0):
        if fps is None:
            continue
        rounded = round(float(fps), 2)
        if rounded not in values and rounded > 0:
            values.append(rounded)
    return values


def _ffmpeg_webp_to_gif(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    scale: float,
    fps: float | None,
) -> tuple[bool, str]:
    """Run ffmpeg palette-based WebP 鈫?GIF conversion.

    Parameters:
        ffmpeg: Path to ffmpeg.
        input_path: Source file.
        output_path: Destination GIF.
        scale: Relative scale factor (1.0 = original).
        fps: Optional FPS override.

    Returns:
        (ok, stderr) pair.
    """
    # Even width/height keep palette filters happy on odd dimensions.
    scale_expr = f"scale=trunc(iw*{scale}/2)*2:trunc(ih*{scale}/2)*2:flags=lanczos"
    filters = [scale_expr]
    if fps is not None:
        filters.append(f"fps={fps}")

    # Two-pass palette pipeline yields smaller / cleaner GIFs than raw encode.
    vf = ",".join(filters)
    filter_complex = (
        f"[0:v]{vf},split[s0][s1];"
        f"[s0]palettegen=max_colors=256:stats_mode=diff[p];"
        f"[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        filter_complex,
        "-loop",
        "0",
        "-an",
        str(output_path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not output_path.is_file():
        return False, (completed.stderr or completed.stdout or "").strip()
    return True, ""


def _convert_static(
    input_path: Path,
    output_path: Path,
    target: str,
    max_bytes: int | None,
    info: MediaInfo,
) -> ConvertResult:
    """Convert a static image with optional size budget.

    Parameters:
        input_path: Source image.
        output_path: Destination path.
        target: png or jpg.
        max_bytes: Optional size budget.
        info: Inspected media info.

    Returns:
        ConvertResult for the static export.
    """
    with Image.open(input_path) as image:
        frame = image.convert("RGBA" if target == "png" else "RGB")

    return _save_static_with_budget(frame, output_path, target, max_bytes, info)


def _convert_static_frame(
    input_path: Path,
    output_path: Path,
    target: str,
    max_bytes: int | None,
    info: MediaInfo,
) -> ConvertResult:
    """Export the first frame of an animated source as PNG/JPEG.

    Parameters:
        input_path: Animated source.
        output_path: Destination path.
        target: png or jpg.
        max_bytes: Optional size budget.
        info: Inspected media info.

    Returns:
        ConvertResult for the static export.
    """
    with Image.open(input_path) as image:
        image.seek(0)
        frame = image.convert("RGBA" if target == "png" else "RGB")

    return _save_static_with_budget(frame, output_path, target, max_bytes, info)


def _save_static_with_budget(
    image: Image.Image,
    output_path: Path,
    target: str,
    max_bytes: int | None,
    info: MediaInfo,
) -> ConvertResult:
    """Save a static image, shrinking quality/scale until under max_bytes.

    Parameters:
        image: Pillow image to save.
        output_path: Destination path.
        target: png or jpg.
        max_bytes: Optional size budget.
        info: Inspected media info.

    Returns:
        ConvertResult for the saved file.
    """
    qualities = [95, 85, 75, 65, 55, 45]
    scales = [1.0, 0.85, 0.7, 0.55, 0.4]
    attempt = 0

    with tempfile.TemporaryDirectory(prefix="media-convert-static-", ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        for scale in scales:
            if scale != 1.0:
                w = max(1, int(image.width * scale))
                h = max(1, int(image.height * scale))
                frame = image.resize((w, h), Image.Resampling.LANCZOS)
            else:
                frame = image

            for quality in qualities if target == "jpg" else [None]:
                attempt += 1
                candidate = tmp_dir / f"try_{attempt}.{target}"
                _save_image(frame, candidate, target, quality)
                size = candidate.stat().st_size
                if max_bytes is None or size <= max_bytes:
                    shutil.copyfile(candidate, output_path)
                    return ConvertResult(
                        output=output_path,
                        bytes=size,
                        attempts=attempt,
                        scale=scale,
                        fps=None,
                        info=info,
                    )

        candidates = sorted(tmp_dir.glob(f"try_*.{target}"), key=lambda p: p.stat().st_size)
        best = candidates[0]
        shutil.copyfile(best, output_path)
        size = best.stat().st_size
        if max_bytes is not None and size > max_bytes:
            raise RuntimeError(
                f"unable to fit {target.upper()} under {format_size(max_bytes)}; "
                f"smallest result is {format_size(size)}"
            )
        return ConvertResult(
            output=output_path,
            bytes=size,
            attempts=attempt,
            scale=scales[-1],
            fps=None,
            info=info,
        )


def _save_image(image: Image.Image, path: Path, target: str, quality: int | None) -> None:
    """Save a Pillow image to disk.

    Parameters:
        image: Image to write.
        path: Destination path.
        target: png or jpg.
        quality: JPEG quality when applicable.
    """
    if target == "png":
        image.save(path, format="PNG", optimize=True)
        return

    rgb = image.convert("RGB")
    rgb.save(path, format="JPEG", quality=quality or 85, optimize=True)
