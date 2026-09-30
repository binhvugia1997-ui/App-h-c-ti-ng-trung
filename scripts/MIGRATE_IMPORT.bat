@echo off
REM ============================================================
REM MIGRATE_IMPORT.bat - Nhap du lieu tu may cu (migration)
REM Cach dung: keo-tha thu muc migration-output vao file .bat nay,
REM             hoac go: MIGRATE_IMPORT.bat "duong-dan-toi-migration-output"
REM - Tim Python bang `where python` (khong hard-code duong dan)
REM ============================================================
setlocal
cd /d "%~dp0.."

if "%~1"=="" (
  echo [LOI] Thieu thu muc du lieu can nhap.
  echo Cach dung: keo-tha thu muc "migration-output" tu may cu vao file .bat nay.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo [LOI] Khong tim thay Python. Vui long cai Python 3.10+ tu https://www.python.org/downloads/
  echo       va danh dau "Add python.exe to PATH" khi cai dat.
  pause
  exit /b 1
)

echo Dang nhap du lieu tu: %~1
python -m app.migration.import_cli --in "%~1"

if errorlevel 1 (
  echo.
  echo [LOI] Import that bai. Kiem tra log o tren.
  pause
  exit /b 1
)

echo.
echo Import thanh cong. Chay VERIFY_MIGRATION.bat de kiem tra.
pause
