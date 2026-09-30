# AUDIT — Hán Ngữ Server

Ngày: 2026-09-30
Người thực hiện: coordinator subagent

## Hiện trạng repository

- Repo local: `~/workspace/hanngu-server/`
- Remote: `binhvugia1997-ui/App-h-c-ti-ng-trung`, branch `main`
- Nội dung hiện tại:
  - `README.md` — 1 dòng: `# App-h-c-ti-ng-trung`
  - `.git/` — đã init, chưa có commit nào ngoài file trên (cần kiểm chứng bởi agent cha)
- **Kết luận: repo trống hoàn toàn, chưa có source code nào.**

## Các điểm kiểm tra theo MASTER PROMPT

| Hạng mục | Trạng thái |
|---|---|
| backend | CHƯA CÓ |
| frontend | CHƯA CÓ |
| database | CHƯA CÓ |
| media / recordings | CHƯA CÓ |
| video processing (`process_video.py`) | CHƯA CÓ — theo nguyên tắc, KHÔNG được tạo/sửa file này; các module khác phải degrade gracefully khi file vắng mặt |
| pronunciation | CHƯA CÓ |
| AI/Qwen | CHƯA CÓ |
| config / backup / migration / recovery | CHƯA CÓ |
| hard-coded path `D:\HanNguServer` | KHÔNG TỒN TẠI (repo trống) |
| secret trong repo | KHÔNG TỒN TẠI (repo trống) |
| marker FINAL/DO NOT MODIFY/LOCKED | KHÔNG TỒN TẠI |

## Quyết định kiến trúc

Vì repo trống, không có "code hiện tại" để bảo toàn. Xây dựng mới theo kiến trúc
đề xuất trong task, tuân thủ toàn bộ nguyên tắc của MASTER PROMPT:

- Portable: mọi path derive từ `APP_ROOT`, không hard-code absolute path
- Local-first: SQLite (stdlib), FastAPI backend, frontend tĩnh đơn giản
- Không over-engineer: stdlib tối đa, ít dependency
- `process_video.py` là module độc lập do user tự cập nhật sau → chỉ tạo adapter
- Qwen là external service (máy B), app không crash khi Qwen offline
- Không bịa metric/score: trả `null` khi không tính được
- Test trung thực: không báo PASS giả

## Môi trường kiểm chứng

- Python 3.12.3 (`/usr/bin/python3`)
- ffmpeg: CÓ (`/usr/bin/ffmpeg`)
- OS hiện tại: Linux (app mục tiêu chạy tốt trên Windows — giữ `.bat`)
