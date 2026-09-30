"""QwenClient — client DUY NHẤT trong app giao tiếp với Qwen qua Ollama.

Qwen chạy trên MÁY B (không giả định cùng máy với server), giao tiếp qua HTTP
tới ``settings.qwen_base_url`` (mặc định http://127.0.0.1:11434).

Mọi module khác muốn dùng AI đều phải đi qua ``get_qwen_client()``.
Khi Qwen offline: KHÔNG crash, luôn raise ``QwenError`` với message tiếng Việt
thân thiện để tầng router trả về cho người dùng.
"""

from __future__ import annotations

import json
import re
import time

import httpx

from app.config import settings
from app.logging_config import get_logger

log = get_logger(__name__)

CONN_ERR_VI = "Máy AI hiện không kết nối được. Vui lòng kiểm tra máy Qwen."
FORMAT_ERR_VI = "AI trả về dữ liệu không đúng định dạng, vui lòng thử lại."

# Qwen là service LAN/local: luôn kết nối trực tiếp, KHÔNG đi qua proxy hệ thống
# (trust_env=False để bỏ qua HTTP(S)_PROXY — proxy sai/bẩn không được làm hỏng
# kết nối tới máy Qwen và cũng không rò rỉ request nội bộ ra proxy ngoài).
_http = httpx.Client(trust_env=False)


class QwenError(Exception):
    """Lỗi AI với message tiếng Việt thân thiện, an toàn hiển thị cho user."""


class _Retryable(Exception):
    """Lỗi nội bộ: có thể thử lại (mất mạng/timeout/HTTP 5xx)."""


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _extract_json(text: str):
    """Trích JSON từ text AI trả về.

    Chịu được: markdown code fence (```json ... ```), text lẫn lộn trước/sau
    JSON, trailing comma. Raise ValueError nếu không trích được.
    """
    if not text or not text.strip():
        raise ValueError("empty response")
    candidate = text.strip().lstrip("\ufeff")
    m = _FENCE_RE.search(candidate)
    if m:
        candidate = m.group(1).strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found")
    candidate = candidate[start : end + 1]
    candidate = _TRAILING_COMMA_RE.sub(r"\1", candidate)  # repair nhẹ
    return json.loads(candidate)


class QwenClient:
    """Client gọi Ollama /api/chat. Đọc base_url/model từ settings mỗi lần dùng."""

    def __init__(self) -> None:
        self.refresh_settings()

    def refresh_settings(self) -> None:
        """Nạp lại base_url/model từ settings (cho phép đổi .env lúc chạy)."""
        self.base_url = str(getattr(settings, "qwen_base_url", "") or "").rstrip("/")
        self.model = str(getattr(settings, "qwen_model", "") or "")

    # ------------------------------------------------------------------ check
    def check(self, timeout: float = 5) -> dict:
        """Kiểm tra kết nối tới Ollama qua GET {base}/api/tags.

        Không bao giờ raise: luôn trả dict
        {"ok": bool, "message_vi": str, "model": str|None, "latency_ms": int|None}.
        """
        url = f"{self.base_url}/api/tags"
        start = time.perf_counter()
        try:
            resp = _http.get(url, timeout=httpx.Timeout(timeout, connect=timeout))
        except Exception as exc:  # offline / DNS / refused / timeout
            log.warning("Qwen check thất bại (%s): %s", url, exc)
            return {
                "ok": False,
                "message_vi": "Không kết nối được tới máy AI. "
                "Vui lòng kiểm tra máy Qwen đang bật và địa chỉ QWEN_BASE_URL.",
                "model": None,
                "latency_ms": None,
            }
        latency_ms = int((time.perf_counter() - start) * 1000)
        if resp.status_code != 200:
            log.warning("Qwen check trả mã HTTP %s", resp.status_code)
            return {
                "ok": False,
                "message_vi": f"Máy AI phản hồi không thành công (mã {resp.status_code}). "
                "Vui lòng kiểm tra máy Qwen.",
                "model": None,
                "latency_ms": None,
            }
        return {
            "ok": True,
            "message_vi": "Kết nối tới máy AI thành công.",
            "model": self.model or None,
            "latency_ms": latency_ms,
        }

    # ------------------------------------------------------------------- chat
    def _chat_once(self, system: str, user: str, timeout: float) -> str:
        """Một lần gọi POST {base}/api/chat (Ollama format, stream=false)."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = _http.post(
                url, json=payload, timeout=httpx.Timeout(timeout, connect=10.0)
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise _Retryable(f"kết nối: {exc}") from exc
        except httpx.RequestError as exc:
            # Lỗi request khác (URL sai, SSL...): không retry, báo thân thiện
            log.warning("Qwen request lỗi: %s", exc)
            raise QwenError(CONN_ERR_VI) from exc

        if resp.status_code >= 500:
            raise _Retryable(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            log.warning("Qwen chat trả mã HTTP %s", resp.status_code)
            raise QwenError(CONN_ERR_VI)

        try:
            data = resp.json()
        except ValueError as exc:
            log.warning("Qwen trả body không phải JSON")
            raise QwenError(FORMAT_ERR_VI) from exc

        content = (data.get("message") or {}).get("content")
        if not content or not str(content).strip():
            log.warning("Qwen trả JSON thiếu message.content")
            raise QwenError(FORMAT_ERR_VI)
        return str(content)

    def chat(self, system: str, user: str, timeout: float = 60) -> str:
        """Gọi Qwen, trả về text. Retry tối đa 2 lần với backoff đơn giản.

        Lỗi mạng/timeout/5xx sau 3 lần thử -> raise QwenError(CONN_ERR_VI).
        Response sai định dạng -> raise QwenError(FORMAT_ERR_VI).
        """
        last: Exception | None = None
        for attempt in range(3):  # 1 lần chính + tối đa 2 lần retry
            try:
                return self._chat_once(system, user, timeout)
            except _Retryable as exc:
                last = exc
                log.warning(
                    "Qwen chat thử lần %d thất bại (%s), sẽ thử lại",
                    attempt + 1,
                    exc,
                )
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))  # backoff đơn giản: 1s, 2s
            except QwenError:
                raise  # lỗi đã thân thiện / không retry: ném ngay
        log.error("Qwen chat thất bại sau 3 lần thử: %s", last)
        raise QwenError(CONN_ERR_VI) from last

    # Alias theo hợp đồng PLAN mục 3.7
    def chat_text(self, system: str, user: str, timeout: float = 60) -> str:
        return self.chat(system, user, timeout=timeout)

    # -------------------------------------------------------------- chat_json
    def chat_json(self, system: str, user: str, timeout: float = 60) -> dict:
        """Gọi chat() rồi trích JSON từ text trả về.

        - Mất kết nối -> raise QwenError(CONN_ERR_VI) (từ chat()).
        - Parse thất bại / không phải dict -> raise QwenError(FORMAT_ERR_VI).
        """
        raw = self.chat(system, user, timeout=timeout)
        try:
            data = _extract_json(raw)
        except ValueError as exc:
            log.warning("Không trích được JSON từ câu trả lời của Qwen")
            raise QwenError(FORMAT_ERR_VI) from exc
        if not isinstance(data, dict):
            log.warning("Qwen trả JSON không phải object")
            raise QwenError(FORMAT_ERR_VI)
        return data


_instance: QwenClient | None = None


def get_qwen_client() -> QwenClient:
    """Trả về singleton QwenClient.

    Đọc lại settings.qwen_base_url / settings.qwen_model MỖI LẦN gọi để luôn
    dùng cấu hình mới nhất (đổi .env không cần restart để có hiệu lực ở client).
    """
    global _instance
    if _instance is None:
        _instance = QwenClient()
    else:
        _instance.refresh_settings()
    return _instance
