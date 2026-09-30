"""Import migration: nhập gói migration vào máy mới.

Quy trình từng bước (mỗi bước ghi vào báo cáo):
  1. validate: manifest tồn tại, đúng migration_version, sha256 file media/recordings.
  2. tạo recovery point (trừ dry-run).
  3. import dữ liệu: db snapshot → settings.db_path (fallback: learning JSON),
     media/recordings → thư mục mới, config an toàn (không đè secret).
  4. remap "<APP_ROOT>" trong dữ liệu text → APP_ROOT mới.
  5. verify DB: mở được, đủ bảng so với manifest.
Thất bại giữa chừng → thử rollback từ recovery point (ghi rõ kết quả).
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

from app.config import settings
from app.logging_config import get_logger
from app.migration.export import (
    APP_ROOT_PLACEHOLDER,
    MIGRATION_VERSION,
    _is_sensitive_filename,
)
from app.paths import (
    APP_ROOT,
    CONFIG_DIR,
    MEDIA_DIR,
    RECORDINGS_DIR,
    ensure_dirs,
)
from app.recovery import create_recovery_point, restore_recovery_point

log = get_logger(__name__)


def _step(steps: list, buoc: str, trang_thai: str, chi_tiet: str = "") -> None:
    steps.append({"buoc": buoc, "trang_thai": trang_thai, "chi_tiet": chi_tiet})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_package(package_path: str | Path) -> tuple[Path, Path | None]:
    """Trả về (thư mục gói, thư mục tạm cần dọn | None).

    Chấp nhận thư mục gói hoặc file .zip chứa gói.
    """
    pkg = Path(package_path)
    if pkg.is_dir():
        return pkg, None
    if pkg.is_file() and zipfile.is_zipfile(pkg):
        tmp = Path(tempfile.mkdtemp(prefix="hanngu-import-"))
        with zipfile.ZipFile(pkg, "r") as zf:
            for member in zf.namelist():
                parts = Path(member).parts
                if not parts or ".." in parts or Path(member).is_absolute():
                    raise ValueError(f"Zip chứa đường dẫn không an toàn: {member}")
            zf.extractall(tmp)
        # Gói có thể nằm ngay trong zip hoặc trong 1 thư mục con.
        candidates = [p for p in tmp.iterdir()
                      if p.is_dir() and (p / "manifest.json").is_file()]
        if (tmp / "manifest.json").is_file():
            return tmp, tmp
        if len(candidates) == 1:
            return candidates[0], tmp
        raise ValueError("File zip không chứa gói migration hợp lệ.")
    raise ValueError(f"Không tìm thấy gói migration: {package_path}")


def _validate_package(pkg_dir: Path) -> tuple[dict, list[str]]:
    """Đọc manifest + kiểm tra sha256 media/recordings. Trả về (manifest, lỗi)."""
    manifest_path = pkg_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Gói thiếu manifest.json.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if str(manifest.get("migration_version")) != MIGRATION_VERSION:
        raise ValueError(
            f"Phiên bản migration không hỗ trợ: {manifest.get('migration_version')}")
    errors: list[str] = []
    groups = manifest.get("groups", {})
    for group_name in ("media", "recordings"):
        for entry in groups.get(group_name, {}).get("files", []):
            fpath = pkg_dir / group_name / entry["path"]
            if not fpath.is_file():
                errors.append(f"Thiếu file {group_name}/{entry['path']}")
            elif _sha256(fpath) != entry.get("sha256"):
                errors.append(f"Sai checksum {group_name}/{entry['path']}")
    db_info = groups.get("db", {})
    if db_info.get("trang_thai") == "ok":
        db_file = pkg_dir / db_info.get("file", "")
        if not db_file.is_file():
            errors.append(f"Thiếu file database snapshot: {db_info.get('file')}")
    return manifest, errors


def _import_db(pkg_dir: Path, manifest: dict, dry_run: bool, steps: list) -> bool:
    """Nhập database: ưu tiên snapshot, fallback learning JSON. Trả về True nếu ok."""
    groups = manifest["groups"]
    db_info = groups.get("db", {})
    db_path = Path(str(settings.db_path))

    if db_info.get("trang_thai") == "ok":
        src = pkg_dir / db_info["file"]
        if dry_run:
            _step(steps, "nhap-database",
                  "skip", f"[dry-run] Sẽ copy {src.name} → {db_path}")
            return True
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, db_path)
        _step(steps, "nhap-database", "ok", f"Đã copy snapshot → {db_path.name}")
        return True

    # Fallback: dựng lại từ learning/tables/*.json
    tables_dir = pkg_dir / "learning" / "tables"
    if not tables_dir.is_dir():
        _step(steps, "nhap-database", "fail",
              "Không có db snapshot lẫn learning JSON.")
        return False
    if dry_run:
        n = len(list(tables_dir.glob("*.json")))
        _step(steps, "nhap-database", "skip",
              f"[dry-run] Sẽ dựng lại {n} bảng từ learning JSON.")
        return True
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            for payload_path in sorted(tables_dir.glob("*.json")):
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
                schema = payload.get("schema", "")
                if schema:
                    conn.execute(schema)
                table = payload["table"]
                rows = payload.get("rows", [])
                if rows:
                    cols = list(rows[0].keys())
                    placeholders = ", ".join(["?"] * len(cols))
                    conn.executemany(
                        f'INSERT OR REPLACE INTO "{table}" '
                        f'({", ".join(cols)}) VALUES ({placeholders})',
                        [[row.get(c) for c in cols] for row in rows],
                    )
            conn.commit()
        finally:
            conn.close()
        _step(steps, "nhap-database", "ok", "Đã dựng lại DB từ learning JSON.")
        return True
    except Exception as exc:  # noqa: BLE001
        _step(steps, "nhap-database", "fail", f"Lỗi dựng DB từ JSON: {exc}")
        return False


def _import_tree(pkg_dir: Path, group: str, dest_root: Path,
                 dry_run: bool, steps: list) -> None:
    src_root = pkg_dir / group
    entries = manifest_files_of(pkg_dir, group)
    if dry_run:
        _step(steps, f"nhap-{group}", "skip",
              f"[dry-run] Sẽ copy {len(entries)} file → {dest_root}")
        return
    copied = 0
    if src_root.is_dir():
        for src in sorted(src_root.rglob("*")):
            if src.is_file():
                rel = src.relative_to(src_root)
                if ".." in rel.parts:
                    continue
                dest = dest_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                copied += 1
    _step(steps, f"nhap-{group}", "ok", f"Đã copy {copied} file → {dest_root}")


def manifest_files_of(pkg_dir: Path, group: str) -> list[dict]:
    try:
        manifest = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
        return manifest.get("groups", {}).get(group, {}).get("files", [])
    except (OSError, ValueError):
        return []


def _import_config(pkg_dir: Path, dry_run: bool, steps: list) -> None:
    src_root = pkg_dir / "config"
    if not src_root.is_dir():
        _step(steps, "nhap-config", "skip", "Gói không có config.")
        return
    if dry_run:
        files = [p.relative_to(src_root).as_posix()
                 for p in sorted(src_root.rglob("*")) if p.is_file()]
        _step(steps, "nhap-config", "skip",
              f"[dry-run] Sẽ copy {len(files)} file config (không đè secret).")
        return
    copied, skipped = 0, 0
    for src in sorted(src_root.rglob("*")):
        if not src.is_file() or _is_sensitive_filename(src.name):
            if src.is_file():
                skipped += 1
            continue
        rel = src.relative_to(src_root)
        if ".." in rel.parts:
            continue
        dest = CONFIG_DIR / rel
        # Không ghi đè file secret hiện tại (vd .env của máy mới).
        if dest.exists() and _is_sensitive_filename(dest.name):
            skipped += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    _step(steps, "nhap-config", "ok",
          f"Đã copy {copied} file config, bỏ qua {skipped} file secret.")


def _remap_app_root_in_db(dry_run: bool, steps: list) -> None:
    """Thay '<APP_ROOT>' trong mọi cột TEXT → APP_ROOT mới."""
    if dry_run:
        _step(steps, "remap-duong-dan", "skip",
              "[dry-run] Sẽ thay '<APP_ROOT>' và dấu vết máy cũ → đường dẫn mới.")
        return
    db_path = Path(str(settings.db_path))
    if not db_path.exists():
        _step(steps, "remap-duong-dan", "skip", "Chưa có database.")
        return
    new_root = str(APP_ROOT)
    # Placeholder do export tạo ra + dấu vết tuyệt đối của máy cũ (Windows).
    thay_the = [(APP_ROOT_PLACEHOLDER, new_root),
                ("D:\\HanNguServer", new_root),
                ("D:/HanNguServer", new_root)]
    conn = sqlite3.connect(str(db_path))
    tables_fixed = 0
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'").fetchall()]
        for table in tables:
            info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            for col in info:
                col_type = str(col[2]).upper()
                if "TEXT" in col_type or "CHAR" in col_type or "CLOB" in col_type:
                    for cu, moi in thay_the:
                        cur = conn.execute(
                            f'UPDATE "{table}" SET "{col[1]}" = REPLACE("{col[1]}", ?, ?) '
                            f'WHERE "{col[1]}" LIKE ?',
                            (cu, moi, f"%{cu}%"))
                        if cur.rowcount:
                            tables_fixed += 1
        conn.commit()
    finally:
        conn.close()
    _step(steps, "remap-duong-dan", "ok",
          f"Đã remap '<APP_ROOT>' và dấu vết máy cũ → {new_root} "
          f"({tables_fixed} lượt cập nhật cột).")


def _verify_db(manifest: dict, steps: list) -> bool:
    db_path = Path(str(settings.db_path))
    if not db_path.exists():
        _step(steps, "verify-db", "fail", "Không tìm thấy database sau import.")
        return False
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'").fetchall()}
            conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        _step(steps, "verify-db", "fail", f"Không mở được database: {exc}")
        return False
    expected = set(manifest.get("groups", {}).get("db", {}).get("bang", []) or [])
    missing = sorted(expected - tables)
    if missing:
        _step(steps, "verify-db", "fail", f"Thiếu bảng: {', '.join(missing)}")
        return False
    _step(steps, "verify-db", "ok",
          f"DB mở được, đủ {len(tables)} bảng " +
          (f"(khớp {len(expected)} bảng trong manifest)." if expected else "."))
    return True


def import_package(package_path: str | Path, dry_run: bool = False) -> dict:
    """Nhập gói migration. Trả về báo cáo từng bước.

    Thất bại giữa chừng (không phải dry-run) → thử rollback từ recovery point.
    """
    ensure_dirs()
    steps: list[dict] = []
    tmp_dir: Path | None = None
    recovery_point: str | None = None
    da_rollback = False

    try:
        # B1: validate
        pkg_dir, tmp_dir = _resolve_package(package_path)
        try:
            manifest, errors = _validate_package(pkg_dir)
        except ValueError as exc:
            _step(steps, "validate", "fail", str(exc))
            return {"ok": False, "dry_run": dry_run, "steps": steps,
                    "error_vi": str(exc)}
        if errors:
            _step(steps, "validate", "fail", "; ".join(errors[:5]))
            return {"ok": False, "dry_run": dry_run, "steps": steps,
                    "error_vi": "Gói migration không toàn vẹn: " + "; ".join(errors[:5])}
        _step(steps, "validate", "ok",
              f"Manifest hợp lệ (migration_version={manifest.get('migration_version')}).")

        # B2: recovery point
        if dry_run:
            _step(steps, "recovery-point", "skip",
                  "[dry-run] Sẽ tạo recovery point trước khi ghi.")
        else:
            recovery_point = create_recovery_point("truoc-khi-nhap-migration")
            _step(steps, "recovery-point", "ok", f"Đã tạo: {recovery_point}")

        # B3: import dữ liệu
        media_dir = Path(str(settings.media_dir or MEDIA_DIR))
        recordings_dir = Path(str(settings.recordings_dir or RECORDINGS_DIR))
        if not _import_db(pkg_dir, manifest, dry_run, steps):
            raise RuntimeError("Import database thất bại.")
        _import_tree(pkg_dir, "media", media_dir, dry_run, steps)
        _import_tree(pkg_dir, "recordings", recordings_dir, dry_run, steps)
        _import_config(pkg_dir, dry_run, steps)

        # B4: remap đường dẫn
        _remap_app_root_in_db(dry_run, steps)

        # B5: verify
        if dry_run:
            _step(steps, "verify-db", "skip", "[dry-run] Sẽ kiểm tra DB sau khi ghi.")
            ok = True
        else:
            ok = _verify_db(manifest, steps)

        status = "ok" if ok else "fail"
        return {"ok": ok, "dry_run": dry_run, "steps": steps,
                "recovery_point": recovery_point, "da_rollback": da_rollback,
                **({} if ok else
                   {"error_vi": "Import thất bại ở bước verify-db, xem chi tiết từng bước."})}
    except Exception as exc:  # noqa: BLE001
        _step(steps, "import", "fail", f"Lỗi không mong đợi: {exc}")
        log.error("import_package thất bại: %s", exc)
        if not dry_run and recovery_point:
            try:
                name = Path(recovery_point).name
                rb = restore_recovery_point(name)
                da_rollback = bool(rb.get("ok"))
                _step(steps, "rollback", "ok" if da_rollback else "fail",
                      f"Rollback từ {name}: {'thành công' if da_rollback else 'THẤT BẠI'}")
            except Exception as rb_exc:  # noqa: BLE001
                _step(steps, "rollback", "fail", f"Rollback lỗi: {rb_exc}")
        return {"ok": False, "dry_run": dry_run, "steps": steps,
                "recovery_point": recovery_point, "da_rollback": da_rollback,
                "error_vi": f"Import thất bại: {exc}"}
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
