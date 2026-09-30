"""Chấm bài dịch Việt -> Trung bằng Qwen.

analyze_viet_trung(cau_vi, cau_trung_cua_ban) -> dict theo schema:
{
  "correct": bool, "score": None,
  "original": str, "corrected": str, "pinyin": str, "translation": str,
  "errors": [...], "grammar": [...], "vocabulary": [...],
  "explanation_vi": str, "alternatives": [...]
}
Giải thích theo cấu trúc SAI Ở ĐÂU -> VÌ SAO SAI -> SỬA THẾ NÀO, bằng tiếng Việt.
"""

from __future__ import annotations

from app.logging_config import get_logger
from app.qwen.client import QwenError, get_qwen_client

log = get_logger(__name__)

_SYSTEM_VT = """Bạn là giáo viên tiếng Trung giàu kinh nghiệm, dạy cho người Việt.
Nhiệm vụ: chấm câu tiếng Trung mà học viên tự dịch từ một câu tiếng Việt cho trước,
rồi giải thích lỗi hoàn toàn bằng TIẾNG VIỆT.

YÊU CẦU TRẢ LỜI: chỉ trả về JSON thuần (KHÔNG dùng markdown code fence,
không viết chữ giải thích ngoài JSON), đúng schema sau:
{
  "correct": true/false,
  "score": null,
  "original": "<câu tiếng Trung của học viên, giữ nguyên>",
  "corrected": "<câu tiếng Trung đúng, tự nhiên nhất>",
  "pinyin": "<pinyin của câu đúng, có dấu thanh>",
  "translation": "<nghĩa tiếng Việt của câu đúng>",
  "errors": [
    {"type": "<loại lỗi: từ vựng/ngữ pháp/trật tự từ/thiếu từ/thừa từ>",
     "detail_vi": "<mô tả lỗi bằng tiếng Việt>",
     "fix_vi": "<cách sửa bằng tiếng Việt>"}
  ],
  "grammar": ["<điểm ngữ pháp liên quan cần nhớ, tiếng Việt>"],
  "vocabulary": [{"word": "<từ>", "pinyin": "<pinyin>", "meaning_vi": "<nghĩa>"}],
  "explanation_vi": "<giải thích chi tiết>",
  "alternatives": ["<cách diễn đạt khác tự nhiên hơn, nếu có>"]
}

Quy tắc bắt buộc:
- "explanation_vi" viết bằng tiếng Việt, theo đúng 3 bước:
  1) SAI Ở ĐÂU: chỉ ra cụ thể chỗ sai trong câu của học viên.
  2) VÌ SAO SAI: giải thích nguyên nhân (ngữ pháp/từ vựng/thói quen tiếng Việt).
  3) SỬA THẾ NÀO: đưa câu sửa đúng và lý do chọn cách sửa đó.
- "score": LUÔN để null (không tự chấm điểm số).
- Nếu câu của học viên đúng hoàn toàn: "correct": true, "errors": [],
  "explanation_vi" khen ngắn gọn và gợi ý cách nói nâng cao nếu có.
- "alternatives": 1-2 cách diễn đạt khác tự nhiên (có thể bỏ trống mảng nếu không có).
- "vocabulary": chỉ liệt kê từ mới/khó đáng học trong câu (tối đa 8 từ).
- Pinyin phải có dấu thanh (ví dụ: nǐ hǎo)."""


def _user_prompt(cau_vi: str, cau_trung_cua_ban: str) -> str:
    return (
        "Câu tiếng Việt gốc:\n" + cau_vi.strip()
        + "\n\nCâu tiếng Trung của học viên:\n" + cau_trung_cua_ban.strip()
        + "\n\nHãy chấm và phân tích theo đúng schema JSON ở trên."
    )


def _normalize(raw: dict, cau_vi: str, cau_trung_cua_ban: str) -> dict:
    """Chuẩn hoá kết quả AI về đúng schema, không bịa score (luôn None)."""
    if not isinstance(raw, dict):
        raise QwenError(
            "AI trả về dữ liệu không đúng định dạng, vui lòng thử lại."
        )
    correct = raw.get("correct")
    correct = bool(correct) if isinstance(correct, bool) else None

    def _as_list(v):
        return v if isinstance(v, list) else []

    def _as_str(v, fallback=""):
        return v if isinstance(v, str) else fallback

    return {
        "correct": correct,
        "score": None,  # không có cơ sở chấm điểm số -> null, không bịa
        "original": _as_str(raw.get("original"), cau_trung_cua_ban.strip()),
        "corrected": _as_str(raw.get("corrected")),
        "pinyin": _as_str(raw.get("pinyin")),
        "translation": _as_str(raw.get("translation"), cau_vi.strip()),
        "errors": _as_list(raw.get("errors")),
        "grammar": _as_list(raw.get("grammar")),
        "vocabulary": _as_list(raw.get("vocabulary")),
        "explanation_vi": _as_str(raw.get("explanation_vi")),
        "alternatives": _as_list(raw.get("alternatives")),
    }


def analyze_viet_trung(cau_vi: str, cau_trung_cua_ban: str) -> dict:
    """Chấm câu tiếng Trung do học viên dịch từ câu tiếng Việt.

    Raise QwenError (message tiếng Việt) khi thiếu input hoặc AI lỗi.
    """
    if not cau_vi or not cau_vi.strip():
        raise QwenError("Vui lòng nhập câu tiếng Việt cần dịch.")
    if not cau_trung_cua_ban or not cau_trung_cua_ban.strip():
        raise QwenError("Vui lòng nhập câu tiếng Trung của bạn để chấm.")
    log.info("Chấm bài Việt-Trung (độ dài câu VI: %d ký tự)", len(cau_vi.strip()))
    client = get_qwen_client()
    raw = client.chat_json(_SYSTEM_VT, _user_prompt(cau_vi, cau_trung_cua_ban))
    return _normalize(raw, cau_vi, cau_trung_cua_ban)
