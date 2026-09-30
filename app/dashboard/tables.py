"""Bảng sự kiện học tập cho dashboard."""

from app.db.database import ensure_column


def init_db(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS study_events (
            id INTEGER PRIMARY KEY,
            ngay TEXT,
            so_phut INTEGER,
            hoat_dong TEXT,
            chi_tiet TEXT,
            created_at TEXT
        )
        """
    )
    for cot, ddl in [
        ("ngay", "TEXT"),
        ("so_phut", "INTEGER"),
        ("hoat_dong", "TEXT"),
        ("chi_tiet", "TEXT"),
        ("created_at", "TEXT"),
    ]:
        ensure_column(conn, "study_events", cot, ddl)
