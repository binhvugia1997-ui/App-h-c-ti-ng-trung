"""Source of truth cho mọi đường dẫn trong ứng dụng.

Mọi module PHẢI import path từ đây, CẤM hard-code absolute path
(``D:\\...``, ``C:\\...``...). Thư mục dữ liệu có thể ghi đè bằng biến
môi trường ``HANNGU_DATA_DIR``.
"""
from __future__ import annotations

import os
from pathlib import Path

# Thư mục gốc của repo (thư mục chứa package ``app/``).
APP_ROOT = Path(__file__).resolve().parent.parent


def _resolve_data_dir() -> Path:
    override = os.environ.get("HANNGU_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return APP_ROOT / "data"


# Thư mục dữ liệu (ghi đè được qua HANNGU_DATA_DIR).
DATA_DIR = _resolve_data_dir()

# Mọi thư mục bên dưới đều nằm trong DATA_DIR.
MEDIA_DIR = DATA_DIR / "media"
RECORDINGS_DIR = DATA_DIR / "recordings"
RECOVERY_DIR = DATA_DIR / "recovery"
TRASH_DIR = DATA_DIR / "trash"
CONFIG_DIR = DATA_DIR / "config"
BACKUP_DIR = DATA_DIR / "backups"
MODEL_DIR = DATA_DIR / "models"
LOGS_DIR = DATA_DIR / "logs"

ALL_DIRS: tuple[Path, ...] = (
    DATA_DIR,
    MEDIA_DIR,
    RECORDINGS_DIR,
    RECOVERY_DIR,
    TRASH_DIR,
    CONFIG_DIR,
    BACKUP_DIR,
    MODEL_DIR,
    LOGS_DIR,
)


def ensure_dirs() -> None:
    """Tạo mọi thư mục dữ liệu nếu thiếu. Không xóa dữ liệu đã có."""
    for directory in ALL_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
