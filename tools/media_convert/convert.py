"""Convert WebP media into GIF / PNG / JPEG with optional size caps."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageSequence

from tools.media_convert.inspect import MediaInfo, inspect_media, require_ffmpeg
from tools.media_convert.sizeutil import format_size


SUPPORTED_OUTPUTS = {"gif", "png", "jpg", "jpeg"}
# Reject empty / truncated ffmpeg leftovers that can appear after failed encodes.
MIN_GIF_BYTES = 32


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
    # Ubuntu 22.04 ffmpeg 4.4 cannot decode animated WebP; use Pillow then.
    use_pillow = info.is_animated and _looks_like_webp(input_path) and not _ffmpeg_supports_animated_webp(
        ffmpeg, input_path
    )

    attempt = 0
    last_error = ""
    valid: list[tuple[Path, int, float, float | None]] = []
    with tempfile.TemporaryDirectory(prefix="media-convert-gif-", ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        for scale in scales:
            for fps in fps_options:
                attempt += 1
                candidate = tmp_dir / f"try_{attempt}.gif"
                if use_pillow:
                    ok, err = _pillow_webp_to_gif(input_path, candidate, scale, fps)
                else:
                    ok, err = _encode_gif(ffmpeg, input_path, candidate, scale, fps)
                if not ok:
                    last_error = _short_error(err)
                    _safe_unlink(candidate)
                    continue

                size = candidate.stat().st_size
                if size < MIN_GIF_BYTES:
                    last_error = f"ffmpeg produced empty/invalid GIF ({size} bytes)"
                    _safe_unlink(candidate)
                    continue

                valid.append((candidate, size, scale, fps))
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

        if not valid:
            raise RuntimeError(f"ffmpeg failed to produce GIF: {last_error or 'unknown error'}")

        # Prefer the smallest *valid* oversized candidate when nothing fit the budget.
        best_path, size, scale, fps = min(valid, key=lambda item: item[1])
        if max_bytes is not None and size > max_bytes:
            raise RuntimeError(
                f"unable to fit GIF under {format_size(max_bytes)}; "
                f"smallest result is {format_size(size)} after {attempt} attempts"
            )

        shutil.copyfile(best_path, output_path)
        return ConvertResult(
            output=output_path,
            bytes=size,
            attempts=attempt,
            scale=scale,
            fps=fps,
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


def _encode_gif(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    scale: float,
    fps: float | None,
) -> tuple[bool, str]:
    """Encode a GIF via ffmpeg, falling back to Pillow when needed.

    Parameters:
        ffmpeg: Path to ffmpeg.
        input_path: Source file.
        output_path: Destination GIF.
        scale: Relative scale factor (1.0 = original).
        fps: Optional FPS override.

    Returns:
        (ok, error_message) pair.
    """
    ok, err = _ffmpeg_webp_to_gif(ffmpeg, input_path, output_path, scale, fps)
    if ok:
        return True, ""

    pillow_ok, pillow_err = _pillow_webp_to_gif(input_path, output_path, scale, fps)
    if pillow_ok:
        return True, ""
    return False, _short_error(pillow_err or err)


def _ffmpeg_supports_animated_webp(ffmpeg: str, sample_path: Path) -> bool:
    """Probe whether ffmpeg can decode this animated WebP.

    Parameters:
        ffmpeg: Path to ffmpeg.
        sample_path: Local WebP file.

    Returns:
        True when ffmpeg can decode at least one frame.
    """
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-f",
        "webp",
        "-i",
        str(sample_path),
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    err = ((completed.stderr or "") + (completed.stdout or "")).lower()
    if "unsupported chunk: anim" in err or "unsupported chunk: anmf" in err:
        return False
    return completed.returncode == 0


def _ffmpeg_webp_to_gif(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    scale: float,
    fps: float | None,
) -> tuple[bool, str]:
    """Run ffmpeg WebP/image → GIF conversion.

    Parameters:
        ffmpeg: Path to ffmpeg.
        input_path: Source file.
        output_path: Destination GIF.
        scale: Relative scale factor (1.0 = original).
        fps: Optional FPS override.

    Returns:
        (ok, stderr) pair.
    """
    # Even width/height keep palette filters happy on odd dimensions; never go below 2px.
    scale_expr = (
        f"scale=max(2\\,trunc(iw*{scale}/2)*2):max(2\\,trunc(ih*{scale}/2)*2):flags=lanczos"
    )
    filters = [scale_expr]
    if fps is not None:
        filters.append(f"fps={fps}")

    vf = ",".join(filters)
    filter_complex = (
        f"[0:v]{vf},split[s0][s1];"
        f"[s0]palettegen=max_colors=256:stats_mode=diff[p];"
        f"[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
    )

    # Force webp demuxer when content is webp but the temp suffix is wrong.
    input_args = ["-i", str(input_path)]
    if _looks_like_webp(input_path):
        input_args = ["-f", "webp", "-i", str(input_path)]

    cmd = [
        ffmpeg,
        "-y",
        *input_args,
        "-filter_complex",
        filter_complex,
        "-loop",
        "0",
        "-an",
        str(output_path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    err = (completed.stderr or completed.stdout or "").strip()
    if completed.returncode == 0 and output_path.is_file() and output_path.stat().st_size >= MIN_GIF_BYTES:
        return True, ""

    _safe_unlink(output_path)
    fallback_cmd = [
        ffmpeg,
        "-y",
        *input_args,
        "-vf",
        vf,
        "-loop",
        "0",
        "-an",
        str(output_path),
    ]
    fallback = subprocess.run(fallback_cmd, capture_output=True, text=True, check=False)
    fallback_err = (fallback.stderr or fallback.stdout or "").strip()
    if fallback.returncode != 0 or not output_path.is_file():
        _safe_unlink(output_path)
        return False, fallback_err or err
    if output_path.stat().st_size < MIN_GIF_BYTES:
        _safe_unlink(output_path)
        return False, fallback_err or err or "ffmpeg produced empty GIF"
    return True, ""


def _pillow_webp_to_gif(
    input_path: Path,
    output_path: Path,
    scale: float,
    fps: float | None,
) -> tuple[bool, str]:
    """Convert animated/static WebP to GIF with Pillow (libwebp).

    Parameters:
        input_path: Source image.
        output_path: Destination GIF.
        scale: Relative scale factor.
        fps: Optional FPS override.

    Returns:
        (ok, error_message) pair.
    """
    try:
        with Image.open(input_path) as image:
            frames: list[Image.Image] = []
            durations: list[int] = []
            for frame in ImageSequence.Iterator(image):
                rgba = frame.convert("RGBA")
                if scale != 1.0:
                    width = max(1, int(rgba.width * scale))
                    height = max(1, int(rgba.height * scale))
                    rgba = rgba.resize((width, height), Image.Resampling.LANCZOS)

                # Flatten onto white so GIF palette conversion stays stable.
                canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                canvas.alpha_composite(rgba)
                frames.append(
                    canvas.convert("RGB").convert(
                        "P", palette=Image.Palette.ADAPTIVE, colors=255
                    )
                )
                durations.append(max(20, int(frame.info.get("duration", 100) or 100)))

            if not frames:
                return False, "Pillow found no frames in source image"

            if fps is not None and fps > 0:
                durations = [max(20, int(round(1000 / fps)))] * len(frames)

            frames[0].save(
                output_path,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=0,
                optimize=False,
            )
    except Exception as exc:  # noqa: BLE001 - conversion boundary
        _safe_unlink(output_path)
        return False, str(exc)

    if not output_path.is_file() or output_path.stat().st_size < MIN_GIF_BYTES:
        _safe_unlink(output_path)
        return False, "Pillow produced empty GIF"
    return True, ""


def _looks_like_webp(path: Path) -> bool:
    """Detect WebP by magic bytes (RIFF....WEBP).

    Parameters:
        path: Local file path.

    Returns:
        True when the file content looks like WebP.
    """
    try:
        with path.open("rb") as handle:
            header = handle.read(12)
    except OSError:
        return False
    return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"


def _short_error(message: str, limit: int = 280) -> str:
    """Keep API errors readable instead of dumping full ffmpeg banners.

    Parameters:
        message: Raw error text.
        limit: Maximum characters to keep.

    Returns:
        Trimmed error string focused on the last useful lines.
    """
    text = (message or "").strip()
    if not text:
        return "unknown encoder error"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    useful = [
        line
        for line in lines
        if not line.lower().startswith("ffmpeg version")
        and "configuration:" not in line.lower()
        and not line.startswith("--")
        and not line.startswith("libav")
        and not line.startswith("built with")
    ]
    picked = useful[-6:] if useful else lines[-6:]
    compact = " | ".join(picked)
    if len(compact) > limit:
        return compact[-limit:]
    return compact


def _safe_unlink(path: Path) -> None:
    """Delete a temp file if present, ignoring lock/race errors.

    Parameters:
        path: File to remove.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


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
