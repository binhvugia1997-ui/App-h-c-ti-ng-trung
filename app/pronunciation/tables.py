"""Bảng kết quả phát âm và bảng hiệu chuẩn (calibration)."""

from app.db.database import ensure_column


def init_db(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pronunciation_results (
            id INTEGER PRIMARY KEY,
            target_sentence TEXT,
            recording_path TEXT,
            pronunciation REAL NULL,
            rhythm REAL NULL,
            fluency REAL NULL,
            similarity REAL NULL,
            nhan_xet_vi TEXT,
            created_at TEXT
        )
        """
    )
    for cot, ddl in [
        ("target_sentence", "TEXT"),
        ("recording_path", "TEXT"),
        ("pronunciation", "REAL NULL"),
        ("rhythm", "REAL NULL"),
        ("fluency", "REAL NULL"),
        ("similarity", "REAL NULL"),
        ("nhan_xet_vi", "TEXT"),
        ("created_at", "TEXT"),
    ]:
        ensure_column(conn, "pronunciation_results", cot, ddl)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calibration (
            id INTEGER PRIMARY KEY,
            khoa TEXT UNIQUE,
            gia_tri_json TEXT,
            updated_at TEXT
        )
        """
    )
    for cot, ddl in [
        ("khoa", "TEXT UNIQUE"),
        ("gia_tri_json", "TEXT"),
        ("updated_at", "TEXT"),
    ]:
        ensure_column(conn, "calibration", cot, ddl)
