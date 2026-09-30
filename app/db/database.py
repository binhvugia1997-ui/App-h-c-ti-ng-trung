"""Tầng DB dùng stdlib ``sqlite3``: kết nối, migration cột, bảng lõi.

Sử dụng::

    from app.db.database import get_conn, ensure_column, init_core_db

    with get_conn() as conn:          # tự commit khi xong, rollback khi lỗi
        conn.execute("INSERT INTO ...")
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app import config as _config
from app.logging_config import get_logger

log = get_logger(__name__)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_identifier(value: str, kind: str) -> None:
    if not value or not _IDENTIFIER_RE.match(value):
        raise ValueError(f"Tên {kind} không hợp lệ: {value!r}")


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Mở kết nối SQLite.

    - ``row_factory = sqlite3.Row`` (truy cập cột theo tên)
    - ``check_same_thread = False`` (dùng được với FastAPI/uvicorn)
    - bật ``PRAGMA foreign_keys = ON``
    - tự ``commit`` khi khối ``with`` chạy xong, ``rollback`` khi có lỗi
    """
    db_path = Path(str(_config.settings.db_path))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """Thêm cột vào bảng nếu chưa có (kiểm tra qua ``PRAGMA table_info``).

    ``column`` là tên cột, ``ddl`` là định nghĩa cột KHÔNG kèm tên
    (ví dụ ``"TEXT"``, ``"INTEGER NOT NULL DEFAULT 0"``).
    Hàm là idempotent: gọi lại khi cột đã tồn tại thì không làm gì.
    """
    _check_identifier(table, "bảng")
    _check_identifier(column, "cột")
    if not ddl or not ddl.strip():
        raise ValueError("ddl định nghĩa cột không được để trống.")
    existing = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        log.info("Đã thêm cột '%s' vào bảng '%s'.", column, table)


def init_core_db(conn: sqlite3.Connection) -> None:
    """Tạo các bảng lõi: ``schema_version`` và ``kv_store``."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "version INTEGER NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS kv_store ("
        "key TEXT PRIMARY KEY, "
        "value TEXT"
        ")"
    )
    row = conn.execute("SELECT COUNT(*) AS n FROM schema_version").fetchone()
    if row is not None and row["n"] == 0:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
    log.info("Đã khởi tạo bảng lõi (schema_version, kv_store).")
