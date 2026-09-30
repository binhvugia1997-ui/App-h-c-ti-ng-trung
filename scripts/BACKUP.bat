@echo off
REM ============================================================
REM BACKUP.bat - Sao luu du lieu Han Ngu Server
REM - Tim Python bang `where python` (khong hard-code duong dan)
REM - File backup .zip se duoc tao trong data\backups
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

echo Dang sao luu du lieu...
python -m app.backup.backup_cli

if errorlevel 1 (
  echo.
  echo [LOI] Sao luu that bai. Kiem tra log o tren.
  pause
  exit /b 1
)

echo.
echo Sao luu thanh cong. File backup nam trong thu muc data\backups
pause
