"""API dashboard: xem tổng hợp học tập, ghi nhận buổi học."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.dashboard.stats import get_summary
from app.db.database import get_conn
from app.logging_config import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/dashboard")


def _ok(data):
    return {"ok": True, "data": data}


def _loi(error_vi: str, status: int = 400):
    return JSONResponse(status_code=status, content={"ok": False, "error_vi": error_vi})


class LogIn(BaseModel):
    so_phut: int = Field(..., ge=0, le=1440, description="Số phút học (0-1440)")
    hoat_dong: str = Field(..., description="Hoạt động: hoc_tu_vung, on_tu_vung, shadowing, nghe_chep, ...")
    chi_tiet: Optional[str] = None


@router.get("/summary")
def summary():
    """Tổng hợp tình hình học tập (đếm thật từ DB)."""
    try:
        with get_conn() as conn:
            data = get_summary(conn)
    except Exception:
        log.exception("Lỗi khi tính dashboard summary")
        return _loi("Không tính được thống kê lúc này. Vui lòng thử lại.", 500)
    return _ok(data)


@router.post("/log")
def log_study(body: LogIn):
    """Ghi nhận một buổi/hoạt động học."""
    hoat_dong = (body.hoat_dong or "").strip()
    if not hoat_dong:
        return _loi("Hoạt động học không được để trống.")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO study_events (ngay, so_phut, hoat_dong, chi_tiet, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                date.today().isoformat(),
                body.so_phut,
                hoat_dong,
                (body.chi_tiet or "").strip() or None,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        row = conn.execute("SELECT * FROM study_events WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _ok(dict(row))
