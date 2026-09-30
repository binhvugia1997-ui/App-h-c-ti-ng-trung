# Hán Ngữ Server

Ứng dụng học tiếng Trung **chạy hoàn toàn trên máy của bạn** (local-first), giao diện tiếng Việt.
Gồm: từ vựng + flashcard SRS, học qua video (tách câu, pinyin, dịch), shadowing,
nghe chép chính tả, luyện dịch Việt↔Trung, phân tích phát âm, dashboard theo dõi tiến độ,
sao lưu/phục hồi và migration chuyển máy.

> ⚠️ **Lưu ý về `process_video.py`**: file này KHÔNG có trong repo. Nó là module độc lập
> do **bạn tự cập nhật bản FINAL** và đặt vào vị trí mà app mong đợi (xem PLAN.md mục video).
> App được thiết kế để **chạy bình thường khi file vắng mặt** — các tính năng video sẽ
> báo rõ ràng là "chưa có module xử lý video", không crash. Không tạo/sửa file này thay bạn.

---

## 1. Cài đặt dependency

Yêu cầu: Python 3.10+ (đã đánh dấu "Add python.exe to PATH" khi cài trên Windows) và `ffmpeg`.

```bash
# Windows (cmd)
cd /d <duong-dan-thu-muc-app>
pip install -r requirements.txt

# Linux/Mac
cd <duong-dan-thu-muc-app>
pip install -r requirements.txt
```

`ffmpeg` cần cho xử lý audio/video:
- Windows: tải tại https://ffmpeg.org/download.html, giải nén, thêm thư mục `bin` vào PATH
  (hoặc khai báo đường dẫn trong `.env` → `FFMPEG_PATH`).
- Linux: `sudo apt install ffmpeg`
- Mac: `brew install ffmpeg`

Kiểm tra: `ffmpeg -version`

---

## 2. Cấu hình `.env`

```bash
copy .env.example .env     # Windows
cp .env.example .env       # Linux/Mac
```

Mở `.env` và sửa các mục cần thiết (chi tiết từng key xem file `.env.example`):

| Key | Ý nghĩa | Mặc định |
|---|---|---|
| `HOST` | Địa chỉ lắng nghe (`127.0.0.1` = chỉ máy này; `0.0.0.0` = cho phép LAN) | `127.0.0.1` |
| `PORT` | Cổng web | `8000` |
| `HANNGU_DB_PATH` | File SQLite (để trống = `data/hanngu.db`) | — |
| `HANNGU_DATA_DIR` | Thư mục dữ liệu (để trống = `data/`) | — |
| `FFMPEG_PATH` | Đường dẫn ffmpeg (để trống = tự tìm) | — |
| `QWEN_BASE_URL` | Địa chỉ máy AI Qwen, ví dụ `http://192.168.1.50:11434` | `http://127.0.0.1:11434` |
| `QWEN_MODEL` | Tên model Ollama | `qwen2.5:7b` |
| `LOG_LEVEL` | Mức log | `INFO` |

> Không commit file `.env` thật lên git.

---

## 3. Chạy app

- Windows: nhấp đúp **`scripts\START_APP.bat`**
- Linux/Mac (hoặc thủ công):

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Mở trình duyệt: **http://127.0.0.1:8000**
(đổi `127.0.0.1` thành IP LAN của máy nếu truy cập từ thiết bị khác, khi `HOST=0.0.0.0`).

Dừng app: nhấn `Ctrl+C` trong cửa sổ đang chạy.

---

## 4. Cấu hình máy Qwen (máy AI thứ 2)

App gọi AI qua **Ollama** chạy trên một máy khác trong cùng mạng LAN
(hoặc chính máy này nếu đủ mạnh).

Trên máy Qwen:

1. Cài Ollama: https://ollama.com
2. Tải model: `ollama pull qwen2.5:7b`
3. Cho phép máy khác gọi tới (mặc định Ollama chỉ nghe localhost):
   - Windows: set biến môi trường `OLLAMA_HOST=0.0.0.0`, khởi động lại Ollama
   - Linux: `sudo systemctl edit ollama` → thêm
     `[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0"`, rồi `sudo systemctl restart ollama`
4. Mở firewall cho cổng `11434` (chỉ trong mạng LAN nhà bạn).
5. Ghi lại IP LAN của máy Qwen, ví dụ `192.168.1.50`.

Trên máy chạy app, sửa `.env`:

```
QWEN_BASE_URL=http://192.168.1.50:11434
QWEN_MODEL=qwen2.5:7b
```

Hoặc sửa trực tiếp trong app: tab **Cài đặt** → mục "Kết nối máy AI".

---

## 5. Kiểm tra kết nối Qwen

- Trong app: tab **Cài đặt** → nút **🔄 Kiểm tra lại** (mục "Trạng thái hệ thống").
  Dòng Qwen hiện ✅ là kết nối tốt; ❌ kèm thông báo tiếng Việt nếu không kết nối được.
- Hoặc gọi API trực tiếp: `GET /api/health` — trường `external` cho biết trạng thái Qwen.

> App **không crash** khi Qwen offline. Các tính năng cần AI (chấm dịch, phân tích phát âm...)
> sẽ báo rõ "Máy AI hiện không kết nối được", các tính năng còn lại vẫn dùng bình thường.

---

## 6. Import video (học qua video)

1. Chuẩn bị file `process_video.py` **bản FINAL do bạn tự cung cấp** (xem lưu ý đầu README).
2. Trong app: tab **Video** → chọn file video → **⬆️ Tải lên & xử lý**.
3. Theo dõi tiến trình ở mục "Tiến trình xử lý" (tự cập nhật mỗi 3 giây).
4. Xong: bài học xuất hiện ở "Bài học từ video". Nhấn vào bài học để xem danh sách câu,
   nhấn từng câu để nhảy tới đúng đoạn trong video. Có thể bật/tắt Pinyin và nghĩa Việt.

---

## 7. Sao lưu (Backup)

- Windows: nhấp đúp **`scripts\BACKUP.bat`**
- Hoặc trong app: tab **Cài đặt** → **💾 Sao lưu ngay**
- Thủ công: `python -m app.backup.backup_cli`

File backup `.zip` nằm trong `data\backups\`. Nên copy file này ra USB/ổ khác định kỳ.

---

## 8. Phục hồi (Restore)

1. Đảm bảo app **đang tắt**.
2. Giải nén file `.zip` backup gần nhất vào thư mục `data/` (ghi đè các file cũ).
3. Chạy lại app.

> Nếu muốn an toàn, hãy đổi tên thư mục `data` hiện tại thành `data.bak` trước khi giải nén,
> để có thể quay lại khi cần.

---

## 9. Export migration (chuyển sang máy mới)

Dùng khi bạn muốn **chuyển toàn bộ dữ liệu sang một máy khác** (không phải backup dự phòng).

- Windows: nhấp đúp **`scripts\MIGRATE_EXPORT.bat`**
- Thủ công: `python -m app.migration.export_cli --out migration-output`

Kết quả: thư mục `migration-output` chứa toàn bộ dữ liệu ở định dạng portable.
**Copy thư mục này sang máy mới** (USB, mạng LAN...).

---

## 10. Import migration (trên máy mới)

1. Cài app mới trên máy mới (mục 1–3), **chưa cần nhập dữ liệu**.
2. Copy thư mục `migration-output` từ máy cũ sang máy mới.
3. Windows: **kéo-thả** thư mục `migration-output` vào file **`scripts\MIGRATE_IMPORT.bat`**,
   hoặc chạy: `scripts\MIGRATE_IMPORT.bat "D:\duong\dan\migration-output"`
4. Thủ công: `python -m app.migration.import_cli --in "<duong-dan>/migration-output"`

---

## 11. Verify migration (kiểm tra sau khi chuyển máy)

Sau khi import, kiểm tra dữ liệu có đầy đủ và khớp với máy cũ không:

- Windows: nhấp đúp **`scripts\VERIFY_MIGRATION.bat`**
- Trong app: tab **Cài đặt** → **✔️ Kiểm tra migration**
- Thủ công: `python -m app.migration.verify_cli`

Nếu báo không khớp, **đừng xóa dữ liệu máy cũ** — kiểm tra log và chạy lại import.

---

## 12. Vị trí dữ liệu người dùng

Mọi dữ liệu đều nằm dưới thư mục `data/` ngay trong thư mục app (portable —
copy cả thư mục app sang chỗ khác là mang theo toàn bộ dữ liệu):

```
<app>/
  data/
    hanngu.db        # Database SQLite (từ vựng, bài học, lịch sử...)
    media/           # Video đã upload + file sinh ra khi xử lý
    recordings/      # Bản thu âm shadowing / phát âm
    backups/         # File .zip sao lưu
    recovery/        # File khôi phục khẩn cấp
    trash/           # Thùng rác (xóa mềm)
    config/          # Cấu hình lưu từ tab Cài đặt
    models/          # Model local (nếu có)
    logs/            # Log chạy app
```

Muốn dùng ổ đĩa khác: đặt `HANNGU_DATA_DIR` (và/hoặc `HANNGU_DB_PATH`) trong `.env`.

---

## Cấu trúc repo

```
hanngu-server/
  app/            # Backend FastAPI (core, qwen, video, vocab, dashboard,
                  #   shadowing, pronunciation, dictation, backup, migration...)
  web/            # Frontend tĩnh: index.html, style.css, app.js
  scripts/        # File .bat cho Windows: START_APP, BACKUP,
                  #   MIGRATE_EXPORT, MIGRATE_IMPORT, VERIFY_MIGRATION
  .env.example    # Mẫu cấu hình
  requirements.txt
  README.md  AUDIT.md  PLAN.md  TEST_RESULTS.md
```

API tuân thủ quy ước: thành công `{"ok": true, "data": ...}`,
lỗi `{"ok": false, "error_vi": "..."}` (tiếng Việt, không lộ stack trace).
