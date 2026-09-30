"""API nghe-chép: lấy câu bài tập ngẫu nhiên, nộp bài và nhận so sánh chi tiết."""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db.database import get_conn
from app.dictation.diff import char_diff
from app.logging_config import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/dictation")


def _ok(data):
    return {"ok": True, "data": data}


def _loi(error_vi: str, status: int = 400):
    return JSONResponse(status_code=status, content={"ok": False, "error_vi": error_vi})


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _co_bang(conn, ten_bang: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (ten_bang,)
    ).fetchone()
    return row is not None


class SourceIn(BaseModel):
    cau_trung: str
    pinyin: Optional[str] = None
    nghia_vi: Optional[str] = None
    audio_path: Optional[str] = None


class SubmitIn(BaseModel):
    source_id: Optional[int] = None
    vocab_id: Optional[int] = None
    cau_dung: Optional[str] = None
    cau_nguoi_dung: str = ""
    answer: Optional[str] = None  # alias cho cau_nguoi_dung (frontend)


@router.get("/sources")
def list_sources(limit: int = Query(default=50, ge=1, le=500)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM dictation_sources ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return _ok([dict(r) for r in rows])


@router.post("/sources")
def create_source(body: SourceIn):
    cau = (body.cau_trung or "").strip()
    if not cau:
        return _loi("Câu tiếng Trung không được để trống.")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO dictation_sources (cau_trung, pinyin, nghia_vi, audio_path)"
            " VALUES (?, ?, ?, ?)",
            (cau, body.pinyin, body.nghia_vi, body.audio_path),
        )
        row = conn.execute(
            "SELECT * FROM dictation_sources WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _ok(dict(row))


@router.get("/exercise")
def get_exercise():
    """Lấy ngẫu nhiên 1 câu làm bài nghe-chép.

    Ưu tiên nguồn dictation_sources; nếu trống thì dùng câu ví dụ trong từ vựng.
    Không trả đáp án ở đây — đáp án chỉ hiện sau khi nộp bài.
    """
    with get_conn() as conn:
        nguon = None
        if _co_bang(conn, "dictation_sources"):
            nguon = conn.execute(
                "SELECT * FROM dictation_sources ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
        if nguon:
            cau = nguon["cau_trung"] or ""
            return _ok(
                {
                    "source_id": nguon["id"],
                    "vocab_id": None,
                    "so_ky_tu": len(cau),
                    "co_audio": bool(nguon["audio_path"]),
                    "audio_path": nguon["audio_path"],
                }
            )
        # Fallback: câu ví dụ trong từ vựng.
        if _co_bang(conn, "vocab"):
            tu = conn.execute(
                """SELECT id, vi_du_trung FROM vocab
                   WHERE vi_du_trung IS NOT NULL AND TRIM(vi_du_trung) != ''
                   ORDER BY RANDOM() LIMIT 1"""
            ).fetchone()
            if tu:
                return _ok(
                    {
                        "source_id": None,
                        "vocab_id": tu["id"],
                        "so_ky_tu": len(tu["vi_du_trung"] or ""),
                        "co_audio": False,
                        "audio_path": None,
                    }
                )
    return _loi("Chưa có dữ liệu nghe chép. Hãy thêm từ vựng hoặc video trước.", 404)


@router.post("/submit")
def submit(body: SubmitIn):
    """Nộp bài nghe-chép: trả về diff từng ký tự + đáp án đúng + pinyin/nghĩa (nếu có).

    ``cau_dung`` có thể bỏ trống — khi đó server tự tra từ ``source_id``
    (dictation_sources) hoặc ``vocab_id`` (vocab.vi_du_trung).
    """
    cau_nguoi_dung = body.cau_nguoi_dung or body.answer or ""
    cau_dung = (body.cau_dung or "").strip()
    with get_conn() as conn:
        if not cau_dung and body.source_id and _co_bang(conn, "dictation_sources"):
            nguon = conn.execute(
                "SELECT cau_trung FROM dictation_sources WHERE id = ?",
                (body.source_id,),
            ).fetchone()
            if nguon and nguon["cau_trung"]:
                cau_dung = nguon["cau_trung"].strip()
        if not cau_dung and body.vocab_id and _co_bang(conn, "vocab"):
            tu = conn.execute(
                "SELECT vi_du_trung FROM vocab WHERE id = ?", (body.vocab_id,)
            ).fetchone()
            if tu and tu["vi_du_trung"]:
                cau_dung = tu["vi_du_trung"].strip()
    if not cau_dung:
        return _loi("Không xác định được câu đúng cho bài này. Hãy lấy câu mới và thử lại.")

    diff = char_diff(cau_dung, cau_nguoi_dung)
    dung_hoan_toan = cau_dung == cau_nguoi_dung.strip()

    pinyin = None
    nghia_vi = None
    with get_conn() as conn:
        if body.source_id and _co_bang(conn, "dictation_sources"):
            nguon = conn.execute(
                "SELECT pinyin, nghia_vi FROM dictation_sources WHERE id = ?",
                (body.source_id,),
            ).fetchone()
            if nguon:
                pinyin, nghia_vi = nguon["pinyin"], nguon["nghia_vi"]
        if pinyin is None and _co_bang(conn, "vocab"):
            tu = conn.execute(
                "SELECT pinyin_vidu, dich_vi FROM vocab WHERE vi_du_trung = ? LIMIT 1",
                (cau_dung,),
            ).fetchone()
            if tu:
                pinyin, nghia_vi = tu["pinyin_vidu"], tu["dich_vi"]
        dem = conn.execute(
            "SELECT COUNT(*) FROM dictation_attempts WHERE cau_dung = ?", (cau_dung,)
        ).fetchone()[0]
        so_lan_thu = int(dem or 0) + 1
        cur = conn.execute(
            """INSERT INTO dictation_attempts
               (cau_dung, cau_nguoi_dung, diff_json, so_lan_thu, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                cau_dung,
                cau_nguoi_dung,
                json.dumps(diff, ensure_ascii=False),
                so_lan_thu,
                _now(),
            ),
        )
        attempt_id = cur.lastrowid

    log.info("Nghe-chép: attempt_id=%s dung_hoan_toan=%s", attempt_id, dung_hoan_toan)
    return _ok(
        {
            "attempt_id": attempt_id,
            "diff": diff,
            "cau_dung": cau_dung,
            "cau_nguoi_dung": cau_nguoi_dung,
            "pinyin": pinyin,
            "nghia_vi": nghia_vi,
            "so_lan_thu": so_lan_thu,
            "dung_hoan_toan": dung_hoan_toan,
        }
    )


@router.get("/attempts")
def list_attempts(limit: int = Query(default=20, ge=1, le=200)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, cau_dung, cau_nguoi_dung, so_lan_thu, created_at"
            " FROM dictation_attempts ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return _ok([dict(r) for r in rows])
