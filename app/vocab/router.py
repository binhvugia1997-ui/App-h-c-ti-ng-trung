"""API từ vựng: CRUD, flashcards đến hạn ôn, ghi nhận ôn tập (SRS)."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.db.database import get_conn
from app.logging_config import get_logger
from app.vocab.srs import schedule_review

log = get_logger(__name__)

router = APIRouter(prefix="/api/vocab")


def _ok(data):
    return {"ok": True, "data": data}


def _loi(error_vi: str, status: int = 400):
    return JSONResponse(status_code=status, content={"ok": False, "error_vi": error_vi})


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class VocabIn(BaseModel):
    hanzi: str
    pinyin: Optional[str] = None
    nghia_vi: Optional[str] = None
    loai_tu: Optional[str] = None
    vi_du_trung: Optional[str] = None
    pinyin_vidu: Optional[str] = None
    dich_vi: Optional[str] = None
    audio_path: Optional[str] = None


class VocabUpdate(BaseModel):
    hanzi: Optional[str] = None
    pinyin: Optional[str] = None
    nghia_vi: Optional[str] = None
    loai_tu: Optional[str] = None
    vi_du_trung: Optional[str] = None
    pinyin_vidu: Optional[str] = None
    dich_vi: Optional[str] = None
    audio_path: Optional[str] = None
    trang_thai: Optional[str] = None


class ReviewIn(BaseModel):
    muc_do: int = Field(..., ge=0, le=5, description="Mức độ nhớ tự đánh giá: 0 (quên hẳn) - 5 (nhớ rất rõ)")


@router.get("/flashcards")
def flashcards(limit: int = Query(default=20, ge=1, le=100)):
    """Thẻ ôn tập: các từ đến hạn ôn trả về trước, sau đó đến từ mới chưa lên lịch."""
    hom_nay = date.today().isoformat()
    with get_conn() as conn:
        den_han = conn.execute(
            """SELECT * FROM vocab
               WHERE ngay_can_on IS NOT NULL AND ngay_can_on <= ?
               ORDER BY ngay_can_on ASC LIMIT ?""",
            (hom_nay, limit),
        ).fetchall()
        cards = [dict(r) for r in den_han]
        if len(cards) < limit:
            moi = conn.execute(
                """SELECT * FROM vocab WHERE ngay_can_on IS NULL
                   ORDER BY id DESC LIMIT ?""",
                (limit - len(cards),),
            ).fetchall()
            cards.extend(dict(r) for r in moi)
    return _ok(cards)


@router.get("/")
def list_vocab(
    q: Optional[str] = Query(default=None, description="Tìm theo chữ Hán / nghĩa / pinyin"),
    limit: int = Query(default=200, ge=1, le=1000),
):
    with get_conn() as conn:
        if q and q.strip():
            like = f"%{q.strip()}%"
            rows = conn.execute(
                """SELECT * FROM vocab
                   WHERE hanzi LIKE ? OR nghia_vi LIKE ? OR pinyin LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (like, like, like, limit),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM vocab ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return _ok([dict(r) for r in rows])


@router.get("/{vocab_id}")
def get_vocab(vocab_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
    if not row:
        return _loi("Không tìm thấy từ vựng.", 404)
    return _ok(dict(row))


@router.post("/")
def create_vocab(body: VocabIn):
    hanzi = (body.hanzi or "").strip()
    if not hanzi:
        return _loi("Chữ Hán không được để trống.")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO vocab (hanzi, pinyin, nghia_vi, loai_tu, vi_du_trung,
                                  pinyin_vidu, dich_vi, audio_path, trang_thai, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'moi', ?)""",
            (
                hanzi, body.pinyin, body.nghia_vi, body.loai_tu, body.vi_du_trung,
                body.pinyin_vidu, body.dich_vi, body.audio_path, _now(),
            ),
        )
        row = conn.execute("SELECT * FROM vocab WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _ok(dict(row))


@router.put("/{vocab_id}")
def update_vocab(vocab_id: int, body: VocabUpdate):
    data = dict(body.model_dump(exclude_unset=True))
    if "hanzi" in data and not (data["hanzi"] or "").strip():
        return _loi("Chữ Hán không được để trống.")
    if not data:
        return _loi("Không có gì để cập nhật.")
    cols = ", ".join(f"{k} = ?" for k in data)
    with get_conn() as conn:
        cur = conn.execute(f"UPDATE vocab SET {cols} WHERE id = ?", (*data.values(), vocab_id))
        if cur.rowcount == 0:
            return _loi("Không tìm thấy từ vựng.", 404)
        row = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
    return _ok(dict(row))


@router.delete("/{vocab_id}")
def delete_vocab(vocab_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT id, hanzi FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
        if not row:
            return _loi("Không tìm thấy từ vựng.", 404)
        conn.execute("DELETE FROM vocab WHERE id = ?", (vocab_id,))
    log.info("Đã xóa từ vựng id=%s hanzi=%s", vocab_id, row["hanzi"])
    return _ok({"deleted": True, "id": vocab_id})


@router.post("/{vocab_id}/review")
def review_vocab(vocab_id: int, body: ReviewIn):
    """Ghi nhận một lần ôn tập với mức độ nhớ do người học tự đánh giá (0-5)."""
    try:
        with get_conn() as conn:
            data = schedule_review(conn, vocab_id, body.muc_do)
            _ghi_su_kien_hoc(conn, "on_tu_vung", f"Ôn từ '{data.get('hanzi')}' (mức {body.muc_do}/5)")
    except ValueError:
        return _loi("Không tìm thấy từ vựng.", 404)
    except Exception:
        log.exception("Lỗi khi ghi nhận ôn tập vocab_id=%s", vocab_id)
        return _loi("Không ghi nhận được lần ôn tập. Vui lòng thử lại.", 500)
    return _ok(data)


def _ghi_su_kien_hoc(conn, hoat_dong: str, chi_tiet: str) -> None:
    """Ghi sự kiện học vào dashboard nếu bảng study_events đã được khởi tạo."""
    try:
        ton_tai = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'study_events'"
        ).fetchone()
        if ton_tai:
            conn.execute(
                "INSERT INTO study_events (ngay, so_phut, hoat_dong, chi_tiet, created_at)"
                " VALUES (?, NULL, ?, ?, ?)",
                (date.today().isoformat(), hoat_dong, chi_tiet, _now()),
            )
    except Exception:
        log.warning("Không ghi được sự kiện học vào study_events", exc_info=False)
