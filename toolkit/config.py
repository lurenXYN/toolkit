"""Toolkit runtime configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """Process settings for the toolkit server."""

    host: str
    port: int
    root: Path

    @property
    def static_dir(self) -> Path:
        """Directory that holds portal and tool HTML.

        Returns:
            Absolute static directory path.
        """
        return self.root / "static"

    @property
    def data_dir(self) -> Path:
        """Persistent data root (outputs, etc.).

        Returns:
            Absolute data directory path.
        """
        return self.root / "data"

    @property
    def media_output_dir(self) -> Path:
        """Converted media output directory.

        Returns:
            Absolute output directory for media-convert.
        """
        return self.data_dir / "outputs" / "media-convert"


def load_settings() -> Settings:
    """Load settings from environment variables.

    Returns:
        Settings instance.
    """
    return Settings(
        host=os.getenv("TOOLKIT_HOST", "127.0.0.1"),
        port=int(os.getenv("TOOLKIT_PORT", "8780")),
        root=ROOT,
    )
