"""Bảng lịch sử bài tập AI (ai_exercises)."""

from app.db.database import ensure_column


def init_db(conn) -> None:
    """Tạo bảng ai_exercise_history (idempotent, có nâng cấp cột)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_exercise_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT NOT NULL DEFAULT '',
            input_text TEXT NOT NULL DEFAULT '',
            user_answer TEXT,
            result_json TEXT,
            created_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    # Nâng cấp cho DB cũ thiếu cột:
    ensure_column(conn, "ai_exercise_history", "direction", "TEXT")
    ensure_column(conn, "ai_exercise_history", "input_text", "TEXT")
    ensure_column(conn, "ai_exercise_history", "user_answer", "TEXT")
    ensure_column(conn, "ai_exercise_history", "result_json", "TEXT")
    ensure_column(conn, "ai_exercise_history", "created_at", "TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_exercise_history_created "
        "ON ai_exercise_history(created_at DESC)"
    )
