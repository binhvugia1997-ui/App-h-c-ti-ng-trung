"""Quản lý background job cho pipeline xử lý video.

Job được lưu persistent trong SQLite (bảng ``video_jobs``) nên sống sót qua
restart. Job chạy trong ``threading.Thread`` daemon qua ``start_job``.

Trạng thái: queued -> processing -> completed | failed | cancelled.
"""

import threading
import uuid
from datetime import datetime, timezone

from app.db.database import get_conn
from app.logging_config import get_logger
from app.video import tables as video_tables

log = get_logger(__name__)

STATUSES = ("queued", "processing", "completed", "failed", "cancelled")
ACTIVE_STATUSES = ("queued", "processing")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    """Tạo / truy vấn / cập nhật / hủy job video chạy nền."""

    def __init__(self) -> None:
        self._threads: dict[str, threading.Thread] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create_job(self, video_id: str) -> str:
        """Tạo job mới ở trạng thái queued, trả về job_id (uuid hex)."""
        job_id = uuid.uuid4().hex
        now = _now_iso()
        with get_conn() as conn:
            video_tables.init_db(conn)
            conn.execute(
                """INSERT INTO video_jobs
                   (id, video_id, status, stage, progress, error_vi,
                    checkpoint_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job_id, video_id, "queued", "", 0, None, None, now, now),
            )
        log.info("Đã tạo job video %s cho video_id=%s", job_id, video_id)
        return job_id

    def get_job(self, job_id: str) -> dict | None:
        """Lấy job theo id; không tồn tại -> None."""
        with get_conn() as conn:
            video_tables.init_db(conn)
            row = conn.execute(
                "SELECT * FROM video_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_jobs(self, limit: int = 50) -> list[dict]:
        """Liệt kê job mới nhất trước, giới hạn 1..200."""
        try:
            limit = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            limit = 50
        with get_conn() as conn:
            video_tables.init_db(conn)
            rows = conn.execute(
                "SELECT * FROM video_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_status(
        self,
        job_id: str,
        status: str,
        stage: str | None = None,
        progress: int | None = None,
        error_vi: str | None = None,
    ) -> bool:
        """Đổi trạng thái job. ``error_vi=None`` nghĩa là giữ nguyên giá trị cũ;
        truyền chuỗi rỗng để xóa lỗi."""
        if status not in STATUSES:
            raise ValueError(f"Trạng thái job không hợp lệ: {status}")
        sets = ["status = ?", "updated_at = ?"]
        params: list = [status, _now_iso()]
        if stage is not None:
            sets.append("stage = ?")
            params.append(stage)
        if progress is not None:
            sets.append("progress = ?")
            params.append(int(progress))
        if error_vi is not None:
            sets.append("error_vi = ?")
            params.append(error_vi)
        params.append(job_id)
        with get_conn() as conn:
            video_tables.init_db(conn)
            cur = conn.execute(
                f"UPDATE video_jobs SET {', '.join(sets)} WHERE id = ?", params
            )
            return cur.rowcount > 0

    def update_progress(
        self,
        job_id: str,
        stage: str,
        progress: int,
        error_vi: str | None = None,
    ) -> bool:
        """Cập nhật stage + % tiến trình (không đổi status)."""
        sets = ["stage = ?", "progress = ?", "updated_at = ?"]
        params: list = [stage, int(progress), _now_iso()]
        if error_vi is not None:
            sets.append("error_vi = ?")
            params.append(error_vi)
        params.append(job_id)
        with get_conn() as conn:
            video_tables.init_db(conn)
            cur = conn.execute(
                f"UPDATE video_jobs SET {', '.join(sets)} WHERE id = ?", params
            )
            return cur.rowcount > 0

    def cancel_job(self, job_id: str) -> bool:
        """Hủy job. Chỉ hủy được khi đang queued/processing -> True."""
        job = self.get_job(job_id)
        if not job or job.get("status") not in ACTIVE_STATUSES:
            return False
        ok = self.set_status(job_id, "cancelled")
        if ok:
            log.info("Đã hủy job video %s", job_id)
        return ok

    # ------------------------------------------------------------------
    # Chạy nền & phục hồi
    # ------------------------------------------------------------------
    def start_job(self, job_id: str) -> bool:
        """Chạy ``pipeline.run_job`` trong daemon thread. Job không tồn tại -> False."""
        from app.video import pipeline  # import lazy để tránh vòng lặp import

        job = self.get_job(job_id)
        if not job:
            return False
        thread = threading.Thread(
            target=pipeline.run_job,
            args=(job_id,),
            daemon=True,
            name=f"video-job-{job_id[:8]}",
        )
        self._threads[job_id] = thread
        thread.start()
        log.info("Đã khởi động job video %s ở chế độ nền", job_id)
        return True

    def recover_on_startup(self) -> int:
        """Khi server restart: job nào còn 'processing' -> 'failed' (giữ checkpoint
        để có thể chạy lại từ điểm dừng). Trả về số job đã phục hồi."""
        message = (
            "Tiến trình bị gián đoạn do server restart. "
            "Có thể chạy lại từ checkpoint."
        )
        with get_conn() as conn:
            video_tables.init_db(conn)
            rows = conn.execute(
                "SELECT id FROM video_jobs WHERE status = 'processing'"
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE video_jobs SET status = 'failed', error_vi = ?, "
                    "updated_at = ? WHERE id = ?",
                    (message, _now_iso(), row["id"]),
                )
        count = len(rows)
        if count:
            log.warning(
                "Phục hồi %d job video bị gián đoạn do restart (giữ nguyên checkpoint).",
                count,
            )
        return count


# Instance dùng chung cho router và pipeline.
job_manager = JobManager()
