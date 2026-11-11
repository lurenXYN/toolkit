"""Optional CLI for media-convert (prefer the toolkit portal)."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from tools.media_convert import __version__
from tools.media_convert.convert import convert
from tools.media_convert.download import resolve_input
from tools.media_convert.inspect import inspect_media
from tools.media_convert.sizeutil import format_size, parse_size


def build_parser() -> argparse.ArgumentParser:
    """Build the media-convert CLI parser.

    Returns:
        ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="media-convert",
        description="Convert animated WebP to GIF (prefer: python -m toolkit serve)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    convert_parser = sub.add_parser("convert", help="Convert WebP/image to gif/png/jpg")
    convert_parser.add_argument("source", help="Local file path or http(s) URL")
    convert_parser.add_argument("-o", "--output", help="Output file path")
    convert_parser.add_argument(
        "-f", "--format", choices=["gif", "png", "jpg", "jpeg"], help="Output format"
    )
    convert_parser.add_argument("--max-size", help="Max output size, e.g. 5m")

    info_parser = sub.add_parser("info", help="Inspect a local WebP/image or URL")
    info_parser.add_argument("source", help="Local file path or http(s) URL")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the media-convert CLI.

    Parameters:
        argv: Optional argument list.

    Returns:
        Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "info":
            with tempfile.TemporaryDirectory(prefix="media-convert-") as tmp:
                path = resolve_input(args.source, Path(tmp))
                info = inspect_media(path)
                print(f"path: {path}")
                print(f"size: {info.width}x{info.height}")
                print(f"frames: {info.frame_count}")
                print(f"animated: {info.is_animated}")
            return 0

        if args.command == "convert":
            max_bytes = parse_size(args.max_size) if args.max_size else None
            fmt = args.format
            if fmt == "jpeg":
                fmt = "jpg"
            output = Path(args.output) if args.output else Path.cwd() / "out.gif"
            if fmt is None:
                fmt = output.suffix.lstrip(".").lower() or "gif"
            with tempfile.TemporaryDirectory(prefix="media-convert-") as tmp:
                input_path = resolve_input(args.source, Path(tmp))
                result = convert(input_path, output, fmt=fmt, max_bytes=max_bytes)
            print(f"output: {result.output}")
            print(f"bytes: {format_size(result.bytes)}")
            return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
