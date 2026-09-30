[app]
# Tên hiển thị của app
title = Hán Ngữ
# Tên package (viết thường, không dấu cách)
package.name = hanngu
# Domain cho package id: org.hanngu.hanngu
package.domain = org.hanngu
# Thư mục source = gốc repo (đóng gói package app/ + kivy_app/)
source.dir = .
source.include_exts = py
# File khởi động
source.main = kivy_app/main.py
version = 0.1.0

# Thư viện Python cần: kivy (giao diện) + httpx (gọi máy Qwen)
requirements = python3,kivy,httpx

# Icon (tùy chọn, bỏ qua nếu chưa có)
#icon.filename = %(source.dir)s/kivy_app/icon.png
#presplash.filename = %(source.dir)s/kivy_app/presplash.png

orientation = portrait

# --- Android (buildozer đọc các option android.* từ section [app]) ---
android.api = 35
android.minapi = 24
android.ndk = 28c
# Bỏ qua sdkmanager (môi trường proxy có auth) — SDK/NDK/build-tools
# đã được cài tay trước vào ~/.buildozer/android/platform/android-sdk
android.skip_update = True
p4a.bootstrap = sdl2
# Quyền: mạng (gọi máy Qwen) + micro (thu âm shadowing sau này)
android.permissions = INTERNET,RECORD_AUDIO
# Giữ màn hình dọc, cho phép backup dữ liệu app
android.backup_rules =
# Kiến trúc: arm64 là phổ biến nhất hiện nay
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
