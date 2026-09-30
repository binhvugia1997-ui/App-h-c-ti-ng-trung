@echo off
REM ============================================================
REM MIGRATE_EXPORT.bat - Xuat du lieu de chuyen sang may khac
REM - Tim Python bang `where python` (khong hard-code duong dan)
REM - Ket qua: goi du lieu trong thu muc migration-output
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

echo Dang xuat du lieu de migration...
python -m app.migration.export_cli --out "%~dp0..\migration-output"

if errorlevel 1 (
  echo.
  echo [LOI] Export that bai. Kiem tra log o tren.
  pause
  exit /b 1
)

echo.
echo Export thanh cong. Copy thu muc migration-output sang may moi.
pause
