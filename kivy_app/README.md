# Hán Ngữ App — bản độc lập (Kivy, không cần trình duyệt)

Ứng dụng native chạy độc lập trên desktop và Android, tái dùng trực tiếp
backend Python trong `app/` (SQLite, SRS, Qwen client...). Không cần trình
duyệt web, không cần chạy server riêng.

## Chạy trên desktop (Windows / Linux / macOS)

```bash
pip install kivy httpx
python kivy_app/main.py
```

Dữ liệu lưu trong `kivy_app/data/` (portable, tách khỏi code).

## Build APK Android

```bash
pip install buildozer
# Cần JDK 17 + Android SDK/NDK (tự tải lần đầu)
buildozer android debug
# File APK nằm trong bin/
```

Cấu hình build trong `buildozer.spec`:
- `requirements = python3,kivy,httpx`
- Quyển: INTERNET (gọi máy Qwen), RECORD_AUDIO (thu âm sau này)
- Màn hình dọc, kiến trúc arm64-v8a

Trên Android, dữ liệu lưu trong bộ nhớ riêng của app
(`android.storage.app_storage_path()`), không cần quyền đọc/ghi ngoài.

## 9 màn hình

Hôm nay · Từ vựng (+ flashcard SRS) · Video · Shadowing · Nghe chép ·
Dịch (AI Qwen) · Phát âm · Lịch sử · Cài đặt

## Lưu ý

- Thu âm micro trên Android cần cấp quyền khi chạy (đã khai báo sẵn).
- Chức năng import video nặng nên dùng bản desktop/server;
  bản mobile tập trung vào học và ôn tập.
