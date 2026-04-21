"""Sanctum Forge — document conversion service.

Minimal subset of FORGE_SPEC.md covering:
  GET  /health
  GET  /formats
  POST /import      — file → canonical markdown + blocks
"""
from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from .blocks import parse_blocks
from .importers import SUPPORTED_IMPORT, dispatch

logging.basicConfig(level=os.environ.get("FORGE_LOG_LEVEL", "INFO"))
logger = logging.getLogger("forge")

app = FastAPI(title="Sanctum Forge", version="0.1.0")

_BOOT_AT = time.time()


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "version": app.version,
        "uptime_s": int(time.time() - _BOOT_AT),
    }


@app.get("/formats")
async def formats() -> dict:
    return {
        "import": SUPPORTED_IMPORT,
        "export": [],  # v0: import-only
    }


@app.post("/import")
async def import_file(file: UploadFile = File(...)) -> JSONResponse:
    raw = await file.read()
    started = time.time()
    try:
        result = dispatch(file.filename or "", file.content_type, raw)
    except Exception as exc:
        logger.warning("import failed for %s: %s", file.filename, exc)
        return JSONResponse(
            {"ok": False, "error": {"code": "IMPORT_FAILED", "message": str(exc)}},
            status_code=400,
        )

    blocks = parse_blocks(result.markdown)
    elapsed_ms = int((time.time() - started) * 1000)
    return JSONResponse({
        "ok": True,
        "data": {
            "markdown": result.markdown,
            "blocks": [b.to_dict() for b in blocks],
            "metadata": result.metadata,
            "stats": {
                "bytes_in": len(raw),
                "elapsed_ms": elapsed_ms,
                "backend": result.backend,
                "filename": file.filename,
            },
        },
    })
