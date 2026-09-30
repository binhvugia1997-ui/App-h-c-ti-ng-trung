"""Tầng truy cập cơ sở dữ liệu (stdlib ``sqlite3``, không ORM)."""
from app.db.database import ensure_column, get_conn, init_core_db

__all__ = ["get_conn", "ensure_column", "init_core_db"]
