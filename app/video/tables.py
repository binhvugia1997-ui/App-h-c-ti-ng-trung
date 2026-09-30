"""Tạo bảng dữ liệu cho module video.

Mọi bảng dùng ``CREATE TABLE IF NOT EXISTS`` và ``ensure_column`` để nâng
cấp an toàn khi schema thay đổi. ``startup.py`` tự gọi ``init_db`` của mọi
module nên không cần đăng ký thủ công.
"""

from app.db.database import ensure_column


def init_db(conn) -> None:
    """Tạo/nâng cấp các bảng video_jobs, video_lessons, video_segments."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_jobs (
            id TEXT PRIMARY KEY,
            video_id TEXT,
            status TEXT,
            stage TEXT,
            progress INTEGER,
            error_vi TEXT,
            checkpoint_json TEXT,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    for column, ddl in (
        ("video_id", "TEXT"),
        ("status", "TEXT"),
        ("stage", "TEXT"),
        ("progress", "INTEGER"),
        ("error_vi", "TEXT"),
        ("checkpoint_json", "TEXT"),
        ("created_at", "TEXT"),
        ("updated_at", "TEXT"),
    ):
        ensure_column(conn, "video_jobs", column, ddl)

    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_lessons (
            id TEXT PRIMARY KEY,
            job_id TEXT,
            title TEXT,
            video_path TEXT,
            created_at TEXT
        )"""
    )
    for column, ddl in (
        ("job_id", "TEXT"),
        ("title", "TEXT"),
        ("video_path", "TEXT"),
        ("created_at", "TEXT"),
    ):
        ensure_column(conn, "video_lessons", column, ddl)

    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_segments (
            id INTEGER PRIMARY KEY,
            lesson_id TEXT,
            idx INTEGER,
            start_time REAL,
            end_time REAL,
            chinese TEXT,
            pinyin TEXT,
            vietnamese TEXT
        )"""
    )
    for column, ddl in (
        ("lesson_id", "TEXT"),
        ("idx", "INTEGER"),
        ("start_time", "REAL"),
        ("end_time", "REAL"),
        ("chinese", "TEXT"),
        ("pinyin", "TEXT"),
        ("vietnamese", "TEXT"),
    ):
        ensure_column(conn, "video_segments", column, ddl)
