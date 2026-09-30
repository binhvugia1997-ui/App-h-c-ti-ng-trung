"""Checkpoint / resume cho pipeline xử lý video.

Mỗi job lưu một file JSON tại ``DATA_DIR/"video"/"checkpoints"/{job_id}.json``
với cấu trúc::

    {
      "job_id": "...",
      "stages": {
        "<stage>": {"done": bool, "data": {...}, "updated_at": "..."}
      },
      "updated_at": "..."
    }

Pipeline dùng ``is_stage_done`` để bỏ qua stage đã hoàn thành khi chạy lại.
Ghi file theo kiểu atomic (ghi file tạm rồi rename) để không hỏng dữ liệu
khi server tắt đột ngột.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from app.logging_config import get_logger
from app.paths import DATA_DIR

log = get_logger(__name__)

STAGES = [
    "imported",
    "audio_extracted",
    "transcribed",
    "segmented",
    "translated",
    "lesson_generated",
]


def _checkpoint_dir() -> Path:
    directory = DATA_DIR / "video" / "checkpoints"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _safe_job_id(job_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", str(job_id or ""))
    return cleaned or "job"


def _path(job_id: str) -> Path:
    return _checkpoint_dir() / f"{_safe_job_id(job_id)}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _blank(job_id: str) -> dict:
    return {"job_id": job_id, "stages": {}, "updated_at": _now_iso()}


def load_checkpoint(job_id: str) -> dict | None:
    """Đọc checkpoint của job. Không có / hỏng -> None (không raise)."""
    path = _path(job_id)
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("Không đọc được checkpoint của job %s: %s", job_id, exc)
        return None


def _write(job_id: str, payload: dict) -> None:
    path = _path(job_id)
    tmp = path.with_suffix(".json.tmp")
    payload["job_id"] = job_id
    payload["updated_at"] = _now_iso()
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def save_checkpoint(job_id: str, stage: str, data: dict) -> dict:
    """Lưu dữ liệu trung gian của một stage (chưa đánh dấu hoàn thành)."""
    payload = load_checkpoint(job_id) or _blank(job_id)
    stages = payload.setdefault("stages", {})
    entry = stages.get(stage) or {}
    if not isinstance(entry, dict):
        entry = {}
    entry["data"] = dict(data or {})
    entry["done"] = bool(entry.get("done", False))
    entry["updated_at"] = _now_iso()
    stages[stage] = entry
    _write(job_id, payload)
    return payload


def mark_stage_done(job_id: str, stage: str) -> dict:
    """Đánh dấu một stage đã hoàn thành (giữ nguyên dữ liệu đã lưu)."""
    payload = load_checkpoint(job_id) or _blank(job_id)
    stages = payload.setdefault("stages", {})
    entry = stages.get(stage) or {}
    if not isinstance(entry, dict):
        entry = {}
    entry.setdefault("data", {})
    entry["done"] = True
    entry["updated_at"] = _now_iso()
    stages[stage] = entry
    _write(job_id, payload)
    return payload


def is_stage_done(job_id: str, stage: str) -> bool:
    """True nếu stage đã được đánh dấu hoàn thành trong checkpoint."""
    payload = load_checkpoint(job_id)
    if not payload:
        return False
    entry = payload.get("stages", {}).get(stage)
    return bool(isinstance(entry, dict) and entry.get("done"))


def get_stage_data(job_id: str, stage: str) -> dict:
    """Lấy dữ liệu đã lưu của một stage; thiếu -> {}."""
    payload = load_checkpoint(job_id)
    if not payload:
        return {}
    entry = payload.get("stages", {}).get(stage) or {}
    data = entry.get("data") if isinstance(entry, dict) else None
    return data if isinstance(data, dict) else {}
