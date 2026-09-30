@echo off
REM ============================================================
REM VERIFY_MIGRATION.bat - Kiem tra du lieu sau khi migration
REM - Tim Python bang `where python` (khong hard-code duong dan)
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

echo Dang kiem tra du lieu sau migration...
python -m app.migration.verify_cli

if errorlevel 1 (
  echo.
  echo [LOI] Kiem tra that bai hoac du lieu khong khop. Kiem tra log o tren.
  pause
  exit /b 1
)

echo.
echo Kiem tra xong. Xem ket qua o tren.
pause
