"""Thống kê học tập cho dashboard.

Mọi số liệu đều được đếm thật từ database (study_events + các bảng module khác).
Không bịa số: bảng nào chưa được khởi tạo thì chỉ số tương ứng = 0 / danh sách rỗng.
"""

from datetime import date, timedelta


def _co_bang(conn, ten_bang: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (ten_bang,)
    ).fetchone()
    return row is not None


def _tinh_chuoi_ngay_hoc(conn) -> int:
    """Số ngày học liên tiếp (streak), tính đến hôm nay (hoặc hôm qua nếu hôm nay chưa học)."""
    rows = conn.execute(
        "SELECT DISTINCT ngay FROM study_events WHERE ngay IS NOT NULL AND ngay != ''"
        " ORDER BY ngay DESC"
    ).fetchall()
    ngay_list = [r[0] for r in rows]
    if not ngay_list:
        return 0
    hom_nay = date.today()
    hom_qua = (hom_nay - timedelta(days=1)).isoformat()
    if ngay_list[0] == hom_nay.isoformat():
        cursor = hom_nay
    elif ngay_list[0] == hom_qua:
        cursor = hom_nay - timedelta(days=1)
    else:
        return 0
    chuoi = 0
    for n in ngay_list:
        if n == cursor.isoformat():
            chuoi += 1
            cursor -= timedelta(days=1)
        else:
            break
    return chuoi


def get_summary(conn) -> dict:
    """Tổng hợp tình hình học tập. Persistent: đọc trực tiếp từ DB mỗi lần gọi."""
    hom_nay = date.today().isoformat()

    bai_hoc_hom_nay = 0
    so_phut_hom_nay = 0
    chuoi_ngay_hoc = 0
    lich_su_gan_day = []
    if _co_bang(conn, "study_events"):
        r = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(so_phut), 0) FROM study_events WHERE ngay = ?",
            (hom_nay,),
        ).fetchone()
        bai_hoc_hom_nay = int(r[0] or 0)
        so_phut_hom_nay = int(r[1] or 0)
        chuoi_ngay_hoc = _tinh_chuoi_ngay_hoc(conn)
        lich_su_gan_day = [
            dict(x)
            for x in conn.execute(
                "SELECT id, ngay, so_phut, hoat_dong, chi_tiet, created_at"
                " FROM study_events ORDER BY id DESC LIMIT 10"
            ).fetchall()
        ]

    tong_tu_vung = 0
    tu_can_on = 0
    if _co_bang(conn, "vocab"):
        tong_tu_vung = conn.execute("SELECT COUNT(*) FROM vocab").fetchone()[0] or 0
        tu_can_on = (
            conn.execute(
                "SELECT COUNT(*) FROM vocab WHERE ngay_can_on IS NOT NULL AND ngay_can_on <= ?",
                (hom_nay,),
            ).fetchone()[0]
            or 0
        )

    so_buoi_shadowing = 0
    if _co_bang(conn, "shadowing_sessions"):
        so_buoi_shadowing = conn.execute("SELECT COUNT(*) FROM shadowing_sessions").fetchone()[0] or 0

    so_bai_nghe_chep = 0
    if _co_bang(conn, "dictation_attempts"):
        so_bai_nghe_chep = conn.execute("SELECT COUNT(*) FROM dictation_attempts").fetchone()[0] or 0

    return {
        "bai_hoc_hom_nay": bai_hoc_hom_nay,
        "so_phut_hom_nay": so_phut_hom_nay,
        "chuoi_ngay_hoc": chuoi_ngay_hoc,
        "tong_tu_vung": tong_tu_vung,
        "tu_can_on": tu_can_on,
        "so_buoi_shadowing": so_buoi_shadowing,
        "so_bai_nghe_chep": so_bai_nghe_chep,
        "lich_su_gan_day": lich_su_gan_day,
    }
