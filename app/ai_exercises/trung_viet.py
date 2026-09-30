"""Chấm/dịch bài Trung -> Việt bằng Qwen.

analyze_trung_viet(cau_trung, cau_vi_cua_ban=None) -> dict theo schema:
{
  "correct": bool|None, "original": str, "pinyin": str, "translation": str,
  "errors": [...], "explanation_vi": str, "alternatives": [...]
}
- Nếu học viên không nhập bản dịch: chỉ dịch + giải thích (correct=None).
- Nếu có bản dịch: chấm đúng/sai và chỉ lỗi bằng tiếng Việt.
"""

from __future__ import annotations

from app.logging_config import get_logger
from app.qwen.client import QwenError, get_qwen_client

log = get_logger(__name__)

_SYSTEM_TV = """Bạn là giáo viên tiếng Trung giàu kinh nghiệm, dạy cho người Việt.
Nhiệm vụ:
1) Dịch câu tiếng Trung sang TIẾNG VIỆT tự nhiên, có đầy đủ dấu.
2) Giải thích từ vựng và ngữ pháp trong câu bằng tiếng Việt.
3) Nếu học viên có đưa bản dịch tiếng Việt của mình: chấm đúng/sai và chỉ rõ lỗi.

YÊU CẦU TRẢ LỜI: chỉ trả về JSON thuần (KHÔNG dùng markdown code fence,
không viết chữ giải thích ngoài JSON), đúng schema sau:
{
  "correct": true/false/null,
  "original": "<câu tiếng Trung gốc, giữ nguyên>",
  "pinyin": "<pinyin của câu gốc, có dấu thanh>",
  "translation": "<bản dịch tiếng Việt tự nhiên, có dấu>",
  "errors": [
    {"type": "<loại lỗi: dịch sai nghĩa/thiếu ý/thừa ý/văn phong>",
     "detail_vi": "<mô tả lỗi bằng tiếng Việt>",
     "fix_vi": "<cách sửa bằng tiếng Việt>"}
  ],
  "explanation_vi": "<giải thích từ mới, cấu trúc ngữ pháp bằng tiếng Việt>",
  "alternatives": ["<cách dịch khác tự nhiên nếu có>"]
}

Quy tắc bắt buộc:
- "translation" phải là tiếng Việt tự nhiên, có dấu, đúng văn phong người Việt.
- Nếu KHÔNG có bản dịch của học viên: "correct": null, "errors": [],
  chỉ dịch và giải thích từ vựng/ngữ pháp.
- Nếu CÓ bản dịch của học viên: chấm "correct" true/false; khi sai, mỗi lỗi
  giải thích theo 3 bước: SAI Ở ĐÂU -> VÌ SAO SAI -> SỬA THẾ NÀO.
- "explanation_vi" luôn bằng tiếng Việt, dễ hiểu với người mới học.
- Pinyin phải có dấu thanh (ví dụ: xuéxí hànyǔ)."""


def _user_prompt(cau_trung: str, cau_vi_cua_ban: str | None) -> str:
    prompt = "Câu tiếng Trung cần dịch:\n" + cau_trung.strip()
    if cau_vi_cua_ban and cau_vi_cua_ban.strip():
        prompt += (
            "\n\nBản dịch tiếng Việt của học viên:\n" + cau_vi_cua_ban.strip()
            + "\n\nHãy dịch, giải thích và chấm bản dịch của học viên "
              "theo đúng schema JSON ở trên."
        )
    else:
        prompt += (
            "\n\n(Học viên không đưa bản dịch — chỉ cần dịch sang tiếng Việt "
            "và giải thích từ vựng/ngữ pháp theo schema JSON ở trên.)"
        )
    return prompt


def _normalize(raw: dict, cau_trung: str) -> dict:
    """Chuẩn hoá kết quả AI về đúng schema."""
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
        "correct": correct,  # None khi học viên không nộp bản dịch
        "original": _as_str(raw.get("original"), cau_trung.strip()),
        "pinyin": _as_str(raw.get("pinyin")),
        "translation": _as_str(raw.get("translation")),
        "errors": _as_list(raw.get("errors")),
        "explanation_vi": _as_str(raw.get("explanation_vi")),
        "alternatives": _as_list(raw.get("alternatives")),
    }


def analyze_trung_viet(cau_trung: str, cau_vi_cua_ban: str | None = None) -> dict:
    """Dịch câu tiếng Trung sang tiếng Việt; chấm bản dịch nếu học viên có nộp.

    Raise QwenError (message tiếng Việt) khi thiếu input hoặc AI lỗi.
    """
    if not cau_trung or not cau_trung.strip():
        raise QwenError("Vui lòng nhập câu tiếng Trung cần dịch.")
    log.info(
        "Bài Trung-Việt (có bản dịch của HV: %s)",
        bool(cau_vi_cua_ban and cau_vi_cua_ban.strip()),
    )
    client = get_qwen_client()
    raw = client.chat_json(_SYSTEM_TV, _user_prompt(cau_trung, cau_vi_cua_ban))
    return _normalize(raw, cau_trung)
