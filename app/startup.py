"""Trình tự khởi động ứng dụng — gọi một lần khi app start.

Các bước:
  1. Tải cấu hình (``.env`` + biến môi trường)
  2. Tạo thư mục dữ liệu
  3. Áp dụng mức log từ cấu hình
  4. Khởi tạo / nâng cấp DB: bảng lõi + ``init_db(conn)`` của mọi module
     (tự phát hiện mọi ``app/<module>/tables.py``)
  5. Kiểm tra dependency lõi (ghi log, KHÔNG crash nếu thiếu thứ optional)
  6. Log "Khởi động hoàn tất"

Mọi bước đều bọc ``try/except`` với log rõ ràng. Lỗi DB là **fatal**.
"""
from __future__ import annotations

import importlib
import pkgutil
import shutil
import sys
import traceback
from collections.abc import Callable

import app as _app_pkg
from app import paths as _paths
from app.config import reload_settings
from app.db.database import get_conn, init_core_db
from app.logging_config import get_logger, set_level

log = get_logger(__name__)


def _discover_table_inits() -> list[tuple[str, Callable]]:
    """Tìm mọi ``app/<module>/tables.py`` có hàm ``init_db(conn)``."""
    found: list[tuple[str, Callable]] = []
    for _finder, name, is_pkg in pkgutil.iter_modules(_app_pkg.__path__):
        if not is_pkg:
            continue
        module_name = f"app.{name}.tables"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue  # module không có tables.py: bỏ qua
        except Exception:
            log.warning(
                "Bỏ qua tables của module '%s': không import được, app vẫn chạy.\n%s",
                name,
                traceback.format_exc(limit=3),
            )
            continue
        init_fn = getattr(module, "init_db", None)
        if callable(init_fn):
            found.append((module_name, init_fn))
    return found


def _step_config() -> None:
    """(1) Tải cấu hình."""
    try:
        settings = reload_settings()
        log.info(
            "Đã tải cấu hình: host=%s port=%s qwen_model=%s log_level=%s",
            settings.host,
            settings.port,
            settings.qwen_model,
            settings.log_level,
        )
    except Exception:
        log.error(
            "Lỗi khi tải cấu hình, dùng giá trị mặc định.\n%s",
            traceback.format_exc(limit=3),
        )


def _step_dirs() -> None:
    """(2) Tạo thư mục dữ liệu."""
    try:
        _paths.ensure_dirs()
        log.info("Đã kiểm tra thư mục dữ liệu: %s", _paths.DATA_DIR)
    except Exception:
        log.error(
            "KHÔNG tạo được thư mục dữ liệu.\n%s", traceback.format_exc(limit=3)
        )
        raise


def _step_logging() -> None:
    """(3) Áp dụng mức log từ cấu hình."""
    try:
        from app import config as _config

        set_level(_config.settings.log_level)
        log.info("Mức log: %s", _config.settings.log_level)
    except Exception:
        log.error("Lỗi khi áp dụng mức log.\n%s", traceback.format_exc(limit=3))


def _step_database() -> None:
    """(4) Khởi tạo / nâng cấp DB. Lỗi ở bước này là FATAL."""
    try:
        with get_conn() as conn:
            init_core_db(conn)
            for module_name, init_fn in _discover_table_inits():
                try:
                    init_fn(conn)
                    log.info("Đã khởi tạo DB cho %s.", module_name)
                except Exception:
                    log.error(
                        "Lỗi khởi tạo DB của %s.\n%s",
                        module_name,
                        traceback.format_exc(limit=5),
                    )
                    raise
        log.info("Khởi tạo cơ sở dữ liệu hoàn tất.")
    except Exception:
        log.error(
            "LỖI NGHIÊM TRỌNG: không khởi tạo được cơ sở dữ liệu, dừng khởi động.\n%s",
            traceback.format_exc(limit=5),
        )
        raise


def _step_verify_core() -> None:
    """(5) Kiểm tra dependency lõi. Chỉ ghi log, không crash nếu thiếu optional."""
    try:
        py_version = sys.version.split()[0]
        if sys.version_info < (3, 10):
            log.warning(
                "Python %s: khuyến nghị dùng Python 3.10 trở lên.", py_version
            )
        else:
            log.info("Python %s: đạt yêu cầu.", py_version)
        import sqlite3  # noqa: F401  (stdlib, luôn có)

        log.info("sqlite3 (stdlib): khả dụng.")
    except Exception:
        log.error("Thiếu dependency lõi.\n%s", traceback.format_exc(limit=3))
    try:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            log.info("ffmpeg: khả dụng (%s).", ffmpeg)
        else:
            log.warning(
                "ffmpeg: không tìm thấy trong PATH "
                "(tính năng xử lý video sẽ bị hạn chế)."
            )
    except Exception:
        log.warning("Không kiểm tra được ffmpeg.")


def run_startup() -> None:
    """Chạy toàn bộ trình tự khởi động. Lỗi DB là fatal (raise)."""
    log.info("Bắt đầu khởi động Hán Ngữ Server...")
    _step_config()  # (1) tải cấu hình
    _step_dirs()  # (2) tạo thư mục dữ liệu
    _step_logging()  # (3) áp dụng mức log
    _step_database()  # (4) khởi tạo/nâng cấp DB (fatal nếu lỗi)
    _step_verify_core()  # (5) kiểm tra dependency lõi
    log.info("Khởi động hoàn tất.")  # (6)
