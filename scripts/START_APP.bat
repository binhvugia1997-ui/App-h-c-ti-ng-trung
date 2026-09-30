@echo off
REM ============================================================
REM START_APP.bat - Khoi dong Han Ngu Server
REM - Tim Python bang `where python` (khong hard-code duong dan)
REM - Chay uvicorn tai dia chi 127.0.0.1:8000
REM   (host/port tu .env se duoc app doc; neu muon doi,
REM    sua file .env roi chay lai file nay)
REM ============================================================
setlocal
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
  echo [LOI] Khong tim thay Python. Vui long cai Python 3.10+ tu https://www.python.org/downloads/
  echo       va danh dau "Add python.exe to PATH" khi cai dat.
  pause
  exit /b 1
)

echo Dang khoi dong Han Ngu Server...
echo Mo trinh duyet va truy cap: http://127.0.0.1:8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

if errorlevel 1 (
  echo.
  echo [LOI] Server da dung dot ngot. Kiem tra log o tren.
  pause
  exit /b 1
)
