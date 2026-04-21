"""Async HTTP client for Sanctum Forge.

Every Sanctum Suite app calls Forge through this client instead of
re-implementing PDF/DOCX/HTML/image parsing. Mirrors the shape
translachat's in-tree forge_client.py established — import_file()
for the common case, plus health and formats helpers.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FORGE_URL: str = os.environ.get("FORGE_URL", "http://localhost:8200")
_DEFAULT_CONNECT_TIMEOUT = float(os.environ.get("FORGE_TIMEOUT_CONNECT", "10.0"))
_DEFAULT_READ_TIMEOUT = float(os.environ.get("FORGE_TIMEOUT_READ", "180.0"))


class ForgeError(RuntimeError):
    """Forge returned ok=false or the HTTP call failed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class ForgeImport:
    """Result of a POST /import call."""
    markdown: str
    blocks: list[dict[str, Any]]
    metadata: dict[str, Any]
    stats: dict[str, Any]


def _timeout(connect: float | None = None, read: float | None = None) -> httpx.Timeout:
    return httpx.Timeout(
        connect=connect if connect is not None else _DEFAULT_CONNECT_TIMEOUT,
        read=read if read is not None else _DEFAULT_READ_TIMEOUT,
        write=30.0,
        pool=60.0,
    )


async def forge_health(base_url: str | None = None) -> bool:
    """Is Forge reachable? Swallows errors, returns bool."""
    url = base_url or FORGE_URL
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def get_formats(base_url: str | None = None) -> dict:
    """List supported import/export formats."""
    url = base_url or FORGE_URL
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(f"{url}/formats")
        resp.raise_for_status()
        return resp.json()


async def import_file(
    filename: str,
    mime: str | None,
    raw: bytes,
    *,
    base_url: str | None = None,
    connect_timeout: float | None = None,
    read_timeout: float | None = None,
) -> ForgeImport:
    """Convert `raw` file bytes to canonical markdown + structured blocks.

    Returns a ForgeImport with markdown, blocks, metadata, stats.
    Raises ForgeError on conversion failure.
    """
    url = base_url or FORGE_URL
    async with httpx.AsyncClient(timeout=_timeout(connect_timeout, read_timeout)) as client:
        files = {"file": (filename, raw, mime or "application/octet-stream")}
        resp = await client.post(f"{url}/import", files=files)
        resp.raise_for_status()
        body = resp.json()

    if not body.get("ok"):
        err = body.get("error") or {}
        raise ForgeError(
            code=err.get("code", "UNKNOWN"),
            message=err.get("message", ""),
        )

    data = body["data"]
    return ForgeImport(
        markdown=data["markdown"],
        blocks=data["blocks"],
        metadata=data.get("metadata") or {},
        stats=data.get("stats") or {},
    )
