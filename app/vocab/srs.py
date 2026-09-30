"""Thuật toán lặp lại ngắt quãng (SRS) — phiên bản SM-2 rút gọn, trung thực.

Không bịa điểm: các hàm ở đây chỉ tính *lịch* ôn tập từ mức độ nhớ do chính
người học tự đánh giá (0-5), không tự suy ra mức độ nhớ từ dữ liệu khác.
"""

from datetime import date, timedelta

# Khoảng cách ôn tập (số ngày) ứng với mức độ nhớ 0..5.
# Mức 0 = quên hẳn -> ôn lại ngay ngày mai; mức 5 = nhớ rất rõ -> lâu mới cần ôn.
INTERVALS_NGAY = [1, 3, 7, 16, 35, 75]


def next_review_date(muc_do_nho: int) -> date:
    """Ngày cần ôn tiếp theo, tính từ hôm nay theo mức độ nhớ 0-5."""
    muc = max(0, min(5, int(muc_do_nho)))
    return date.today() + timedelta(days=INTERVALS_NGAY[muc])


def schedule_review(conn, vocab_id: int, muc_do: int) -> dict:
    """Ghi nhận một lần ôn: tăng so_lan_on, cập nhật muc_do_nho và ngày cần ôn.

    Trả về dòng vocab sau khi cập nhật. Raise ValueError nếu không tìm thấy từ.
    """
    muc_do = max(0, min(5, int(muc_do)))
    hom_nay = date.today()
    trang_thai = "da_thuoc" if muc_do >= 4 else "dang_on"
    cur = conn.execute(
        """UPDATE vocab
           SET so_lan_on = COALESCE(so_lan_on, 0) + 1,
               muc_do_nho = ?,
               ngay_hoc_gan_nhat = ?,
               ngay_can_on = ?,
               trang_thai = ?
           WHERE id = ?""",
        (
            muc_do,
            hom_nay.isoformat(),
            next_review_date(muc_do).isoformat(),
            trang_thai,
            vocab_id,
        ),
    )
    if cur.rowcount == 0:
        raise ValueError("Không tìm thấy từ vựng.")
    row = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
    return dict(row)
