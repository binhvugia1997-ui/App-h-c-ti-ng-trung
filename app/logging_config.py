"""Logging tập trung: console + file xoay vòng, tự động che secret/token.

Sử dụng::

    from app.logging_config import get_logger
    log = get_logger(__name__)

CẤM log secret/token — bộ lọc :class:`_RedactFilter` sẽ che các giá trị
nhạy cảm (``password=...``, ``api_key: ...``...) trước khi ghi.
"""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from app.paths import LOGS_DIR

_LOG_FILE = LOGS_DIR / "hanngu.log"
_MAX_BYTES = 1_048_576  # 1 MB
_BACKUP_COUNT = 5  # giữ tối đa 5 file xoay vòng

_SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "pwd",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
    "authorization",
    "auth_token",
    "session_id",
)

# Bắt các dạng: key=giá_trị | key: giá_trị | "key": "giá_trị"
_REDACT_RE = re.compile(
    r"(?i)(\b(?:token|secret|passw(?:or)?d|pwd|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|credentials?|authorization|auth[_-]?token|session[_-]?id)\b"
    r"\s*[:=]\s*)([\"']?)([^\"',\s;}]+)\2"
)


def _redact(text: str) -> str:
    """Che giá trị nhạy cảm trong một chuỗi log."""
    return _REDACT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***{m.group(2)}", text)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


class _RedactFilter(logging.Filter):
    """Che secret/token trong mọi bản ghi log trước khi ghi ra."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = _redact(record.msg)
            elif record.msg is not None:
                record.msg = _redact(str(record.msg))
            if isinstance(record.args, dict):
                record.args = {
                    k: ("***" if _is_sensitive_key(str(k)) else v)
                    for k, v in record.args.items()
                }
            elif record.args:
                record.args = tuple(
                    _redact(a) if isinstance(a, str) else a for a in record.args
                )
        except Exception:
            pass
        return True


_configured = False


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return
    _configured = True
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    )
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(_RedactFilter())
    root.addHandler(console)
    try:
        file_handler = RotatingFileHandler(
            str(_LOG_FILE),
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(_RedactFilter())
        root.addHandler(file_handler)
    except Exception:
        # Không ghi được file log thì vẫn chạy bằng console.
        pass


def get_logger(name: str) -> logging.Logger:
    """Lấy logger đã cấu hình (console + file xoay vòng, che secret)."""
    _ensure_configured()
    return logging.getLogger(name)


def set_level(level_name: str) -> None:
    """Đặt mức log lúc chạy (ví dụ sau khi đổi settings)."""
    _ensure_configured()
    level = getattr(logging, str(level_name).upper(), None)
    if isinstance(level, int):
        logging.getLogger().setLevel(level)
