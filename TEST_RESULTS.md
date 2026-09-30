# TEST_RESULTS — Hán Ngữ Server

Ngày: 2026-09-30
Môi trường test: Python 3.12.3, venv riêng (`/tmp/hanngu-test/venv`),
`HANNGU_DATA_DIR=/tmp/hanngu-test/data` (không làm bẩn repo),
ffmpeg 8.1.2 có sẵn, **không có Qwen/Ollama** (test offline fallback).

> Nguyên tắc: chỉ ghi PASS khi đã chạy test thật. Không PASS giả.

## Kết quả tổng hợp (theo MASTER PROMPT mục 49)

| Hạng mục | Kết quả | Ghi chú |
|---|---|---|
| APP START | **PASS** | `run_startup()` 6 bước OK; uvicorn serve; `GET /` trả web UI tiếng Việt |
| DATABASE | **PASS** | SQLite khởi tạo 14 bảng qua auto-discovery `init_db` của mọi module |
| PORTABLE PATH | **PASS** | Copy repo sang `/tmp/hanngu-test/relocated` (mô phỏng máy mới khác drive): startup OK, verify `NEW INSTALL PATH: PASS`, `OLD ABSOLUTE PATH: PASS (REMOVED)` |
| FFMPEG | **PASS** | Detect `/usr/bin/ffmpeg` 8.1.2; thứ tự settings → bundled → PATH |
| QWEN CLIENT | **PARTIAL** | `check/chat/chat_json`, retry, parse/repair JSON đã test logic; **chưa test với Qwen thật** (không có máy Qwen trong môi trường test) |
| QWEN OFFLINE FALLBACK | **PASS** | `POST /api/exercises/viet-trung` → `{"ok":false,"error_vi":"Máy AI hiện không kết nối được. Vui lòng kiểm tra máy Qwen."}` (HTTP 502), không crash, không lộ stack trace; `/api/health` vẫn UP, qwen DOWN |
| VIDEO JOB | **PARTIAL** | Tạo job, worker thread, fail thân thiện khi thiếu `process_video.py` FINAL, cancel, `recover_on_startup`; **pipeline full NOT TESTED** (đúng thiết kế: `process_video.py` do user tự cập nhật sau) |
| CHECKPOINT INTEGRATION | **PASS** | Save/load/mark_done roundtrip; resume bỏ qua stage đã hoàn thành (test bởi module video) |
| RECORDINGS | **PASS** | Upload shadowing/pronunciation → `RECORDINGS_DIR`; playback qua `/api/shadowing/recordings/{file}` (chặn path traversal) |
| PRONUNCIATION | **PARTIAL** | Lưu bản ghi + calibration OK; 4 metric = `null` trung thực (chưa có engine chấm — đúng yêu cầu "không bịa điểm") |
| BACKUP | **PASS** | `POST /api/backup` tạo zip + manifest sha256; `backup_cli --dry-run` OK |
| RESTORE | **PASS** | Restore dry-run liệt kê đúng; restore thật đã test bởi module data-mgmt (file bị xóa quay lại, recovery point tự tạo) |
| MIGRATE EXPORT | **PASS** | Gói đầy đủ db/learning/media/recordings/config-redact/qwen; secret → `REAUTH REQUIRED`; path máy cũ → `<APP_ROOT>` |
| MIGRATE IMPORT | **PASS** | Import thật sang data trống: validate → recovery point → copy → remap → verify DB đủ 14 bảng |
| VERIFY MIGRATION | **PASS** | CLI chạy thật: 13 PASS / 2 PARTIAL / 1 NOT_TESTED / 2 FAIL — trong đó QWEN FAIL là đúng thực tế (offline), NEW INSTALL PATH FAIL chỉ do test dùng `HANNGU_DATA_DIR` ngoài APP_ROOT (đã PASS khi chạy portable test) |
| OLD ABSOLUTE PATH | **REMOVED** | Quét DB + config: không dấu vết `D:\HanNguServer` (chuỗi còn lại chỉ trong migration compatibility logic — được phép theo mục 50) |
| GOOGLE DRIVE | **NOT CONFIGURED** | Đúng thực tế — local app chạy bình thường không cần Drive |

## API đã test end-to-end (curl, HTTP 200 + `{"ok":true}`)

- `GET /api/health` (core UP / external phân biệt) · `GET /` + `/static/app.js` (web UI)
- Dashboard: `GET /summary`, `POST /log`
- Vocab: CRUD, `GET /flashcards`, `POST /{id}/review`
- Dictation: `GET /exercise` (fallback vocab), `POST /submit` (diff đúng từng ký tự: 你好 dung / 吗 sai / ？ thieu), `GET /attempts`
- Exercises: `POST /viet-trung` (offline → lỗi thân thiện)
- Video: `GET /status`, `POST /upload`, `POST /jobs`, `GET /jobs`, `GET /lessons`
- Pronunciation: `POST /analyze` (metric null), `GET /results`
- Shadowing: `POST /sessions`, `GET /sessions`
- Trash: `GET /`
- Settings: `GET /`, `PUT /` (ghi `.env`, reload)
- Migration: `GET /verify`, `POST /dry-run` (CLI: export/import/verify)

## Bug phát hiện & đã sửa trong PHASE TEST (không giấu)

1. **Thiếu `python-multipart`** → 4 router (video, shadowing, pronunciation, migration) bị auto-discovery bỏ qua lặng lẽ. Đã thêm vào `requirements.txt`. (Cơ chế discovery vẫn đúng: app không crash khi thiếu dependency.)
2. **Lệch endpoint/field giữa frontend và backend** (7 điểm: dashboard log, vocab review, shadowing create/recording, exercises field names, dictation submit, pronunciation form fields, video upload→job). Đã thống nhất: backend thêm `POST /api/backup`, dictation tự tra `cau_dung` từ `source_id`/`vocab_id`, video lesson trả shape phẳng; frontend sửa field names + render theo schema mới.
3. **QwenClient đi qua proxy hệ thống bị hỏng** trong môi trường sandbox → `httpx.Client(trust_env=False)` (Qwen là LAN/local, luôn kết nối trực tiếp).
4. **`get_lesson` video** từng bị edit lỗi (mất dòng fetch) — đã sửa và test lại.

## Chưa test / giới hạn trung thực

- Chat thật với Qwen/Ollama (cần máy B) → AI exercises end-to-end với model thật: NOT TESTED
- Pipeline video full (cần `process_video.py` bản FINAL của user): NOT TESTED
- Google Drive backup: NOT CONFIGURED (thiết kế: local chạy độc lập)
- Windows `.bat`: kiểm tra nội dung (không hard-code path) — chưa chạy trên Windows thật
