"""Bảng từ vựng + lịch ôn tập SRS."""

from app.db.database import ensure_column


def init_db(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vocab (
            id INTEGER PRIMARY KEY,
            hanzi TEXT NOT NULL,
            pinyin TEXT,
            nghia_vi TEXT,
            loai_tu TEXT,
            vi_du_trung TEXT,
            pinyin_vidu TEXT,
            dich_vi TEXT,
            audio_path TEXT,
            trang_thai TEXT DEFAULT 'moi',
            so_lan_on INTEGER DEFAULT 0,
            muc_do_nho INTEGER DEFAULT 0,
            ngay_hoc_gan_nhat TEXT,
            ngay_can_on TEXT,
            created_at TEXT
        )
        """
    )
    for cot, ddl in [
        ("hanzi", "TEXT NOT NULL"),
        ("pinyin", "TEXT"),
        ("nghia_vi", "TEXT"),
        ("loai_tu", "TEXT"),
        ("vi_du_trung", "TEXT"),
        ("pinyin_vidu", "TEXT"),
        ("dich_vi", "TEXT"),
        ("audio_path", "TEXT"),
        ("trang_thai", "TEXT DEFAULT 'moi'"),
        ("so_lan_on", "INTEGER DEFAULT 0"),
        ("muc_do_nho", "INTEGER DEFAULT 0"),
        ("ngay_hoc_gan_nhat", "TEXT"),
        ("ngay_can_on", "TEXT"),
        ("created_at", "TEXT"),
    ]:
        ensure_column(conn, "vocab", cot, ddl)
