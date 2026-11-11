"""Tool registry shown on the toolkit home page."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolCard:
    """One tool entry on the portal."""

    id: str
    name: str
    summary: str
    href: str
    status: str = "ready"  # ready | soon


TOOLS: tuple[ToolCard, ...] = (
    ToolCard(
        id="media-convert",
        name="动图 WebP → GIF",
        summary="本地/链接 WebP 转 GIF，可限制体积（如 ≤5MB）。也支持 PNG/JPG。",
        href="/tools/media-convert/",
        status="ready",
    ),
    ToolCard(
        id="coming-soon",
        name="更多工具",
        summary="下一个小工具位，稍后接入。",
        href="#",
        status="soon",
    ),
)


def list_tools() -> list[dict]:
    """Serialize tool cards for the API / template.

    Returns:
        List of tool dictionaries.
    """
    return [
        {
            "id": tool.id,
            "name": tool.name,
            "summary": tool.summary,
            "href": tool.href,
            "status": tool.status,
        }
        for tool in TOOLS
    ]
