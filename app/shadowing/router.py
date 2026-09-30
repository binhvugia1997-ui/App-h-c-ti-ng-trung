"""API shadowing: quản lý câu mẫu, tải lên bản ghi âm, phát lại bản ghi."""

import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.db.database import get_conn
from app.logging_config import get_logger
from app.paths import RECORDINGS_DIR

log = get_logger(__name__)

router = APIRouter(prefix="/api/shadowing")

# Giới hạn chống tải file quá lớn lên server (100 MB).
MAX_RECORDING_BYTES = 100 * 1024 * 1024

_AUDIO_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".webm": "audio/webm",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".amr": "audio/amr",
}


def _ok(data):
    return {"ok": True, "data": data}


def _loi(error_vi: str, status: int = 400):
    return JSONResponse(status_code=status, content={"ok": False, "error_vi": error_vi})


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_ext(filename: Optional[str]) -> str:
    """Lấy phần mở rộng an toàn từ tên file gốc (chỉ giữ chữ/số)."""
    suffix = Path(filename or "").suffix.lower()
    cleaned = "".join(c for c in suffix if c.isalnum())[:8]
    return f".{cleaned}" if cleaned else ".bin"


class SessionIn(BaseModel):
    cau_chuan: str
    pinyin: Optional[str] = None
    nghia_vi: Optional[str] = None


@router.get("/sessions")
def list_sessions(limit: int = Query(default=50, ge=1, le=500)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM shadowing_sessions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return _ok([dict(r) for r in rows])


@router.post("/sessions")
def create_session(body: SessionIn):
    cau_chuan = (body.cau_chuan or "").strip()
    if not cau_chuan:
        return _loi("Câu mẫu không được để trống.")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO shadowing_sessions (cau_chuan, pinyin, nghia_vi, recording_path, created_at)"
            " VALUES (?, ?, ?, NULL, ?)",
            (cau_chuan, body.pinyin, body.nghia_vi, _now()),
        )
        row = conn.execute(
            "SELECT * FROM shadowing_sessions WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _ok(dict(row))


@router.get("/sessions/{session_id}")
def get_session(session_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM shadowing_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if not row:
        return _loi("Không tìm thấy buổi shadowing.", 404)
    return _ok(dict(row))


@router.post("/sessions/{session_id}/recording")
async def upload_recording(session_id: int, file: UploadFile = File(...)):
    """Tải lên bản ghi âm cho một buổi shadowing. Lưu vào RECORDINGS_DIR/shadowing/."""
    with get_conn() as conn:
        ton_tai = conn.execute(
            "SELECT 1 FROM shadowing_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if not ton_tai:
        return _loi("Không tìm thấy buổi shadowing.", 404)
    if not file or not file.filename:
        return _loi("Chưa chọn file ghi âm.")

    dest_dir = RECORDINGS_DIR / "shadowing"
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{session_id}_{uuid.uuid4().hex[:12]}{_safe_ext(file.filename)}"
    dest = dest_dir / fname
    try:
        size = 0
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RECORDING_BYTES:
                    raise ValueError("File ghi âm quá lớn (tối đa 100MB).")
                out.write(chunk)
    except ValueError as e:
        dest.unlink(missing_ok=True)
        return _loi(str(e))
    except Exception:
        dest.unlink(missing_ok=True)
        log.exception("Lỗi khi lưu file ghi âm shadowing session_id=%s", session_id)
        return _loi("Không lưu được file ghi âm. Vui lòng thử lại.", 500)
    finally:
        try:
            await file.close()
        except Exception:
            pass

    rel_path = f"shadowing/{fname}"
    with get_conn() as conn:
        conn.execute(
            "UPDATE shadowing_sessions SET recording_path = ? WHERE id = ?",
            (rel_path, session_id),
        )
        row = conn.execute(
            "SELECT * FROM shadowing_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    log.info("Đã lưu ghi âm shadowing session_id=%s -> %s", session_id, rel_path)
    return _ok(dict(row))


@router.get("/recordings/{filename}")
def get_recording(filename: str):
    """Phát lại file ghi âm. Chặn path traversal: chỉ phục vụ file trong thư mục shadowing."""
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        return _loi("Tên file không hợp lệ.")
    base = (RECORDINGS_DIR / "shadowing").resolve()
    target = (base / filename).resolve()
    if base not in target.parents:
        return _loi("Tên file không hợp lệ.")
    if not target.is_file():
        return _loi("Không tìm thấy file ghi âm.", 404)
    media_type = _AUDIO_MIME.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(str(target), media_type=media_type, filename=filename)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, recording_path FROM shadowing_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            return _loi("Không tìm thấy buổi shadowing.", 404)
        conn.execute("DELETE FROM shadowing_sessions WHERE id = ?", (session_id,))
    # Xóa file ghi âm đi kèm nếu còn (best-effort, không lỗi nếu thiếu).
    if row["recording_path"]:
        try:
            f = (RECORDINGS_DIR / row["recording_path"]).resolve()
            base = RECORDINGS_DIR.resolve()
            if base in f.parents and f.is_file():
                f.unlink()
        except Exception:
            log.warning("Không xóa được file ghi âm %s", row["recording_path"], exc_info=False)
    log.info("Đã xóa buổi shadowing id=%s", session_id)
    return _ok({"deleted": True, "id": session_id})
