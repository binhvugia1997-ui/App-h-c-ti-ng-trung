"""API backup: tạo và liệt kê các bản sao lưu."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.backup.backup import create_backup, list_backups
from app.logging_config import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/backup")


class BackupIn(BaseModel):
    ghi_chu: Optional[str] = None


@router.post("/")
def post_backup(body: Optional[BackupIn] = None):
    """Tạo một bản backup mới. Trả về {"ok": true, "data": {...}}."""
    try:
        result = create_backup((body.ghi_chu if body else "") or "")
        return {"ok": True, "data": result}
    except Exception:  # noqa: BLE001
        log.exception("Tạo backup qua API thất bại")
        return {"ok": False, "error_vi": "Sao lưu thất bại. Vui lòng thử lại."}


@router.get("/")
def get_backups():
    """Liệt kê các bản backup hiện có, mới nhất trước."""
    try:
        return {"ok": True, "data": list_backups()}
    except Exception:  # noqa: BLE001
        log.exception("Lỗi liệt kê backup qua API")
        return {"ok": False, "error_vi": "Không tải được danh sách bản sao lưu."}
