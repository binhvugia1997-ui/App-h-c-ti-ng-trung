"""Router /api/exercises: bài tập dịch AI Việt-Trung / Trung-Việt + lịch sử.

- POST /viet-trung   {cau_vi, cau_trung_cua_ban} -> chấm bài dịch Việt-Trung
- POST /trung-viet   {cau_trung, cau_vi_cua_ban?} -> dịch/chấm Trung-Việt
- GET  /history?limit=20 -> lịch sử bài đã chấm

QwenError -> HTTP 502 {"ok": false, "error_vi": ...}.
Kết quả thành công được lưu vào bảng ai_exercise_history.
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.ai_exercises.trung_viet import analyze_trung_viet
from app.ai_exercises.viet_trung import analyze_viet_trung
from app.db.database import get_conn
from app.logging_config import get_logger
from app.qwen.client import QwenError

log = get_logger(__name__)

router = APIRouter(prefix="/api/exercises")


# ------------------------------------------------------------------ schemas
class VietTrungRequest(BaseModel):
    cau_vi: str = Field(..., description="Câu tiếng Việt gốc")
    cau_trung_cua_ban: str | None = Field(
        default="",
        description="Câu tiếng Trung của học viên (có thể để trống để chỉ xin câu đề xuất)",
    )


class TrungVietRequest(BaseModel):
    cau_trung: str = Field(..., description="Câu tiếng Trung cần dịch")
    cau_vi_cua_ban: str | None = Field(
        default=None, description="Bản dịch tiếng Việt của học viên (tuỳ chọn)"
    )


# ------------------------------------------------------------------ helpers
def _ok(data) -> dict:
    return {"ok": True, "data": data}


def _err_vi(message: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "error_vi": message})


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _save_history(
    direction: str, input_text: str, user_answer: str | None, result: dict
) -> None:
    """Lưu một lượt chấm vào ai_exercise_history. Lỗi lưu không chặn response."""
    try:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO ai_exercise_history
                    (direction, input_text, user_answer, result_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    direction,
                    input_text,
                    user_answer,
                    json.dumps(result, ensure_ascii=False),
                    _now_iso(),
                ),
            )
    except Exception as exc:  # noqa: BLE001 - lịch sử là phụ, không chặn kết quả
        log.warning("Không lưu được lịch sử bài tập: %s", exc)


def _handle_qwen_error(exc: QwenError) -> JSONResponse:
    return _err_vi(str(exc), 502)


# ------------------------------------------------------------------- routes
@router.post("/viet-trung")
def post_viet_trung(body: VietTrungRequest):
    """Chấm câu tiếng Trung mà học viên dịch từ câu tiếng Việt."""
    try:
        result = analyze_viet_trung(body.cau_vi, body.cau_trung_cua_ban or "")
    except QwenError as exc:
        return _handle_qwen_error(exc)
    except Exception:  # noqa: BLE001 - không lộ stack trace cho client
        log.exception("Lỗi không mong muốn ở POST /api/exercises/viet-trung")
        return _err_vi("Đã xảy ra lỗi không mong muốn, vui lòng thử lại.", 500)
    _save_history("viet-trung", body.cau_vi.strip(), (body.cau_trung_cua_ban or "").strip(), result)
    return _ok(result)


@router.post("/trung-viet")
def post_trung_viet(body: TrungVietRequest):
    """Dịch câu tiếng Trung sang tiếng Việt; chấm nếu học viên có nộp bản dịch."""
    try:
        result = analyze_trung_viet(body.cau_trung, body.cau_vi_cua_ban)
    except QwenError as exc:
        return _handle_qwen_error(exc)
    except Exception:  # noqa: BLE001 - không lộ stack trace cho client
        log.exception("Lỗi không mong muốn ở POST /api/exercises/trung-viet")
        return _err_vi("Đã xảy ra lỗi không mong muốn, vui lòng thử lại.", 500)
    _save_history(
        "trung-viet",
        body.cau_trung.strip(),
        body.cau_vi_cua_ban.strip() if body.cau_vi_cua_ban else None,
        result,
    )
    return _ok(result)


@router.get("/history")
def get_history(limit: int = Query(default=20, ge=1, le=100)):
    """Lấy lịch sử các bài đã chấm, mới nhất trước."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, direction, input_text, user_answer, result_json, created_at
                FROM ai_exercise_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except Exception:  # noqa: BLE001
        log.exception("Lỗi đọc lịch sử bài tập")
        return _err_vi("Không đọc được lịch sử, vui lòng thử lại.", 500)

    items = []
    for r in rows:
        try:
            result = json.loads(r["result_json"]) if r["result_json"] else None
        except (ValueError, TypeError):
            result = None
        items.append(
            {
                "id": r["id"],
                "direction": r["direction"],
                "input_text": r["input_text"],
                "user_answer": r["user_answer"],
                "result": result,
                "created_at": r["created_at"],
            }
        )
    return _ok(items)
