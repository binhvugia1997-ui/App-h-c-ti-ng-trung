"""Router /api/trash: xóa mềm, liệt kê, khôi phục, xóa vĩnh viễn."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.logging_config import get_logger
from app.trash.trash import list_trash, permanent_delete, restore_trash, soft_delete

log = get_logger(__name__)

router = APIRouter(prefix="/api/trash")


class SoftDeleteBody(BaseModel):
    duong_dan_goc: str


@router.get("/")
def api_list_trash():
    """Liệt kê các mục trong thùng rác."""
    try:
        return {"ok": True, "data": list_trash()}
    except Exception as exc:  # noqa: BLE001
        log.error("GET /api/trash lỗi: %s", exc)
        return {"ok": False, "error_vi": "Không đọc được thùng rác, vui lòng thử lại."}


@router.post("/")
def api_soft_delete(body: SoftDeleteBody):
    """Xóa mềm một file/thư mục (đưa vào thùng rác)."""
    try:
        return soft_delete(body.duong_dan_goc)
    except Exception as exc:  # noqa: BLE001
        log.error("POST /api/trash lỗi: %s", exc)
        return {"ok": False, "error_vi": "Không xóa được, vui lòng thử lại."}


@router.post("/restore/{item_id}")
def api_restore_trash(item_id: str):
    """Khôi phục một mục từ thùng rác về vị trí gốc."""
    try:
        return restore_trash(item_id)
    except Exception as exc:  # noqa: BLE001
        log.error("POST /api/trash/restore/%s lỗi: %s", item_id, exc)
        return {"ok": False, "error_vi": "Không khôi phục được, vui lòng thử lại."}


@router.delete("/{item_id}")
def api_permanent_delete(item_id: str, confirm: str = Query(default="")):
    """Xóa vĩnh viễn một mục. Bắt buộc ``?confirm=yes``."""
    try:
        if confirm.lower() != "yes":
            return {"ok": False,
                    "error_vi": "Xóa vĩnh viễn cần xác nhận: thêm ?confirm=yes vào URL."}
        return permanent_delete(item_id, xac_nhan=True)
    except Exception as exc:  # noqa: BLE001
        log.error("DELETE /api/trash/%s lỗi: %s", item_id, exc)
        return {"ok": False, "error_vi": "Không xóa được, vui lòng thử lại."}
