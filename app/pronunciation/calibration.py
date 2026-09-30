"""Hiệu chuẩn (calibration): lưu/đọc các tham số hiệu chuẩn dưới dạng JSON.

Dùng cho việc tinh chỉnh engine chấm phát âm trong tương lai (ngưỡng điểm,
trọng số...). Giá trị là JSON tùy ý nên linh hoạt mà không cần đổi schema.
"""

import json
from datetime import datetime
from typing import Any, Optional


def get_calibration(conn, khoa: str, default: Optional[Any] = None) -> Any:
    """Đọc giá trị hiệu chuẩn theo khóa. Trả về `default` nếu chưa có hoặc JSON hỏng."""
    row = conn.execute(
        "SELECT gia_tri_json FROM calibration WHERE khoa = ?", (khoa,)
    ).fetchone()
    if not row or row["gia_tri_json"] is None:
        return default
    try:
        return json.loads(row["gia_tri_json"])
    except (ValueError, TypeError):
        return default


def set_calibration(conn, khoa: str, gia_tri: Any) -> dict:
    """Ghi (upsert) giá trị hiệu chuẩn theo khóa."""
    payload = json.dumps(gia_tri, ensure_ascii=False)
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO calibration (khoa, gia_tri_json, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(khoa) DO UPDATE SET
             gia_tri_json = excluded.gia_tri_json,
             updated_at = excluded.updated_at""",
        (khoa, payload, now),
    )
    return {"khoa": khoa, "gia_tri": gia_tri, "updated_at": now}
