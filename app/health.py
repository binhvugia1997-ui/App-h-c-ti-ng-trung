"""GET /api/health — kiểm tra sức khỏe hệ thống.

Phân biệt rõ CORE (database, storage) và EXTERNAL (ffmpeg, qwen,
google_drive). Qwen offline → ``external.qwen.status = "DOWN"`` nhưng
``app`` vẫn ``"UP"`` — app không crash khi service ngoài lỗi.
"""
from __future__ import annotations

import asyncio
import shutil
import time
import urllib.request
from typing import Any

from fastapi import APIRouter

from app import config as _config
from app.db.database import get_conn
from app.logging_config import get_logger
from app.paths import DATA_DIR

log = get_logger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])

_QWEN_TIMEOUT_S = 3


def _check_database() -> str:
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
        return "UP"
    except Exception as exc:
        log.warning("Health check: database DOWN (%r).", exc)
        return "DOWN"


def _check_storage() -> str:
    try:
        if not DATA_DIR.is_dir():
            return "DOWN"
        probe = DATA_DIR / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return "UP"
    except Exception as exc:
        log.warning("Health check: storage DOWN (%r).", exc)
        return "DOWN"


def _check_ffmpeg() -> dict[str, Any]:
    path = _config.settings.ffmpeg_path or shutil.which("ffmpeg") or ""
    if path:
        return {"status": "UP", "path": path}
    return {
        "status": "DOWN",
        "path": "",
        "message_vi": "Không tìm thấy ffmpeg trong hệ thống.",
    }


def _check_qwen_sync() -> dict[str, Any]:
    """Kiểm tra máy Qwen (Ollama) với timeout ngắn, không block app."""
    settings = _config.settings
    url = settings.qwen_base_url.rstrip("/") + "/api/tags"
    started = time.monotonic()
    try:
        req = urllib.request.Request(
            url, method="GET", headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=_QWEN_TIMEOUT_S) as resp:
            latency_ms = int((time.monotonic() - started) * 1000)
            if resp.status == 200:
                return {
                    "status": "UP",
                    "model": settings.qwen_model,
                    "latency_ms": latency_ms,
                    "message_vi": "Kết nối máy Qwen bình thường.",
                }
            return {
                "status": "DOWN",
                "model": settings.qwen_model,
                "latency_ms": latency_ms,
                "message_vi": f"Máy Qwen trả mã lỗi {resp.status}.",
            }
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        log.warning("Health check: qwen DOWN (%r).", exc)
        return {
            "status": "DOWN",
            "model": settings.qwen_model,
            "latency_ms": latency_ms,
            "message_vi": (
                "Không kết nối được máy Qwen. "
                "Các tính năng AI sẽ tạm thời không khả dụng."
            ),
        }


async def _check_qwen() -> dict[str, Any]:
    return await asyncio.to_thread(_check_qwen_sync)


@router.get("/")
async def health() -> dict[str, Any]:
    database = await asyncio.to_thread(_check_database)
    storage = await asyncio.to_thread(_check_storage)
    ffmpeg = await asyncio.to_thread(_check_ffmpeg)
    qwen = await _check_qwen()
    return {
        "ok": True,
        "data": {
            "app": "UP",
            "core": {
                "database": database,
                "storage": storage,
            },
            "external": {
                "ffmpeg": ffmpeg,
                "qwen": qwen,
                "google_drive": "NOT_CONFIGURED",
            },
        },
    }
