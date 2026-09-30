"""Export migration: tạo gói di chuyển (thư mục) từ máy cũ sang máy mới.

Cấu trúc gói ``hanngu-migration-YYYYMMDD-HHMMSS/``::

    manifest.json      {migration_version, exported_at,
                        source: {old_app_root: "<REDACTED-PORTABLE>"},
                        groups: {...}}
    db/hanngu.db       snapshot database (sqlite backup API)
    learning/tables/<table>.json   dữ liệu học tập theo từng bảng (có schema)
    media/...          file media (đường dẫn tương đối)
    recordings/...     file ghi âm (đường dẫn tương đối)
    config/...         config AN TOÀN (secret → "REAUTH REQUIRED")
    models/models_manifest.json    chỉ manifest model (không copy model lớn)
    qwen.json          {base_url, model} — không chứa secret

Nguyên tắc an toàn:
- KHÔNG ghi absolute path của máy cũ vào dữ liệu (remap → "<APP_ROOT>").
- Secret (access_token, refresh_token, password, secret, api_key...)
  bị redact thành "REAUTH REQUIRED".
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app import __version__ as _APP_VERSION
from app.backup.backup import (
    _is_sensitive_filename,
    _is_sensitive_key,
    _should_skip,
)
from app.config import settings
from app.db.database import get_conn
from app.logging_config import get_logger
from app.paths import (
    APP_ROOT,
    CONFIG_DIR,
    DATA_DIR,
    MEDIA_DIR,
    MODEL_DIR,
    RECORDINGS_DIR,
    ensure_dirs,
)

log = get_logger(__name__)

MIGRATION_VERSION = "1.0"
APP_ROOT_PLACEHOLDER = "<APP_ROOT>"
REDACTED_SECRET = "REAUTH REQUIRED"

# Dấu vết đường dẫn tuyệt đối của máy cũ cần quét & remap.
OLD_ROOT_HINTS = ("D:\\HanNguServer", "D:/HanNguServer")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remap_value(value):
    """Remap absolute path máy cũ → placeholder tương đối, đệ quy."""
    if isinstance(value, str):
        out = value
        app_root = str(APP_ROOT)
        if app_root and app_root in out:
            out = out.replace(app_root, APP_ROOT_PLACEHOLDER)
        for hint in OLD_ROOT_HINTS:
            if hint in out:
                out = out.replace(hint, APP_ROOT_PLACEHOLDER)
        return out
    if isinstance(value, dict):
        return {key: _remap_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_remap_value(item) for item in value]
    return value


def _redact_config(obj):
    """Redact secret trong config → 'REAUTH REQUIRED', đệ quy."""
    if isinstance(obj, dict):
        return {
            key: (REDACTED_SECRET if _is_sensitive_key(key) else _redact_config(value))
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_config(item) for item in obj]
    return obj


def _user_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [row["name"] for row in rows]


def _copy_tree_relative(src_root: Path, dest_root: Path,
                        dry_run: bool = False) -> list[dict]:
    """Copy cây thư mục, trả về danh sách file {path(tương đối), size, sha256}."""
    files: list[dict] = []
    if not src_root.exists():
        return files
    for src in sorted(src_root.rglob("*")):
        if not src.is_file() or _should_skip(src):
            continue
        rel = src.relative_to(src_root).as_posix()
        if not dry_run:
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        files.append({"path": rel, "size": src.stat().st_size,
                      "sha256": _sha256(src)})
    return files


def create_export_package(dich: str | Path | None = None,
                          dry_run: bool = False) -> dict:
    """Tạo gói migration tại ``dich``. ``dry_run=True``: chỉ lập kế hoạch."""
    ensure_dirs()
    base = Path(dich) if dich else DATA_DIR / "migration-exports"
    timestamp = datetime.now()
    package_dir = base / f"hanngu-migration-{timestamp:%Y%m%d-%H%M%S}"
    if not dry_run:
        package_dir.mkdir(parents=True, exist_ok=True)

    media_dir = Path(str(settings.media_dir or MEDIA_DIR))
    recordings_dir = Path(str(settings.recordings_dir or RECORDINGS_DIR))
    db_path = Path(str(settings.db_path))

    groups: dict = {}
    exported_at = timestamp.isoformat(timespec="seconds")

    # --- 1. Database snapshot ---
    db_info: dict = {"trang_thai": "bo_qua", "ly_do": "không tìm thấy database"}
    if db_path.exists():
        try:
            with get_conn() as src_conn:
                tables = _user_tables(src_conn)
                rows_total = sum(
                    src_conn.execute(
                        f'SELECT COUNT(*) AS n FROM "{t}"').fetchone()["n"]
                    for t in tables
                )
                if not dry_run:
                    dest_db = package_dir / "db" / db_path.name
                    dest_db.parent.mkdir(parents=True, exist_ok=True)
                    with sqlite3.connect(str(dest_db)) as dst_conn:
                        src_conn.backup(dst_conn)
            db_info = {"trang_thai": "ok", "file": f"db/{db_path.name}",
                       "bang": tables, "tong_dong": rows_total}
        except Exception as exc:  # noqa: BLE001
            db_info = {"trang_thai": "loi", "ly_do": str(exc)}
            log.error("Export DB snapshot thất bại: %s", exc)
    groups["db"] = db_info

    # --- 2. Learning data: từng bảng → JSON (có schema, đã remap path) ---
    learning_info: dict = {"trang_thai": "bo_qua", "bang": []}
    if db_path.exists() and db_info.get("trang_thai") == "ok":
        try:
            with get_conn() as conn:
                tables = _user_tables(conn)
                exported_tables = []
                for table in tables:
                    schema_row = conn.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)).fetchone()
                    rows = [_remap_value(dict(row))
                            for row in conn.execute(f'SELECT * FROM "{table}"')]
                    payload = {"table": table,
                               "schema": schema_row["sql"] if schema_row else "",
                               "rows": rows, "so_dong": len(rows)}
                    if not dry_run:
                        out = package_dir / "learning" / "tables" / f"{table}.json"
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
                    exported_tables.append({"table": table, "so_dong": len(rows)})
            learning_info = {"trang_thai": "ok", "bang": exported_tables,
                             "tong_bang": len(exported_tables)}
        except Exception as exc:  # noqa: BLE001
            learning_info = {"trang_thai": "loi", "ly_do": str(exc)}
            log.error("Export learning data thất bại: %s", exc)
    groups["learning"] = learning_info

    # --- 3 & 4. Media + recordings ---
    media_files = _copy_tree_relative(media_dir, package_dir / "media", dry_run)
    groups["media"] = {"trang_thai": "ok", "so_file": len(media_files),
                       "tong_dung_luong": sum(f["size"] for f in media_files),
                       "files": media_files}
    rec_files = _copy_tree_relative(recordings_dir, package_dir / "recordings", dry_run)
    groups["recordings"] = {"trang_thai": "ok", "so_file": len(rec_files),
                            "tong_dung_luong": sum(f["size"] for f in rec_files),
                            "files": rec_files}

    # --- 5. Config an toàn (redact secret) ---
    config_files: list[dict] = []
    redacted_keys: list[str] = []
    bo_qua_secret: list[str] = []
    if CONFIG_DIR.exists():
        for src in sorted(CONFIG_DIR.rglob("*")):
            if not src.is_file() or _should_skip(src):
                continue
            rel = src.relative_to(CONFIG_DIR).as_posix()
            if _is_sensitive_filename(src.name):
                bo_qua_secret.append(rel)
                continue
            if not dry_run:
                dest = package_dir / "config" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src.suffix.lower() == ".json":
                    try:
                        data = json.loads(src.read_text(encoding="utf-8"))

                        def _collect_keys(obj, prefix=""):
                            if isinstance(obj, dict):
                                for key, value in obj.items():
                                    if _is_sensitive_key(key):
                                        redacted_keys.append(f"{rel}:{prefix}{key}")
                                    _collect_keys(value, f"{prefix}{key}.")
                            elif isinstance(obj, list):
                                for item in obj:
                                    _collect_keys(item, prefix)
                        _collect_keys(data)
                        dest.write_text(json.dumps(_redact_config(data),
                                                  ensure_ascii=False, indent=2),
                                        encoding="utf-8")
                        config_files.append({"path": rel, "size": dest.stat().st_size})
                        continue
                    except (OSError, ValueError):
                        pass
                shutil.copy2(src, dest)
                config_files.append({"path": rel, "size": dest.stat().st_size})
    groups["config"] = {"trang_thai": "ok", "so_file": len(config_files),
                        "files": config_files,
                        "khoa_da_redact": sorted(set(redacted_keys)),
                        "file_secret_da_bo_qua": bo_qua_secret}

    # --- 6. Models: chỉ manifest, không copy model lớn ---
    model_files: list[dict] = []
    if MODEL_DIR.exists():
        for src in sorted(MODEL_DIR.rglob("*")):
            if not src.is_file() or _should_skip(src):
                continue
            model_files.append({"path": src.relative_to(MODEL_DIR).as_posix(),
                                "size": src.stat().st_size, "sha256": _sha256(src)})
    if not dry_run:
        out = package_dir / "models" / "models_manifest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"models": model_files,
                                   "ghi_chu": "Chỉ manifest, không copy model lớn. "
                                              "Tải/cài lại model trên máy mới."},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    groups["models"] = {"trang_thai": "ok", "so_model": len(model_files),
                        "che_do": "chi-manifest", "models": model_files}

    # --- 7. Qwen config (url + model, không secret) ---
    qwen_cfg = {"base_url": getattr(settings, "qwen_base_url", ""),
                "model": getattr(settings, "qwen_model", "")}
    if not dry_run:
        (package_dir / "qwen.json").write_text(
            json.dumps(qwen_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    groups["qwen"] = {"trang_thai": "ok", "cau_hinh": qwen_cfg}

    manifest = {
        "migration_version": MIGRATION_VERSION,
        "exported_at": exported_at,
        "app_version": _APP_VERSION,
        "source": {"old_app_root": "<REDACTED-PORTABLE>",
                   "ghi_chu": "Đường dẫn tuyệt đối máy cũ đã được remap tương đối."},
        "groups": groups,
        "dry_run": dry_run,
    }
    if not dry_run:
        (package_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["package_path"] = str(package_dir)
        log.info("Đã tạo gói migration: %s.", package_dir)
    return manifest
