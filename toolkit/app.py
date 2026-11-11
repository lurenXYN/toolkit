"""FastAPI application for the toolkit portal and tools."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from toolkit import __version__
from toolkit.config import load_settings
from toolkit.registry import list_tools
from tools.media_convert.web import create_router as create_media_convert_router

settings = load_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Ensure data directories exist on startup.

    Parameters:
        _app: FastAPI application.

    Yields:
        None while the app runs.
    """
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.media_output_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="toolkit", version=__version__, lifespan=lifespan)

static_dir = settings.static_dir
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

media_page = static_dir / "tools" / "media-convert.html"
app.include_router(
    create_media_convert_router(settings.media_output_dir, media_page),
    prefix="/tools/media-convert",
    tags=["media-convert"],
)


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    """Serve the toolkit portal home page.

    Returns:
        Portal HTML response.
    """
    return HTMLResponse((static_dir / "index.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict:
    """Platform health check.

    Returns:
        Status payload.
    """
    return {"status": "ok", "service": "toolkit", "version": __version__}


@app.get("/api/tools")
def api_tools() -> dict:
    """List registered tools for the portal.

    Returns:
        Tool card list.
    """
    return {"tools": list_tools()}


@app.get("/favicon.ico", response_model=None)
def favicon():
    """Optional favicon placeholder.

    Returns:
        Icon file response or empty 204 response.
    """
    icon = static_dir / "favicon.ico"
    if icon.is_file():
        return FileResponse(icon)
    return HTMLResponse(status_code=204, content="")
