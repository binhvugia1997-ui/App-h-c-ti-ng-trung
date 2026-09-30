"""Bảng bài nghe-chép: nguồn câu và lịch sử các lần nộp bài."""

from app.db.database import ensure_column


def init_db(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dictation_attempts (
            id INTEGER PRIMARY KEY,
            cau_dung TEXT,
            cau_nguoi_dung TEXT,
            diff_json TEXT,
            so_lan_thu INTEGER DEFAULT 1,
            created_at TEXT
        )
        """
    )
    for cot, ddl in [
        ("cau_dung", "TEXT"),
        ("cau_nguoi_dung", "TEXT"),
        ("diff_json", "TEXT"),
        ("so_lan_thu", "INTEGER DEFAULT 1"),
        ("created_at", "TEXT"),
    ]:
        ensure_column(conn, "dictation_attempts", cot, ddl)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dictation_sources (
            id INTEGER PRIMARY KEY,
            cau_trung TEXT,
            pinyin TEXT,
            nghia_vi TEXT,
            audio_path TEXT
        )
        """
    )
    for cot, ddl in [
        ("cau_trung", "TEXT"),
        ("pinyin", "TEXT"),
        ("nghia_vi", "TEXT"),
        ("audio_path", "TEXT"),
    ]:
        ensure_column(conn, "dictation_sources", cot, ddl)
