"""Bảng ``app_settings``: key-value cho cài đặt lưu trong DB."""
from __future__ import annotations

import sqlite3


def init_db(conn: sqlite3.Connection) -> None:
    """Tạo bảng ``app_settings`` nếu chưa có (startup tự gọi)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS app_settings ("
        "key TEXT PRIMARY KEY, "
        "value TEXT, "
        "updated_at TEXT"
        ")"
    )
