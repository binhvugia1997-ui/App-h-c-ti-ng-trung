"""Orchestration pipeline xử lý video.

Mọi logic xử lý video nặng đều đi QUA ADAPTER (``adapter_process_video``) —
pipeline không gọi trực tiếp bất kỳ logic nào bên trong ``process_video.py``
và không đoán implementation của nó.

Luồng stage (xem ``checkpoints.STAGES``):
  imported -> audio_extracted -> transcribed -> segmented -> translated
  -> lesson_generated -> ghi DB -> completed

Quy tắc:
- Stage đã done trong checkpoint -> bỏ qua (log "bỏ qua stage đã hoàn thành").
- Adapter không sẵn sàng:
    * audio_extracted: thử trích audio bằng FFmpeg (bước trung gian tối thiểu).
    * transcribed: BẮT BUỘC có adapter/engine STT -> fail rõ ràng nếu thiếu.
    * translated: dùng Qwen nếu reachable; Qwen offline -> PARTIAL, vẫn lưu
      các trường đã có, không fail cả job.
    * các stage còn lại: fallback trung thực (không bịa kết quả).
- Mọi exception -> job failed + error_vi tiếng Việt thân thiện + log chi tiết.
"""

import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.db.database import get_conn
from app.logging_config import get_logger
from app.paths import DATA_DIR, MEDIA_DIR
from app.video import checkpoints
from app.video import jobs as jobs_module
from app.video import tables as video_tables
from app.video.adapter_process_video import (
    VideoModuleNotReady,
    is_available,
    run_stage,
)
from app.video.checkpoints import STAGES
from app.video.ffmpeg import detect_ffmpeg

log = get_logger(__name__)

QWEN_OFFLINE_NOTE = "Máy AI offline nên phần dịch tự động chưa hoàn tất."


class _FriendlyError(Exception):
    """Lỗi đã có thông điệp tiếng Việt thân thiện, dùng làm error_vi."""


class _JobCancelled(Exception):
    """Job bị hủy giữa chừng -> dừng pipeline trong yên lặng."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fail(job_id: str, error_vi: str) -> None:
    jobs_module.job_manager.set_status(job_id, "failed", error_vi=error_vi)
    log.warning("Job video %s thất bại: %s", job_id, error_vi)


def _is_cancelled(job_id: str) -> bool:
    job = jobs_module.job_manager.get_job(job_id)
    return bool(job and job.get("status") == "cancelled")


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def find_video_file(video_id: str) -> Path | None:
    """Tìm file video đã upload theo video_id (tên file bắt đầu bằng video_id)."""
    if not video_id or not MEDIA_DIR.is_dir():
        return None
    try:
        matches = [
            p for p in MEDIA_DIR.iterdir()
            if p.is_file() and p.name.startswith(video_id)
        ]
    except OSError as exc:
        log.warning("Không đọc được MEDIA_DIR: %s", exc)
        return None
    return sorted(matches)[0] if matches else None


# ----------------------------------------------------------------------
# Qwen (import an toàn, try/except)
# ----------------------------------------------------------------------
def _qwen_client():
    """Trả về Qwen client nếu reachable, ngược lại None (không raise)."""
    try:
        from app.qwen.client import get_qwen_client
    except Exception as exc:  # noqa: BLE001
        log.info("Không import được Qwen client: %s", exc)
        return None
    try:
        client = get_qwen_client()
        status = client.check()
    except Exception as exc:  # noqa: BLE001
        log.info("Không kết nối được Qwen: %s", exc)
        return None
    if not isinstance(status, dict) or not status.get("ok"):
        log.info("Qwen offline: %s", (status or {}).get("message_vi"))
        return None
    return client


def _translate_segment(client, seg: dict) -> dict:
    """Dịch 1 segment (chinese -> pinyin + vietnamese) bằng Qwen."""
    seg = dict(seg) if isinstance(seg, dict) else {}
    chinese = (seg.get("chinese") or "").strip()
    if not chinese or seg.get("vietnamese"):
        return seg
    system = (
        "Bạn là trợ lý dịch tiếng Trung. Chỉ trả về JSON hợp lệ, "
        "không thêm giải thích."
    )
    user = (
        "Hãy cho pinyin và nghĩa tiếng Việt của câu tiếng Trung sau. "
        'Trả về JSON đúng định dạng: {"pinyin": "...", "vietnamese": "..."}\n'
        f"Câu: {chinese}"
    )
    result = client.chat_json(system, user, timeout=60)
    if isinstance(result, dict):
        if result.get("pinyin"):
            seg["pinyin"] = result["pinyin"]
        if result.get("vietnamese"):
            seg["vietnamese"] = result["vietnamese"]
    return seg


# ----------------------------------------------------------------------
# Các stage
# ----------------------------------------------------------------------
def _handle_imported(job_id: str, job: dict) -> dict:
    video_id = job.get("video_id") or ""
    path = find_video_file(video_id)
    if path is None:
        raise _FriendlyError("Không tìm thấy file video. Vui lòng tải video lên lại.")
    data = {"video_id": video_id, "filename": path.name, "video_path": str(path)}
    if is_available():
        try:
            extra = run_stage(
                "imported", job_id=job_id, video_id=video_id,
                video_path=str(path), filename=path.name,
            )
            if isinstance(extra, dict):
                data.update(extra)
        except VideoModuleNotReady:
            pass  # adapter thiếu stage này -> dùng kết quả kiểm tra file
    return data


def _handle_audio_extracted(job_id: str, job: dict) -> dict:
    imported = checkpoints.get_stage_data(job_id, "imported")
    video_path = imported.get("video_path") or ""
    path = Path(video_path) if video_path else find_video_file(job.get("video_id") or "")
    if path is None or not path.is_file():
        raise _FriendlyError("Không tìm thấy file video để trích xuất âm thanh.")

    if is_available():
        try:
            result = run_stage("audio_extracted", job_id=job_id, video_path=str(path))
            data = result if isinstance(result, dict) else {}
            data.setdefault("video_path", str(path))
            data.setdefault("engine", "process_video")
            return data
        except VideoModuleNotReady:
            pass  # rơi xuống fallback FFmpeg bên dưới

    # Fallback tối thiểu: trích audio bằng FFmpeg (chưa cần adapter).
    ffmpeg = detect_ffmpeg()
    if not ffmpeg.get("ok"):
        raise _FriendlyError(
            ffmpeg.get("message_vi")
            or "Không tìm thấy FFmpeg. Vui lòng cài FFmpeg hoặc cấu hình đường dẫn trong Cài đặt."
        )
    out_dir = DATA_DIR / "video" / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{job_id}.wav"
    cmd = [
        ffmpeg["path"], "-y", "-i", str(path),
        "-vn", "-ac", "1", "-ar", "16000", str(out_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise _FriendlyError(
            "Trích xuất âm thanh quá lâu và đã bị dừng. Vui lòng thử video ngắn hơn."
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Lỗi khi chạy FFmpeg cho job %s: %s", job_id, exc)
        raise _FriendlyError("Không thể trích xuất âm thanh từ video. Vui lòng thử lại.")
    if proc.returncode != 0 or not out_path.is_file():
        log.error("FFmpeg thất bại cho job %s: %s", job_id, (proc.stderr or "")[-500:])
        raise _FriendlyError(
            "Không thể trích xuất âm thanh từ video. "
            "File có thể bị hỏng hoặc không đúng định dạng."
        )
    log.info("Job %s: đã trích audio bằng FFmpeg -> %s", job_id, out_path)
    return {"audio_path": str(out_path), "video_path": str(path), "engine": "ffmpeg"}


def _handle_transcribed(job_id: str, job: dict) -> dict:
    audio = checkpoints.get_stage_data(job_id, "audio_extracted")
    audio_path = audio.get("audio_path")
    if not audio_path:
        raise _FriendlyError("Chưa có file âm thanh để nhận dạng giọng nói.")
    if is_available():
        try:
            result = run_stage("transcribed", job_id=job_id, audio_path=audio_path)
            data = result if isinstance(result, dict) else {}
            data.setdefault("audio_path", audio_path)
            return data
        except VideoModuleNotReady:
            pass
    # Nhận dạng giọng nói bắt buộc cần engine STT (nằm trong process_video
    # bản FINAL) -> không bịa transcript, fail rõ ràng.
    raise _FriendlyError(
        "Chưa có engine speech-to-text. "
        "Vui lòng cập nhật file process_video.py bản FINAL."
    )


def _handle_segmented(job_id: str, job: dict) -> dict:
    transcript = checkpoints.get_stage_data(job_id, "transcribed")
    if is_available():
        try:
            result = run_stage("segmented", job_id=job_id, transcript=transcript)
            data = result if isinstance(result, dict) else {}
            data.setdefault("segments", [])
            return data
        except VideoModuleNotReady:
            pass
    segments = transcript.get("segments")
    if isinstance(segments, list):
        return {"segments": segments}
    text = (transcript.get("text") or "").strip()
    if text:
        return {"segments": [{
            "start_time": 0.0, "end_time": 0.0,
            "chinese": text, "pinyin": "", "vietnamese": "",
        }]}
    return {"segments": []}


def _handle_translated(job_id: str, job: dict) -> dict:
    seg_data = checkpoints.get_stage_data(job_id, "segmented")
    segments = seg_data.get("segments")
    if not isinstance(segments, list):
        segments = []

    if is_available():
        try:
            result = run_stage("translated", job_id=job_id, segments=segments)
            data = result if isinstance(result, dict) else {}
            data.setdefault("segments", segments)
            return data
        except VideoModuleNotReady:
            pass

    client = _qwen_client()
    if client is None:
        log.info("Job %s: Qwen offline -> stage translated PARTIAL.", job_id)
        return {
            "segments": segments,
            "partial": True,
            "note_vi": QWEN_OFFLINE_NOTE,
            "engine": None,
        }
    try:
        translated = [_translate_segment(client, seg) for seg in segments]
    except Exception as exc:  # noqa: BLE001 - QwenError hoặc lỗi mạng
        log.warning("Job %s: dịch bằng Qwen thất bại: %s", job_id, exc)
        return {
            "segments": segments,
            "partial": True,
            "note_vi": QWEN_OFFLINE_NOTE,
            "engine": "qwen",
        }
    return {"segments": translated, "engine": "qwen"}


def _handle_lesson_generated(job_id: str, job: dict) -> dict:
    if is_available():
        try:
            result = run_stage("lesson_generated", job_id=job_id)
            if isinstance(result, dict):
                return result
        except VideoModuleNotReady:
            pass
    imported = checkpoints.get_stage_data(job_id, "imported")
    filename = imported.get("filename") or "video"
    title = Path(filename).stem.replace("_", " ").strip() or f"Bài học {job_id[:8]}"
    return {"title": title}


_STAGE_HANDLERS = {
    "imported": _handle_imported,
    "audio_extracted": _handle_audio_extracted,
    "transcribed": _handle_transcribed,
    "segmented": _handle_segmented,
    "translated": _handle_translated,
    "lesson_generated": _handle_lesson_generated,
}


# ----------------------------------------------------------------------
# Finalize: ghi bài học + segments vào DB
# ----------------------------------------------------------------------
def _collect_segments(job_id: str) -> tuple[list[dict], list[str]]:
    """Lấy segments từ stage gần nhất có dữ liệu + các cảnh báo partial."""
    warnings: list[str] = []
    for stage in ("lesson_generated", "translated", "segmented", "transcribed"):
        data = checkpoints.get_stage_data(job_id, stage)
        note = data.get("note_vi")
        if data.get("partial") and note and note not in warnings:
            warnings.append(str(note))
        segments = data.get("segments")
        if isinstance(segments, list) and segments:
            return [s for s in segments if isinstance(s, dict)], warnings
    return [], warnings


def _finalize(job_id: str) -> str:
    """Ghi video_lessons + video_segments. Trả về lesson_id."""
    manager = jobs_module.job_manager
    job = manager.get_job(job_id) or {}
    lesson_id = uuid.uuid4().hex

    segments, warnings = _collect_segments(job_id)
    lesson_data = checkpoints.get_stage_data(job_id, "lesson_generated")
    title = (lesson_data.get("title") or "").strip() or f"Bài học video {job_id[:8]}"
    imported = checkpoints.get_stage_data(job_id, "imported")
    video_path = imported.get("filename") or ""  # lưu tên file (portable)

    if warnings:
        log.warning("Job %s hoàn thành với cảnh báo: %s", job_id, " | ".join(warnings))

    now = _now_iso()
    with get_conn() as conn:
        video_tables.init_db(conn)
        conn.execute(
            "INSERT INTO video_lessons (id, job_id, title, video_path, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (lesson_id, job_id, title, video_path, now),
        )
        for idx, seg in enumerate(segments):
            conn.execute(
                """INSERT INTO video_segments
                   (lesson_id, idx, start_time, end_time, chinese, pinyin, vietnamese)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    lesson_id,
                    idx,
                    _num(seg.get("start_time", seg.get("start"))),
                    _num(seg.get("end_time", seg.get("end"))),
                    seg.get("chinese") or "",
                    seg.get("pinyin") or "",
                    seg.get("vietnamese") or "",
                ),
            )
    log.info(
        "Job %s: đã lưu bài học %s với %d segments.", job_id, lesson_id, len(segments)
    )
    return lesson_id


# ----------------------------------------------------------------------
# Entry point chạy trong background thread
# ----------------------------------------------------------------------
def run_job(job_id: str) -> None:
    """Chạy toàn bộ pipeline cho job. Không bao giờ raise ra ngoài."""
    manager = jobs_module.job_manager
    job = manager.get_job(job_id)
    if not job:
        log.error("Không tìm thấy job video %s, bỏ qua.", job_id)
        return
    if job.get("status") not in ("queued", "processing", "failed"):
        log.info(
            "Job video %s đang ở trạng thái %s, không chạy lại.",
            job_id, job.get("status"),
        )
        return

    manager.set_status(job_id, "processing", error_vi="")
    log.info(
        "Bắt đầu job video %s (video_id=%s)", job_id, job.get("video_id")
    )
    try:
        total = len(STAGES)
        for index, stage in enumerate(STAGES):
            if _is_cancelled(job_id):
                raise _JobCancelled()
            if checkpoints.is_stage_done(job_id, stage):
                log.info("Job %s: bỏ qua stage đã hoàn thành: %s", job_id, stage)
                continue
            manager.update_progress(job_id, stage, int(index * 90 / total))
            handler = _STAGE_HANDLERS[stage]
            current_job = manager.get_job(job_id) or {}
            data = handler(job_id, current_job)
            checkpoints.save_checkpoint(job_id, stage, data or {})
            checkpoints.mark_stage_done(job_id, stage)
            log.info("Job %s: hoàn thành stage %s", job_id, stage)

        lesson_id = _finalize(job_id)
        manager.set_status(job_id, "completed", stage="done", progress=100, error_vi="")
        log.info("Job video %s hoàn thành (lesson_id=%s).", job_id, lesson_id)
    except _JobCancelled:
        log.info("Job video %s đã bị hủy, dừng pipeline.", job_id)
    except VideoModuleNotReady as exc:
        _fail(job_id, str(exc))
    except _FriendlyError as exc:
        _fail(job_id, str(exc))
    except Exception:  # noqa: BLE001
        log.exception("Job video %s gặp lỗi không mong đợi", job_id)
        _fail(
            job_id,
            "Đã xảy ra lỗi không mong đợi khi xử lý video. "
            "Vui lòng thử lại hoặc kiểm tra nhật ký.",
        )
