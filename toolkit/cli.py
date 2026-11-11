"""CLI entry for the toolkit platform."""

from __future__ import annotations

import argparse

from toolkit import __version__
from toolkit.config import load_settings


def build_parser() -> argparse.ArgumentParser:
    """Build the toolkit CLI parser.

    Returns:
        ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(prog="toolkit", description="Small-tools portal")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Start the toolkit web UI")
    serve.add_argument("--host", default=None, help="Bind host")
    serve.add_argument("--port", type=int, default=None, help="Bind port")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the toolkit CLI.

    Parameters:
        argv: Optional argument list.

    Returns:
        Process exit code.
    """
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        settings = load_settings()
        host = args.host or settings.host
        port = args.port or settings.port
        import uvicorn

        print(f"toolkit UI: http://{host}:{port}")
        uvicorn.run("toolkit.app:app", host=host, port=port, reload=False)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
