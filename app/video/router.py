"""API Video Learning (prefix /api/video).

Endpoints:
- POST   /upload               : tải video lên (lưu vào MEDIA_DIR, trả video_id)
- POST   /jobs                 : tạo + khởi động job xử lý từ {video_id}
- GET    /jobs?limit=50        : liệt kê job
- GET    /jobs/{job_id}        : chi tiết job (kèm checkpoint)
- POST   /jobs/{job_id}/cancel : hủy job đang queued/processing
- GET    /lessons              : liệt kê bài học
- GET    /lessons/{lesson_id}  : bài học kèm segments
- GET    /status               : trạng thái FFmpeg / adapter / danh sách stage

Mọi response tuân thủ {"ok": true/false, ...}, lỗi dùng "error_vi" tiếng Việt,
không lộ stack trace.
"""

import re
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel

from app.db.database import get_conn
from app.logging_config import get_logger
from app.paths import MEDIA_DIR
from app.video import checkpoints
from app.video import tables as video_tables
from app.video.adapter_process_video import is_available, list_supported_stages
from app.video.checkpoints import STAGES
from app.video.ffmpeg import detect_ffmpeg
from app.video.jobs import job_manager
from app.video.pipeline import find_video_file

log = get_logger(__name__)

router = APIRouter(prefix="/api/video")


class CreateJobBody(BaseModel):
    video_id: str


def _safe_filename(original: str) -> str:
    name = Path(original or "video").name
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._") or "video"
    if len(safe) > 120:
        stem, dot, ext = safe.rpartition(".")
        safe = (stem[: 110 - len(ext)] + dot + ext) if dot else safe[:120]
    return safe


# ----------------------------------------------------------------------
# Upload
# ----------------------------------------------------------------------
@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Nhận file video, lưu vào MEDIA_DIR với tên an toàn, trả về video_id."""
    try:
        video_id = uuid.uuid4().hex
        filename = f"{video_id}_{_safe_filename(file.filename or 'video')}"
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        dest = MEDIA_DIR / filename
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        log.info("Đã upload video %s (%s)", video_id, filename)
        return {"ok": True, "data": {"video_id": video_id, "filename": filename}}
    except Exception:  # noqa: BLE001
        log.exception("Upload video thất bại")
        return {"ok": False, "error_vi": "Tải video lên thất bại. Vui lòng thử lại."}
    finally:
        try:
            await file.close()
        except Exception:  # noqa: BLE001
            pass


# ----------------------------------------------------------------------
# Jobs
# ----------------------------------------------------------------------
@router.post("/jobs")
def create_and_start_job(body: CreateJobBody):
    """Tạo job xử lý video từ video_id đã upload và khởi động ngay."""
    video_id = (body.video_id or "").strip()
    if not video_id or find_video_file(video_id) is None:
        return {
            "ok": False,
            "error_vi": "Không tìm thấy video. Vui lòng tải video lên lại.",
        }
    try:
        job_id = job_manager.create_job(video_id)
        job_manager.start_job(job_id)
        return {"ok": True, "data": {"job_id": job_id, "video_id": video_id}}
    except Exception:  # noqa: BLE001
        log.exception("Không tạo được job video")
        return {
            "ok": False,
            "error_vi": "Không tạo được tiến trình xử lý. Vui lòng thử lại.",
        }


@router.get("/jobs")
def list_jobs(limit: int = Query(default=50, ge=1, le=200)):
    try:
        return {"ok": True, "data": job_manager.list_jobs(limit=limit)}
    except Exception:  # noqa: BLE001
        log.exception("Lỗi liệt kê job video")
        return {"ok": False, "error_vi": "Không tải được danh sách tiến trình."}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    try:
        job = job_manager.get_job(job_id)
        if not job:
            return {"ok": False, "error_vi": "Không tìm thấy tiến trình."}
        job["checkpoint"] = checkpoints.load_checkpoint(job_id)
        return {"ok": True, "data": job}
    except Exception:  # noqa: BLE001
        log.exception("Lỗi đọc job video %s", job_id)
        return {"ok": False, "error_vi": "Không tải được thông tin tiến trình."}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    try:
        if job_manager.cancel_job(job_id):
            return {"ok": True, "data": {"job_id": job_id, "cancelled": True}}
        job = job_manager.get_job(job_id)
        if not job:
            return {"ok": False, "error_vi": "Không tìm thấy tiến trình."}
        return {
            "ok": False,
            "error_vi": "Tiến trình đã kết thúc nên không thể hủy.",
        }
    except Exception:  # noqa: BLE001
        log.exception("Lỗi hủy job video %s", job_id)
        return {"ok": False, "error_vi": "Không hủy được tiến trình. Vui lòng thử lại."}


# ----------------------------------------------------------------------
# Lessons
# ----------------------------------------------------------------------
@router.get("/lessons")
def list_lessons(limit: int = Query(default=50, ge=1, le=200)):
    try:
        with get_conn() as conn:
            video_tables.init_db(conn)
            rows = conn.execute(
                """SELECT l.*, COUNT(s.id) AS segment_count
                   FROM video_lessons l
                   LEFT JOIN video_segments s ON s.lesson_id = l.id
                   GROUP BY l.id
                   ORDER BY l.created_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return {"ok": True, "data": [dict(row) for row in rows]}
    except Exception:  # noqa: BLE001
        log.exception("Lỗi liệt kê bài học video")
        return {"ok": False, "error_vi": "Không tải được danh sách bài học."}


@router.get("/lessons/{lesson_id}")
def get_lesson(lesson_id: str):
    try:
        with get_conn() as conn:
            video_tables.init_db(conn)
            lesson = conn.execute(
                "SELECT * FROM video_lessons WHERE id = ?", (lesson_id,)
            ).fetchone()
            if not lesson:
                return {"ok": False, "error_vi": "Không tìm thấy bài học."}
            lesson_d = dict(lesson)
            segments = [
                {
                    "start": row["start_time"],
                    "end": row["end_time"],
                    "hanzi": row["chinese"],
                    "pinyin": row["pinyin"],
                    "vi": row["vietnamese"],
                }
                for row in conn.execute(
                    "SELECT * FROM video_segments WHERE lesson_id = ? ORDER BY idx ASC",
                    (lesson_id,),
                ).fetchall()
            ]
        return {
            "ok": True,
            "data": {
                "id": lesson_d.get("id"),
                "title": lesson_d.get("title"),
                "video_url": None,
                "segments": segments,
            },
        }
    except Exception:  # noqa: BLE001
        log.exception("Lỗi đọc bài học video %s", lesson_id)
        return {"ok": False, "error_vi": "Không tải được bài học."}


# ----------------------------------------------------------------------
# Trạng thái hệ thống của module video
# ----------------------------------------------------------------------
@router.get("/status")
def video_status():
    try:
        return {
            "ok": True,
            "data": {
                "ffmpeg": detect_ffmpeg(),
                "adapter": {
                    "available": is_available(),
                    "stages": list_supported_stages(),
                },
                "stages": STAGES,
            },
        }
    except Exception:  # noqa: BLE001
        log.exception("Lỗi đọc trạng thái module video")
        return {"ok": False, "error_vi": "Không đọc được trạng thái module video."}
