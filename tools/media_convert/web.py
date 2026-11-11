"""FastAPI router for the media-convert tool."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from tools.media_convert.cleanup import cleanup_outputs
from tools.media_convert.convert import convert
from tools.media_convert.download import resolve_input
from tools.media_convert.inspect import inspect_media
from tools.media_convert.sizeutil import format_size, parse_size

logger = logging.getLogger(__name__)


def create_router(output_dir: Path, page_html: Path) -> APIRouter:
    """Build the media-convert API + page router.

    Parameters:
        output_dir: Directory for converted outputs.
        page_html: Path to the tool HTML page.

    Returns:
        Configured APIRouter mounted by the toolkit app.
    """
    router = APIRouter()
    output_dir.mkdir(parents=True, exist_ok=True)

    def run_output_cleanup() -> None:
        """Apply dual retention cleanup on converted outputs."""
        report = cleanup_outputs(output_dir)
        if report.deleted:
            logger.info(
                "media-convert cleanup deleted=%s freed=%s remaining=%s",
                report.deleted,
                format_size(report.freed_bytes),
                report.remaining,
            )

    @router.get("/", response_class=HTMLResponse)
    def tool_page() -> HTMLResponse:
        """Serve the media-convert UI page.

        Returns:
            HTML page response.
        """
        html = page_html.read_text(encoding="utf-8")
        return HTMLResponse(html)

    @router.get("/api/health")
    def health() -> dict:
        """Tool-level health check.

        Returns:
            Status payload.
        """
        return {"status": "ok", "tool": "media-convert"}

    @router.post("/api/convert")
    async def api_convert(
        file: UploadFile | None = File(default=None),
        url: str = Form(default=""),
        fmt: str = Form(default="gif"),
        max_size: str = Form(default="5m"),
    ) -> dict:
        """Convert an uploaded file or remote URL.

        Parameters:
            file: Optional uploaded media.
            url: Optional remote URL.
            fmt: Output format.
            max_size: Optional max size string.

        Returns:
            Conversion result payload with download URL.
        """
        fmt = (fmt or "gif").lower()
        if fmt == "jpeg":
            fmt = "jpg"
        if fmt not in {"gif", "png", "jpg"}:
            raise HTTPException(status_code=400, detail="format must be gif/png/jpg")

        source_url = (url or "").strip()
        if file is None and not source_url:
            raise HTTPException(status_code=400, detail="请上传文件或填写网络链接")
        if file is not None and source_url:
            raise HTTPException(status_code=400, detail="文件和链接请二选一")

        max_bytes = None
        if max_size.strip():
            try:
                max_bytes = parse_size(max_size)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"无效的体积上限: {exc}") from exc

        job_id = uuid.uuid4().hex[:12]

        try:
            with tempfile.TemporaryDirectory(
                prefix="media-convert-web-", ignore_cleanup_errors=True
            ) as tmp:
                tmp_dir = Path(tmp)
                if source_url:
                    input_path = resolve_input(source_url, tmp_dir)
                    stem = input_path.stem or "converted"
                else:
                    assert file is not None
                    suffix = Path(file.filename or "upload.webp").suffix.lower() or ".webp"
                    input_path = tmp_dir / f"upload{suffix}"
                    content = await file.read()
                    if not content:
                        raise HTTPException(status_code=400, detail="上传文件为空")
                    input_path.write_bytes(content)
                    stem = Path(file.filename or "upload").stem or "converted"

                info = inspect_media(input_path)
                output_name = f"{stem}-{job_id}.{fmt}"
                output_path = output_dir / output_name
                result = convert(input_path, output_path, fmt=fmt, max_bytes=max_bytes)

                payload = {
                    "ok": True,
                    "download_url": f"./api/download/{result.output.name}",
                    "filename": result.output.name,
                    "bytes": result.bytes,
                    "bytes_label": format_size(result.bytes),
                    "attempts": result.attempts,
                    "scale": result.scale,
                    "fps": result.fps,
                    "source": {
                        "width": info.width,
                        "height": info.height,
                        "frames": info.frame_count,
                        "animated": info.is_animated,
                    },
                }
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - API boundary
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        run_output_cleanup()
        return payload

    @router.get("/api/download/{filename}")
    def api_download(filename: str) -> FileResponse:
        """Download a previously converted file.

        Parameters:
            filename: Output filename.

        Returns:
            File download response.
        """
        safe_name = Path(filename).name
        path = output_dir / safe_name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="文件不存在或已清理")
        media_types = {
            ".gif": "image/gif",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        return FileResponse(
            path,
            media_type=media_types.get(path.suffix.lower(), "application/octet-stream"),
            filename=safe_name,
        )

    # Initial cleanup when router is created (app startup path).
    run_output_cleanup()
    return router
