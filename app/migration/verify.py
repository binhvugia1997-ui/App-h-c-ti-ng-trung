"""Verify installation: kiểm chứng cài đặt sau migration.

Mỗi nhóm trả về ``{"trang_thai": PASS|PARTIAL|FAIL|NOT_TESTED, "chi_tiet": ...}``.
Mọi kiểm tra đều chạy THẬT (mở DB, đọc thư mục, import module, gọi client...),
không đoán, không bịa số.
"""

from __future__ import annotations

import importlib.util
import json
import platform
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app import __version__ as _APP_VERSION
from app.config import settings
from app.logging_config import get_logger
from app.paths import (
    APP_ROOT,
    BACKUP_DIR,
    CONFIG_DIR,
    DATA_DIR,
    LOGS_DIR,
    MEDIA_DIR,
    MODEL_DIR,
    RECORDINGS_DIR,
    RECOVERY_DIR,
    TRASH_DIR,
)

log = get_logger(__name__)

OLD_ROOT_HINTS = ("D:\\HanNguServer", "D:/HanNguServer")

_HOC_TAP_KEYWORDS = ("vocab", "tu_vung", "tuvung", "pronunciation", "phat_am",
                     "phatam", "calibration", "hieu_chuan", "hieuchuan")


def _group(trang_thai: str, chi_tiet: str, muc_kiem_tra: list | None = None) -> dict:
    return {"trang_thai": trang_thai, "chi_tiet": chi_tiet,
            "muc_kiem_tra": muc_kiem_tra or []}


def _check_migration_system() -> dict:
    checks, missing = [], []
    for mod, funcs in (("app.migration.export", ["create_export_package"]),
                       ("app.migration.import_", ["import_package"]),
                       ("app.migration.verify", ["verify_installation"]),
                       ("app.migration.dry_run", ["ke_hoach_export", "ke_hoach_import"])):
        try:
            module = importlib.import_module(mod)
            ok = all(callable(getattr(module, f, None)) for f in funcs)
            checks.append(f"{mod}: {'OK' if ok else 'thiếu hàm'}")
            if not ok:
                missing.append(mod)
        except Exception as exc:  # noqa: BLE001
            checks.append(f"{mod}: LỖI import ({exc})")
            missing.append(mod)
    if not missing:
        return _group("PASS", "Đủ 4 module migration (export/import/verify/dry_run).", checks)
    if len(missing) < 4:
        return _group("PARTIAL", f"Thiếu: {', '.join(missing)}.", checks)
    return _group("FAIL", "Không import được module migration nào.", checks)


def _open_db() -> tuple[sqlite3.Connection | None, str]:
    db_path = Path(str(settings.db_path))
    if not db_path.exists():
        return None, f"Không tìm thấy file database: {db_path.name}"
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("SELECT 1").fetchone()
        return conn, ""
    except Exception as exc:  # noqa: BLE001
        return None, f"Không mở được database: {exc}"


def _user_tables(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]


def _check_database() -> dict:
    conn, err = _open_db()
    if conn is None:
        return _group("FAIL", err)
    try:
        tables = _user_tables(conn)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    checks = [f"số bảng: {len(tables)}", f"integrity_check: {integrity}"]
    if not tables:
        return _group("PARTIAL", "DB mở được nhưng chưa có bảng dữ liệu nào.", checks)
    if integrity != "ok":
        return _group("FAIL", f"DB mở được nhưng integrity_check báo: {integrity}", checks)
    return _group("PASS", f"DB mở được, toàn vẹn, có {len(tables)} bảng: "
                          f"{', '.join(tables[:10])}{'...' if len(tables) > 10 else ''}.",
                  checks)


def _check_learning_data() -> dict:
    conn, err = _open_db()
    if conn is None:
        return _group("FAIL", err)
    try:
        tables = _user_tables(conn)
        found = []
        for table in tables:
            if any(kw in table.lower() for kw in _HOC_TAP_KEYWORDS):
                n = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                found.append(f"{table} ({n} dòng)")
    finally:
        conn.close()
    if not found:
        return _group("FAIL", "Không tìm thấy bảng học tập nào "
                               "(vocab/pronunciation/calibration).",
                      [f"tổng số bảng trong DB: {len(tables)}"])
    empty = [f for f in found if f.endswith("(0 dòng)")]
    if len(empty) == len(found):
        return _group("PARTIAL", "Đã có bảng học tập nhưng tất cả đều trống.", found)
    return _group("PASS", f"Tìm thấy dữ liệu học tập: {'; '.join(found)}.", found)


def _check_dir(path: Path, ten: str) -> dict:
    if not path.exists():
        return _group("FAIL", f"Thiếu thư mục {ten}.")
    files = [p for p in path.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    chi_tiet = f"Thư mục {ten} OK: {len(files)} file, {total} bytes."
    if not files:
        return _group("PARTIAL", chi_tiet + " (đang trống — bình thường với cài mới).")
    return _group("PASS", chi_tiet)


def _check_pronunciation_calibration() -> dict:
    conn, err = _open_db()
    if conn is None:
        return _group("FAIL", err)
    try:
        tables = _user_tables(conn)
        found = [t for t in tables
                 if "pronunciation" in t.lower() or "phat_am" in t.lower()
                 or "calibration" in t.lower() or "hieu_chuan" in t.lower()]
        detail = []
        for table in found:
            n = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            detail.append(f"{table} ({n} dòng)")
    finally:
        conn.close()
    if not found:
        return _group("FAIL", "Không tìm thấy bảng pronunciation/calibration.")
    if all(d.endswith("(0 dòng)") for d in detail):
        return _group("PARTIAL", f"Có bảng nhưng trống: {'; '.join(detail)}.", detail)
    return _group("PASS", f"Dữ liệu phát âm/hiệu chuẩn: {'; '.join(detail)}.", detail)


def _check_recovery() -> dict:
    try:
        from app.recovery import list_recovery_points
        points = list_recovery_points()
    except Exception as exc:  # noqa: BLE001
        return _group("FAIL", f"Không gọi được module recovery: {exc}")
    if not RECOVERY_DIR.exists():
        return _group("FAIL", "Thiếu thư mục recovery.")
    if not points:
        return _group("PARTIAL", "Module recovery OK nhưng chưa có recovery point nào.")
    return _group("PASS", f"Module recovery OK, có {len(points)} recovery point "
                          f"(mới nhất: {points[0]['name']}).")


def _check_trash() -> dict:
    try:
        from app.trash import list_trash, restore_trash  # noqa: F401
        items = list_trash()
    except Exception as exc:  # noqa: BLE001
        return _group("FAIL", f"Không gọi được module trash: {exc}")
    if not TRASH_DIR.exists():
        return _group("FAIL", "Thiếu thư mục trash.")
    return _group("PASS", f"Module trash OK, hiện có {len(items)} mục trong thùng rác.")


def _check_config() -> dict:
    if not CONFIG_DIR.exists():
        return _group("FAIL", "Thiếu thư mục config.")
    files = [p.relative_to(CONFIG_DIR).as_posix()
             for p in sorted(CONFIG_DIR.rglob("*")) if p.is_file()]
    return _group("PASS", f"Thư mục config OK: {len(files)} file.",
                  files[:20])


def _check_secrets() -> dict:
    checks: list[str] = []
    # 1. Không có file .env lọt vào DATA_DIR.
    env_in_data = [p for p in DATA_DIR.rglob(".env")] if DATA_DIR.exists() else []
    if env_in_data:
        return _group("FAIL", ".env lọt vào thư mục dữ liệu: "
                               + ", ".join(str(p) for p in env_in_data))
    checks.append("không có .env trong DATA_DIR")
    # 2. Gói export mới nhất (nếu có): config không chứa secret chưa redact.
    exports_base = DATA_DIR / "migration-exports"
    packages = sorted(exports_base.glob("hanngu-migration-*")) if exports_base.exists() else []
    if packages:
        pkg = packages[-1]
        bad: list[str] = []
        for cfg in (pkg / "config").rglob("*.json"):
            try:
                text = cfg.read_text(encoding="utf-8")
            except OSError:
                continue
            lowered = text.lower()
            if "reauth required" not in lowered:
                for hint in ("access_token", "refresh_token", "api_key", "client_secret"):
                    if f'"{hint}"' in lowered:
                        bad.append(f"{cfg.name}: chứa {hint} chưa redact")
        if bad:
            return _group("FAIL", "Gói export mới nhất còn lộ secret: " + "; ".join(bad))
        checks.append(f"gói {pkg.name}: config đã redact secret")
    else:
        checks.append("chưa có gói export nào để kiểm tra (bỏ qua)")
    return _group("PASS", "Không phát hiện secret lộ: " + "; ".join(checks) + ".", checks)


def _check_models() -> dict:
    if not MODEL_DIR.exists():
        return _group("FAIL", "Thiếu thư mục models.")
    files = [p for p in MODEL_DIR.rglob("*") if p.is_file()]
    if not files:
        return _group("PARTIAL", "Thư mục models trống — cần tải model trên máy mới "
                                  "(gói migration chỉ mang manifest).")
    total = sum(p.stat().st_size for p in files)
    return _group("PASS", f"Có {len(files)} file model ({total} bytes).",
                  [p.relative_to(MODEL_DIR).as_posix() for p in files[:20]])


def _check_qwen() -> dict:
    try:
        from app.qwen.client import get_qwen_client
    except Exception as exc:  # noqa: BLE001
        return _group("NOT_TESTED", f"Module app.qwen.client chưa sẵn sàng: {exc}")
    try:
        result = get_qwen_client().check()
    except Exception as exc:  # noqa: BLE001
        return _group("FAIL", f"Không gọi được Qwen client: {exc}")
    if result.get("ok"):
        return _group("PASS",
                      f"Qwen kết nối OK (model={result.get('model')}, "
                      f"{result.get('latency_ms')}ms).")
    return _group("FAIL", f"Qwen không kết nối được: {result.get('message_vi')}")


def _check_google_drive() -> dict:
    names = ("google_drive_folder_id", "drive_folder_id", "gdrive_enabled",
             "google_drive_enabled")
    found = {name: getattr(settings, name, None) for name in names}
    found = {k: v for k, v in found.items() if v}
    if not found:
        return _group("NOT_TESTED", "Chưa cấu hình Google Drive (không tìm thấy "
                                    "thiết lập drive trong settings).")
    return _group("PASS", f"Đã cấu hình Google Drive: {', '.join(found)}.")


def _check_old_absolute_path() -> dict:
    found: list[str] = []
    conn, _ = _open_db()
    if conn is not None:
        try:
            for table in _user_tables(conn):
                info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
                for col in info:
                    ctype = str(col[2]).upper()
                    if "TEXT" not in ctype and "CHAR" not in ctype and "CLOB" not in ctype:
                        continue
                    for hint in OLD_ROOT_HINTS:
                        n = conn.execute(
                            f'SELECT COUNT(*) FROM "{table}" WHERE "{col[1]}" LIKE ?',
                            (f"%{hint}%",)).fetchone()[0]
                        if n:
                            found.append(f"DB {table}.{col[1]}: {n} dòng chứa '{hint}'")
        finally:
            conn.close()
    if CONFIG_DIR.exists():
        for cfg in CONFIG_DIR.rglob("*"):
            if not cfg.is_file():
                continue
            try:
                text = cfg.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for hint in OLD_ROOT_HINTS:
                if hint in text:
                    found.append(f"config {cfg.relative_to(CONFIG_DIR)}: chứa '{hint}'")
    if found:
        return _group("FAIL", "FOUND — vẫn còn dấu vết đường dẫn tuyệt đối máy cũ.",
                      found[:10])
    return _group("PASS", "REMOVED — không tìm thấy dấu vết 'D:\\HanNguServer' "
                          "trong DB và config.")


def _check_new_install_path() -> dict:
    app_root = APP_ROOT.resolve()
    offenders: list[str] = []
    paths = {
        "DATA_DIR": DATA_DIR, "MEDIA_DIR": MEDIA_DIR, "RECORDINGS_DIR": RECORDINGS_DIR,
        "RECOVERY_DIR": RECOVERY_DIR, "TRASH_DIR": TRASH_DIR, "CONFIG_DIR": CONFIG_DIR,
        "BACKUP_DIR": BACKUP_DIR, "MODEL_DIR": MODEL_DIR, "LOGS_DIR": LOGS_DIR,
        "db_path": Path(str(settings.db_path)),
    }
    for name, path in paths.items():
        try:
            resolved = Path(path).resolve()
            if resolved != app_root and app_root not in resolved.parents:
                offenders.append(f"{name}={resolved}")
        except OSError:
            offenders.append(f"{name}: không resolve được")
    if offenders:
        return _group("FAIL", "Một số đường dẫn KHÔNG nằm dưới APP_ROOT "
                               "(không portable).", offenders)
    return _group("PASS", f"PORTABLE — mọi đường dẫn đều suy từ APP_ROOT ({app_root}).")


def _check_dependencies() -> dict:
    required = ("fastapi", "uvicorn", "dotenv", "httpx")
    missing = [name for name in required
               if importlib.util.find_spec(name) is None]
    checks = [f"{name}: {'OK' if name not in missing else 'THIẾU'}"
              for name in required]
    if not missing:
        return _group("PASS", "Đủ dependency: fastapi, uvicorn, dotenv, httpx.", checks)
    return _group("FAIL", f"Thiếu dependency: {', '.join(missing)}. "
                          "Chạy: pip install -r requirements.txt", checks)


def _check_ffmpeg() -> dict:
    configured = (settings.ffmpeg_path or "").strip()
    if configured and Path(configured).exists():
        return _group("PASS", f"ffmpeg đã cấu hình: {configured}.")
    found = shutil.which("ffmpeg")
    if found:
        return _group("PASS", f"Tìm thấy ffmpeg trong PATH: {found}.")
    return _group("FAIL", "Không tìm thấy ffmpeg (cả cấu hình lẫn PATH). "
                          "Cần cài ffmpeg để xử lý video/audio.")


def _check_gpu_support() -> dict:
    info = {"he_dieu_hanh": platform.system(), "kien_truc": platform.machine()}
    try:
        import torch  # type: ignore
        info["torch"] = torch.__version__
        info["cuda_kha_dung"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            info["ten_gpu"] = torch.cuda.get_device_name(0)
    except ImportError:
        info["torch"] = "chưa cài (app chạy CPU-only, không bắt buộc)"
    except Exception as exc:  # noqa: BLE001
        info["torch"] = f"lỗi khi kiểm tra: {exc}"
    # Nhóm này mang tính thông tin: luôn PASS nếu kiểm tra chạy được.
    chi_tiet = ("Hỗ trợ GPU khác nhau: " +
                "; ".join(f"{k}={v}" for k, v in info.items()) +
                ". App chạy CPU-only; Qwen qua Ollama tận dụng GPU của máy host "
                "nếu có.")
    return _group("PASS", chi_tiet, [f"{k}={v}" for k, v in info.items()])


_CHECKS: list[tuple[str, callable]] = [
    ("MIGRATION SYSTEM", _check_migration_system),
    ("DATABASE SNAPSHOT", _check_database),
    ("LEARNING DATA", _check_learning_data),
    ("MEDIA", lambda: _check_dir(MEDIA_DIR, "media")),
    ("RECORDINGS", lambda: _check_dir(RECORDINGS_DIR, "recordings")),
    ("PRONUNCIATION/CALIBRATION", _check_pronunciation_calibration),
    ("RECOVERY", _check_recovery),
    ("TRASH", _check_trash),
    ("CONFIG", _check_config),
    ("SECRETS", _check_secrets),
    ("MODELS", _check_models),
    ("QWEN", _check_qwen),
    ("GOOGLE DRIVE", _check_google_drive),
    ("OLD ABSOLUTE PATH", _check_old_absolute_path),
    ("NEW INSTALL PATH", _check_new_install_path),
    ("DEPENDENCIES", _check_dependencies),
    ("FFMPEG", _check_ffmpeg),
    ("DIFFERENT GPU SUPPORT", _check_gpu_support),
]


def verify_installation() -> dict:
    """Chạy toàn bộ kiểm chứng, trả về {"ok": True, "data": {groups, tom_tat}}."""
    groups: dict[str, dict] = {}
    for name, func in _CHECKS:
        try:
            groups[name] = func()
        except Exception as exc:  # noqa: BLE001
            log.error("Verify nhóm %s lỗi: %s", name, exc)
            groups[name] = _group("FAIL", f"Lỗi khi kiểm tra: {exc}")
    tom_tat: dict[str, int] = {}
    for result in groups.values():
        status = result.get("trang_thai", "NOT_TESTED")
        tom_tat[status] = tom_tat.get(status, 0) + 1
    return {"ok": True,
            "data": {"generated_at": datetime.now().isoformat(timespec="seconds"),
                     "app_version": _APP_VERSION,
                     "app_root": str(APP_ROOT),
                     "groups": groups,
                     "tom_tat": tom_tat}}
