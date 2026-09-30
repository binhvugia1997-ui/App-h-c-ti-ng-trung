"""Đọc cấu hình từ file ``.env`` ở APP_ROOT + biến môi trường.

Thứ tự ưu tiên: biến môi trường > file ``.env`` > giá trị mặc định.
Dùng ``python-dotenv`` nếu có, ngược lại dùng parser thuần stdlib.

Sử dụng::

    from app.config import settings
    print(settings.port)

Gọi :func:`reload_settings` sau khi file ``.env`` thay đổi để tải lại.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.paths import APP_ROOT, BACKUP_DIR, DATA_DIR, MEDIA_DIR, RECORDINGS_DIR

DOTENV_PATH = APP_ROOT / ".env"

_VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def _parse_dotenv_text(text: str) -> dict[str, str]:
    """Parser .env tối giản thuần stdlib (fallback khi thiếu python-dotenv)."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _read_dotenv_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        from dotenv import dotenv_values

        raw = dotenv_values(path)
        return {str(k): str(v) for k, v in raw.items() if v is not None}
    except ImportError:
        pass
    except Exception:
        pass
    try:
        return _parse_dotenv_text(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _detect_ffmpeg() -> str:
    """Tự tìm ffmpeg trong PATH; trả về chuỗi rỗng nếu không thấy."""
    return shutil.which("ffmpeg") or ""


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    db_path: Path | None = None
    ffmpeg_path: str = ""
    qwen_base_url: str = "http://127.0.0.1:11434"
    qwen_model: str = "qwen2.5:7b"
    log_level: str = "INFO"
    media_dir: Path | None = None
    recordings_dir: Path | None = None
    backup_dir: Path | None = None

    @classmethod
    def load(cls) -> "Settings":
        file_values = _read_dotenv_file(DOTENV_PATH)

        def get(name: str, default: str = "") -> str:
            if name in os.environ:
                return os.environ[name]
            return file_values.get(name, default)

        def get_path(name: str, default: Path) -> Path:
            raw = get(name, "").strip()
            return Path(raw).expanduser() if raw else default

        try:
            port = int(get("HANNGU_PORT", "8000"))
        except (TypeError, ValueError):
            port = 8000
        if not 1 <= port <= 65535:
            port = 8000

        log_level = get("HANNGU_LOG_LEVEL", "INFO").strip().upper() or "INFO"
        if log_level not in _VALID_LOG_LEVELS:
            log_level = "INFO"

        return cls(
            host=get("HANNGU_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=port,
            db_path=get_path("HANNGU_DB_PATH", DATA_DIR / "hanngu.db"),
            ffmpeg_path=get("HANNGU_FFMPEG_PATH", "").strip() or _detect_ffmpeg(),
            qwen_base_url=(
                get("QWEN_BASE_URL", "http://127.0.0.1:11434").strip()
                or "http://127.0.0.1:11434"
            ),
            qwen_model=get("QWEN_MODEL", "qwen2.5:7b").strip() or "qwen2.5:7b",
            log_level=log_level,
            media_dir=get_path("HANNGU_MEDIA_DIR", MEDIA_DIR),
            recordings_dir=get_path("HANNGU_RECORDINGS_DIR", RECORDINGS_DIR),
            backup_dir=get_path("HANNGU_BACKUP_DIR", BACKUP_DIR),
        )

    def public_dict(self) -> dict:
        """Các setting AN TOÀN, dùng cho API (không bao giờ chứa secret)."""
        return {
            "host": self.host,
            "port": self.port,
            "db_path": str(self.db_path),
            "ffmpeg_path": self.ffmpeg_path,
            "qwen_base_url": self.qwen_base_url,
            "qwen_model": self.qwen_model,
            "log_level": self.log_level,
            "media_dir": str(self.media_dir),
            "recordings_dir": str(self.recordings_dir),
            "backup_dir": str(self.backup_dir),
        }


settings = Settings.load()


def reload_settings() -> Settings:
    """Tải lại cấu hình từ .env + biến môi trường."""
    global settings
    settings = Settings.load()
    return settings


_ATTR_TO_ENV = {
    "host": "HANNGU_HOST",
    "port": "HANNGU_PORT",
    "db_path": "HANNGU_DB_PATH",
    "ffmpeg_path": "HANNGU_FFMPEG_PATH",
    "qwen_base_url": "QWEN_BASE_URL",
    "qwen_model": "QWEN_MODEL",
    "log_level": "HANNGU_LOG_LEVEL",
    "media_dir": "HANNGU_MEDIA_DIR",
    "recordings_dir": "HANNGU_RECORDINGS_DIR",
    "backup_dir": "HANNGU_BACKUP_DIR",
}


def save_settings(updates: dict[str, str]) -> None:
    """Ghi các giá trị vào file ``.env`` ở APP_ROOT, giữ nguyên các dòng khác."""
    env_updates = {
        _ATTR_TO_ENV[key]: str(value)
        for key, value in updates.items()
        if key in _ATTR_TO_ENV
    }
    lines: list[str] = []
    if DOTENV_PATH.is_file():
        lines = DOTENV_PATH.read_text(encoding="utf-8").splitlines()
    remaining = dict(env_updates)
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        key: str | None = None
        if stripped and not stripped.startswith("#") and "=" in stripped:
            candidate = stripped.partition("=")[0].strip()
            if candidate.startswith("export "):
                candidate = candidate[len("export "):].strip()
            key = candidate
        if key and key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(raw)
    for key, value in remaining.items():
        out.append(f"{key}={value}")
    DOTENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
