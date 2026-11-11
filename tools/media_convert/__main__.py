"""Allow ``python -m tools.media_convert`` from the toolkit root."""

from tools.media_convert.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
