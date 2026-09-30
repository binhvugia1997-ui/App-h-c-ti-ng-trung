"""Bảng phiên luyện shadowing."""

from app.db.database import ensure_column


def init_db(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shadowing_sessions (
            id INTEGER PRIMARY KEY,
            cau_chuan TEXT,
            pinyin TEXT,
            nghia_vi TEXT,
            recording_path TEXT,
            created_at TEXT
        )
        """
    )
    for cot, ddl in [
        ("cau_chuan", "TEXT"),
        ("pinyin", "TEXT"),
        ("nghia_vi", "TEXT"),
        ("recording_path", "TEXT"),
        ("created_at", "TEXT"),
    ]:
        ensure_column(conn, "shadowing_sessions", cot, ddl)
