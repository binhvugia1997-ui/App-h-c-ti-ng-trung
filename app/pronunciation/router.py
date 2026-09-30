"""API phát âm: nộp bản ghi âm để chấm điểm, xem lịch sử, hiệu chuẩn.

TRUNG THỰC: hiện chưa có engine chấm phát âm, nên mọi chỉ số (pronunciation,
rhythm, fluency, similarity) đều lưu NULL và trả về NULL — không bịa điểm.
Bản ghi âm được lưu lại để người học tự nghe đối chiếu với câu mẫu.
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db.database import get_conn
from app.logging_config import get_logger
from app.paths import RECORDINGS_DIR
from app.pronunciation.calibration import get_calibration, set_calibration

log = get_logger(__name__)

router = APIRouter(prefix="/api/pronunciation")

MAX_RECORDING_BYTES = 100 * 1024 * 1024

NHAN_XET_CHUA_CO_ENGINE = (
    "Chưa có engine chấm phát âm. Bản ghi đã được lưu, "
    "bạn có thể nghe lại để tự đối chiếu."
)


def _ok(data):
    return {"ok": True, "data": data}


def _loi(error_vi: str, status: int = 400):
    return JSONResponse(status_code=status, content={"ok": False, "error_vi": error_vi})


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_ext(filename: Optional[str]) -> str:
    suffix = Path(filename or "").suffix.lower()
    cleaned = "".join(c for c in suffix if c.isalnum())[:8]
    return f".{cleaned}" if cleaned else ".bin"


class CalibrationIn(BaseModel):
    gia_tri: Any


@router.post("/analyze")
async def analyze(
    target_sentence: str = Form(...),
    recording: Optional[UploadFile] = File(default=None),
):
    """Nộp câu mẫu (+ file ghi âm tùy chọn). Lưu bản ghi, tạo kết quả với metric = null."""
    cau = (target_sentence or "").strip()
    if not cau:
        return _loi("Câu mẫu không được để trống.")

    recording_path = None
    if recording is not None and recording.filename:
        dest_dir = RECORDINGS_DIR / "pronunciation"
        dest_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{uuid.uuid4().hex[:16]}{_safe_ext(recording.filename)}"
        dest = dest_dir / fname
        try:
            size = 0
            with dest.open("wb") as out:
                while True:
                    chunk = await recording.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_RECORDING_BYTES:
                        raise ValueError("File ghi âm quá lớn (tối đa 100MB).")
                    out.write(chunk)
            recording_path = f"pronunciation/{fname}"
        except ValueError as e:
            dest.unlink(missing_ok=True)
            return _loi(str(e))
        except Exception:
            dest.unlink(missing_ok=True)
            log.exception("Lỗi khi lưu file ghi âm phát âm")
            return _loi("Không lưu được file ghi âm. Vui lòng thử lại.", 500)
        finally:
            try:
                await recording.close()
            except Exception:
                pass

    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO pronunciation_results
               (target_sentence, recording_path, pronunciation, rhythm, fluency,
                similarity, nhan_xet_vi, created_at)
               VALUES (?, ?, NULL, NULL, NULL, NULL, ?, ?)""",
            (cau, recording_path, NHAN_XET_CHUA_CO_ENGINE, _now()),
        )
        row = conn.execute(
            "SELECT * FROM pronunciation_results WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    log.info("Đã lưu bản ghi phát âm id=%s (chưa chấm điểm)", cur.lastrowid)
    data = dict(row)
    # Alias thân thiện cho frontend: metrics + feedback
    data["metrics"] = {
        "accuracy": data.get("pronunciation"),
        "fluency": data.get("fluency"),
        "tone": data.get("rhythm"),
        "overall": data.get("similarity"),
    }
    data["feedback"] = data.get("nhan_xet_vi")
    return _ok(data)


@router.get("/results")
def list_results(limit: int = Query(default=20, ge=1, le=200)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pronunciation_results ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return _ok([dict(r) for r in rows])


@router.get("/results/{result_id}")
def get_result(result_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM pronunciation_results WHERE id = ?", (result_id,)
        ).fetchone()
    if not row:
        return _loi("Không tìm thấy kết quả.", 404)
    return _ok(dict(row))


@router.get("/calibration/{khoa}")
def read_calibration(khoa: str):
    khoa = (khoa or "").strip()
    if not khoa:
        return _loi("Khóa hiệu chuẩn không được để trống.")
    with get_conn() as conn:
        gia_tri = get_calibration(conn, khoa, default=None)
    return _ok({"khoa": khoa, "gia_tri": gia_tri})


@router.put("/calibration/{khoa}")
def write_calibration(khoa: str, body: CalibrationIn):
    khoa = (khoa or "").strip()
    if not khoa:
        return _loi("Khóa hiệu chuẩn không được để trống.")
    with get_conn() as conn:
        data = set_calibration(conn, khoa, body.gia_tri)
    return _ok(data)
