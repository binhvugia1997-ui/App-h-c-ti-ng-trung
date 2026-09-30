"""API cài đặt (``/api/settings``).

- ``GET /``: trả các setting AN TOÀN (không bao giờ trả secret).
- ``PUT /``: cập nhật ``{qwen_base_url, qwen_model, host, port, log_level}``
  (có validate), ghi vào file ``.env`` ở APP_ROOT (giữ nguyên các dòng
  khác), tải lại cấu hình và trả ``{"ok": true}``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from app import config as _config
from app.config import reload_settings, save_settings
from app.logging_config import get_logger, set_level

log = get_logger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

_VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class SettingsUpdate(BaseModel):
    qwen_base_url: Optional[str] = None
    qwen_model: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    log_level: Optional[str] = None

    @field_validator("qwen_base_url")
    @classmethod
    def _validate_base_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip().rstrip("/")
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("qwen_base_url phải bắt đầu bằng http:// hoặc https://")
        return value

    @field_validator("qwen_model", "host")
    @classmethod
    def _validate_non_empty(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Giá trị không được để trống.")
        return value

    @field_validator("port")
    @classmethod
    def _validate_port(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if not 1 <= value <= 65535:
            raise ValueError("port phải nằm trong khoảng 1-65535.")
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip().upper()
        if value not in _VALID_LOG_LEVELS:
            raise ValueError(
                "log_level phải là một trong: " + ", ".join(_VALID_LOG_LEVELS)
            )
        return value


@router.get("/")
def get_settings() -> dict:
    """Trả các setting an toàn (không bao giờ chứa secret)."""
    return {"ok": True, "data": _config.settings.public_dict()}


@router.put("/")
def update_settings(payload: SettingsUpdate) -> dict:
    """Validate, ghi vào ``.env``, tải lại cấu hình."""
    updates = {
        key: value for key, value in payload.model_dump().items() if value is not None
    }
    if not updates:
        return {"ok": False, "error_vi": "Không có cài đặt nào để cập nhật."}
    save_settings({key: str(value) for key, value in updates.items()})
    new_settings = reload_settings()
    set_level(new_settings.log_level)  # áp dụng mức log mới ngay
    log.info("Đã cập nhật cài đặt: %s", ", ".join(sorted(updates)))
    return {"ok": True, "data": new_settings.public_dict()}
