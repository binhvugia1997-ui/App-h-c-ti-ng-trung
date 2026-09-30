"""Backup: tạo / liệt kê / khôi phục bản sao lưu (.zip) toàn bộ dữ liệu app.

Cấu trúc file zip ``hanngu-backup-YYYYMMDD-HHMMSS.zip``::

    database/      snapshot DB (settings.db_path)
    media/         media_dir (metadata + file)
    recordings/    recordings_dir
    config/        config đã loại bỏ / redact secret
    recovery/      chỉ meta.json của các recovery point (không copy toàn bộ)
    trash/         chỉ meta.json của các mục trong thùng rác
    manifest.json  {version, timestamp, app_version, files:[{path,sha256,size}], ghi_chu}

Sử dụng::

    from app.backup import create_backup, list_backups, restore_backup
    create_backup(ghi_chu="trước khi cập nhật")
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterator

from app import __version__ as _APP_VERSION
from app.config import settings
from app.db.database import get_conn
from app.logging_config import get_logger
from app.paths import (
    BACKUP_DIR,
    CONFIG_DIR,
    DATA_DIR,
    MEDIA_DIR,
    RECORDINGS_DIR,
    RECOVERY_DIR,
    TRASH_DIR,
    ensure_dirs,
)

log = get_logger(__name__)

MANIFEST_VERSION = "1.0"
REDACTED_MARKER = "REDACTED"

# File/thư mục cache/tạm luôn bị bỏ qua khi backup.
_SKIP_SUFFIXES = (".pyc", ".pyo", ".tmp", ".swp", ".bak", ".log")
_SKIP_DIR_NAMES = {"__pycache__", ".git", "node_modules", ".cache"}
_SKIP_FILE_NAMES = {"Thumbs.db", ".DS_Store"}

# Gợi ý tên file chứa secret: KHÔNG đưa vào backup, KHÔNG ghi đè khi restore.
_SENSITIVE_NAME_HINTS = (".env", "secret", "token", "private", ".pem", ".key")

# Key nhạy cảm trong file config JSON → redact giá trị.
_SENSITIVE_KEY_PARTS = (
    "password", "passwd", "pwd", "secret", "token",
    "api_key", "apikey", "private_key", "client_secret", "credential",
)


def _is_sensitive_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _is_sensitive_filename(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _SENSITIVE_NAME_HINTS)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _should_skip(path: Path) -> bool:
    if path.name in _SKIP_FILE_NAMES:
        return True
    if path.suffix.lower() in _SKIP_SUFFIXES:
        return True
    return any(part in _SKIP_DIR_NAMES for part in path.parts)


def _redact_json(obj):
    """Đệ quy redact giá trị của các key nhạy cảm trong JSON."""
    if isinstance(obj, dict):
        return {
            key: (REDACTED_MARKER if _is_sensitive_key(key) else _redact_json(value))
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_json(item) for item in obj]
    return obj


def _iter_tree_files(root: Path) -> Iterator[Path]:
    """Liệt kê file trong cây thư mục, bỏ qua cache/tạm."""
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and not _should_skip(path):
            yield path


def _snapshot_db_to(dest: Path) -> None:
    """Chụp snapshot DB nhất quán bằng sqlite3 backup API."""
    db_path = Path(str(settings.db_path))
    if not db_path.exists():
        raise FileNotFoundError(f"Không tìm thấy database: {db_path}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as src_conn, sqlite3.connect(str(dest)) as dst_conn:
        src_conn.backup(dst_conn)
    log.info("Đã snapshot database (%s bytes).", dest.stat().st_size)


def _collect_plan() -> list[tuple[str, Path | None, str]]:
    """Kế hoạch backup: (arcname, đường dẫn nguồn | None, nhóm).

    Nguồn None nghĩa là file sẽ được sinh ra lúc backup (ví dụ snapshot DB).
    """
    ensure_dirs()
    media_dir = Path(str(settings.media_dir or MEDIA_DIR))
    recordings_dir = Path(str(settings.recordings_dir or RECORDINGS_DIR))
    plan: list[tuple[str, Path | None, str]] = []

    db_path = Path(str(settings.db_path))
    if db_path.exists():
        plan.append((f"database/{db_path.name}", None, "database"))

    for src in _iter_tree_files(media_dir):
        plan.append((f"media/{src.relative_to(media_dir).as_posix()}", src, "media"))
    for src in _iter_tree_files(recordings_dir):
        plan.append(
            (f"recordings/{src.relative_to(recordings_dir).as_posix()}", src, "recordings")
        )

    if CONFIG_DIR.exists():
        for src in _iter_tree_files(CONFIG_DIR):
            if _is_sensitive_filename(src.name):
                continue  # không đưa file secret vào backup
            plan.append(
                (f"config/{src.relative_to(CONFIG_DIR).as_posix()}", src, "config")
            )

    if RECOVERY_DIR.exists():
        for point_dir in sorted(RECOVERY_DIR.iterdir()):
            meta = point_dir / "meta.json"
            if point_dir.is_dir() and meta.is_file():
                plan.append(
                    (f"recovery/{point_dir.name}/meta.json", meta, "recovery")
                )

    if TRASH_DIR.exists():
        for item_dir in sorted(TRASH_DIR.iterdir()):
            meta = item_dir / "meta.json"
            if item_dir.is_dir() and meta.is_file():
                plan.append((f"trash/{item_dir.name}/meta.json", meta, "trash"))

    return plan


def _stage_config_file(src: Path, staging: Path) -> Path:
    """Chuẩn bị file config vào staging: redact secret trong JSON."""
    staged = staging / src.name
    if src.suffix.lower() == ".json":
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
            staged.write_text(
                json.dumps(_redact_json(data), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return staged
        except (OSError, ValueError):
            pass  # không parse được thì copy nguyên
    shutil.copy2(src, staged)
    return staged


def create_backup(ghi_chu: str = "") -> dict:
    """Tạo file backup .zip trong BACKUP_DIR.

    Trả về ``{"ok": True, "backup_path": ..., "manifest": {...},
    "file_count": n, "total_bytes": n}``.
    """
    ensure_dirs()
    backup_dir = Path(str(settings.backup_dir or BACKUP_DIR))
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now()
    zip_name = f"hanngu-backup-{timestamp:%Y%m%d-%H%M%S}.zip"
    zip_path = backup_dir / zip_name
    if zip_path.exists():  # trùng giây → thêm microsecond
        zip_path = backup_dir / f"hanngu-backup-{timestamp:%Y%m%d-%H%M%S-%f}.zip"

    plan = _collect_plan()
    entries: list[dict] = []
    total_bytes = 0

    with tempfile.TemporaryDirectory(prefix="hanngu-backup-") as tmp:
        staging = Path(tmp)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for arcname, src, group in plan:
                if group == "database":
                    staged_db = staging / "hanngu.db.snapshot"
                    _snapshot_db_to(staged_db)
                    data_path = staged_db
                elif group == "config":
                    assert src is not None
                    data_path = _stage_config_file(src, staging)
                else:
                    assert src is not None
                    data_path = src
                zf.write(data_path, arcname)
                size = data_path.stat().st_size
                entries.append(
                    {"path": arcname, "sha256": _sha256(data_path), "size": size,
                     "group": group}
                )
                total_bytes += size

            manifest = {
                "version": MANIFEST_VERSION,
                "timestamp": timestamp.isoformat(timespec="seconds"),
                "app_version": _APP_VERSION,
                "ghi_chu": ghi_chu,
                "files": entries,
            }
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            manifest_entry = {
                "path": "manifest.json",
                "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "size": len(manifest_bytes),
                "group": "manifest",
            }
            manifest["files"].append(manifest_entry)
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            zf.writestr("manifest.json", manifest_bytes)

    log.info("Đã tạo backup: %s (%d file, %d bytes).", zip_path, len(entries), total_bytes)
    return {
        "ok": True,
        "backup_path": str(zip_path),
        "manifest": manifest,
        "file_count": len(entries),
        "total_bytes": total_bytes,
    }


def plan_backup() -> dict:
    """Liệt kê những gì sẽ được backup (không tạo file). Dùng cho --dry-run."""
    plan = _collect_plan()
    items = []
    total = 0
    for arcname, src, group in plan:
        size = src.stat().st_size if src is not None and src.exists() else 0
        if group == "database":
            db_path = Path(str(settings.db_path))
            size = db_path.stat().st_size if db_path.exists() else 0
        items.append({"path": arcname, "group": group, "size": size})
        total += size
    return {"ok": True, "data": {"files": items, "file_count": len(items),
                                 "total_bytes": total}}


def _read_manifest(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            raw = zf.read("manifest.json")
        except KeyError:
            raise ValueError("File zip không có manifest.json — không phải backup hợp lệ.")
    manifest = json.loads(raw.decode("utf-8"))
    if not isinstance(manifest, dict) or "files" not in manifest:
        raise ValueError("manifest.json không đúng định dạng.")
    return manifest


def _validate_archive(zip_path: Path, manifest: dict) -> tuple[list[dict], list[str]]:
    """Kiểm tra sha256 từng file trong manifest. Trả về (hợp lệ, lỗi)."""
    ok_entries: list[dict] = []
    errors: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        for entry in manifest["files"]:
            arcname = entry.get("path", "")
            if arcname == "manifest.json":
                continue
            if arcname not in names:
                errors.append(f"Thiếu file trong zip: {arcname}")
                continue
            with zf.open(arcname) as fh:
                digest = hashlib.sha256()
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != entry.get("sha256"):
                errors.append(f"Sai checksum (sha256) ở file: {arcname}")
            else:
                ok_entries.append(entry)
    return ok_entries, errors


def _restore_target(arcname: str) -> Path | None:
    """Ánh xạ arcname trong zip về đường dẫn đích trên máy hiện tại."""
    parts = Path(arcname).parts
    if not parts or parts[0] == "manifest.json" or ".." in parts:
        return None
    group, rel = parts[0], Path(*parts[1:])
    db_path = Path(str(settings.db_path))
    media_dir = Path(str(settings.media_dir or MEDIA_DIR))
    recordings_dir = Path(str(settings.recordings_dir or RECORDINGS_DIR))
    mapping = {
        "database": db_path.parent,
        "media": media_dir,
        "recordings": recordings_dir,
        "config": CONFIG_DIR,
        "recovery": RECOVERY_DIR,
        "trash": TRASH_DIR,
    }
    base = mapping.get(group)
    if base is None:
        return None
    if group == "database":
        return db_path  # luôn ghi về đúng db_path hiện tại
    return base / rel


def _config_restore_blocked(arcname: str, zf: zipfile.ZipFile) -> str | None:
    """Trả về lý do chặn restore file config, hoặc None nếu được phép.

    - Giữ nguyên .env / file tên nhạy cảm hiện tại (không ghi đè secret).
    - File JSON config chứa secret CHƯA redact → bỏ qua để an toàn.
    """
    parts = Path(arcname).parts
    if not parts or parts[0] != "config":
        return None
    if _is_sensitive_filename(Path(arcname).name):
        return "giữ nguyên file secret hiện tại"
    if arcname.lower().endswith(".json"):
        try:
            data = json.loads(zf.read(arcname).decode("utf-8"))

            def _has_real_secret(obj) -> bool:
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if _is_sensitive_key(key) and value not in (REDACTED_MARKER, None, ""):
                            return True
                        if _has_real_secret(value):
                            return True
                elif isinstance(obj, list):
                    return any(_has_real_secret(item) for item in obj)
                return False

            if _has_real_secret(data):
                return "file config chứa secret chưa redact"
        except (ValueError, KeyError, zipfile.BadZipFile):
            return None
    return None


def restore_backup(backup_path: str | Path, dry_run: bool = False) -> dict:
    """Khôi phục từ file backup.

    - (1) Tạo recovery point trước khi ghi (chỉ khi restore thật).
    - (2) Validate manifest + sha256 từng file.
    - (3) ``dry_run=True``: chỉ liệt kê file sẽ ghi đè, không ghi gì cả.
    - (4) Restore thật: giải nén đè; giữ .env hiện tại, không ghi đè secret.
    """
    zip_path = Path(backup_path)
    if not zip_path.is_file():
        return {"ok": False, "error_vi": f"Không tìm thấy file backup: {zip_path}"}
    if not zipfile.is_zipfile(zip_path):
        return {"ok": False, "error_vi": "File không phải định dạng zip hợp lệ."}

    try:
        manifest = _read_manifest(zip_path)
    except (ValueError, OSError) as exc:
        return {"ok": False, "error_vi": f"Manifest không hợp lệ: {exc}"}

    if str(manifest.get("version")) != MANIFEST_VERSION:
        return {"ok": False,
                "error_vi": f"Phiên bản manifest không hỗ trợ: {manifest.get('version')}"}

    ok_entries, errors = _validate_archive(zip_path, manifest)
    if errors:
        return {"ok": False, "error_vi": "Backup không toàn vẹn: " + "; ".join(errors[:5]),
                "data": {"loi": errors}}

    # Lập danh sách file sẽ ghi đè.
    se_ghi_de: list[dict] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for entry in ok_entries:
            target = _restore_target(entry["path"])
            if target is None:
                continue
            block_reason = _config_restore_blocked(entry["path"], zf)
            se_ghi_de.append({
                "trong_zip": entry["path"],
                "dich": str(target),
                "size": entry.get("size", 0),
                "da_ton_tai": target.exists(),
                "bi_chan": block_reason,
            })

    if dry_run:
        return {"ok": True, "dry_run": True,
                "data": {"da_validate": len(ok_entries), "se_ghi_de": se_ghi_de,
                         "ghi_chu": "Chế độ thử (dry-run): chưa ghi file nào."}}

    # (1) Tạo recovery point trước khi restore thật.
    from app.recovery import create_recovery_point
    recovery_point = create_recovery_point("truoc-khi-phuc-hoi-backup")

    da_khoi_phuc = 0
    bi_bo_qua: list[dict] = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for item in se_ghi_de:
                if item["bi_chan"]:
                    bi_bo_qua.append({"file": item["trong_zip"], "ly_do": item["bi_chan"]})
                    continue
                target = Path(item["dich"])
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(item["trong_zip"]) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                da_khoi_phuc += 1
    except OSError as exc:
        log.error("Restore backup thất bại giữa chừng: %s", exc)
        return {"ok": False,
                "error_vi": f"Khôi phục thất bại giữa chừng: {exc}. "
                            f"Recovery point đã tạo tại: {recovery_point}",
                "data": {"recovery_point": recovery_point,
                         "da_khoi_phuc": da_khoi_phuc, "bi_bo_qua": bi_bo_qua}}

    log.info("Đã khôi phục backup %s (%d file).", zip_path, da_khoi_phuc)
    return {"ok": True, "dry_run": False,
            "data": {"da_validate": len(ok_entries), "da_khoi_phuc": da_khoi_phuc,
                     "bi_bo_qua": bi_bo_qua, "recovery_point": recovery_point}}


def list_backups() -> list[dict]:
    """Liệt kê các file backup trong BACKUP_DIR, mới nhất trước."""
    ensure_dirs()
    backup_dir = Path(str(settings.backup_dir or BACKUP_DIR))
    results: list[dict] = []
    if not backup_dir.exists():
        return results
    for zip_path in sorted(backup_dir.glob("hanngu-backup-*.zip"), reverse=True):
        info: dict = {
            "ten": zip_path.name,
            "duong_dan": str(zip_path),
            "kich_thuoc": zip_path.stat().st_size,
            "ngay_tao": datetime.fromtimestamp(
                zip_path.stat().st_mtime).isoformat(timespec="seconds"),
            "ghi_chu": "",
            "phien_ban": "",
            "so_file": None,
        }
        try:
            manifest = _read_manifest(zip_path)
            info["ghi_chu"] = manifest.get("ghi_chu", "")
            info["phien_ban"] = manifest.get("version", "")
            info["so_file"] = len([f for f in manifest.get("files", [])
                                    if f.get("path") != "manifest.json"])
            info["ngay_tao"] = manifest.get("timestamp", info["ngay_tao"])
        except (ValueError, OSError, zipfile.BadZipFile):
            info["ghi_chu"] = "(không đọc được manifest)"
        results.append(info)
    return results
