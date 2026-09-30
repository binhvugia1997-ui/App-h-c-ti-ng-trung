"""Recovery point: snapshot nhẹ (database + config an toàn) để quay lui nhanh.

Mỗi recovery point là một thư mục::

    DATA_DIR/recovery/recovery-YYYYMMDD-HHMMSS-<ly-do-rut-gon>/
        hanngu.db            (copy database tại thời điểm chụp)
        config/...           (config đã redact secret)
        meta.json            {name, ly_do, created_at, app_version, files}

Sử dụng::

    from app.recovery import (
        create_recovery_point, list_recovery_points,
        restore_recovery_point, cleanup_retention,
    )
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from app import __version__ as _APP_VERSION
from app.backup.backup import _is_sensitive_filename, _redact_json, _should_skip
from app.config import settings
from app.logging_config import get_logger
from app.paths import CONFIG_DIR, RECOVERY_DIR, ensure_dirs

log = get_logger(__name__)

_NAME_RE = re.compile(r"^recovery-\d{8}-\d{6}-[a-z0-9-]{1,60}$")


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    slug = slug.strip("-") or "khong-ly-do"
    return slug[:60]


def _valid_point_name(name: str) -> bool:
    """Chống path traversal: tên point phải đúng định dạng sinh ra."""
    return bool(_NAME_RE.match(name))


def create_recovery_point(ly_do: str) -> str:
    """Chụp snapshot nhẹ (DB + config) vào RECOVERY_DIR. Trả về đường dẫn (str)."""
    ensure_dirs()
    RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
    name = f"recovery-{datetime.now():%Y%m%d-%H%M%S}-{_slug(ly_do)}"
    dest = RECOVERY_DIR / name
    if dest.exists():  # trùng giây → thêm hậu tố
        dest = RECOVERY_DIR / f"{name}-{datetime.now():%f}"
        name = dest.name
    dest.mkdir(parents=True)

    files: list[str] = []
    db_path = Path(str(settings.db_path))
    if db_path.exists():
        shutil.copy2(db_path, dest / db_path.name)
        files.append(db_path.name)
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = db_path.parent / f"{db_path.name}{suffix}"
            if sidecar.exists():
                shutil.copy2(sidecar, dest / sidecar.name)
                files.append(sidecar.name)

    if CONFIG_DIR.exists():
        for src in sorted(CONFIG_DIR.rglob("*")):
            if not src.is_file() or _should_skip(src):
                continue
            if _is_sensitive_filename(src.name):
                continue
            rel = src.relative_to(CONFIG_DIR)
            target = dest / "config" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix.lower() == ".json":
                try:
                    data = json.loads(src.read_text(encoding="utf-8"))
                    target.write_text(
                        json.dumps(_redact_json(data), ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    files.append(f"config/{rel.as_posix()}")
                    continue
                except (OSError, ValueError):
                    pass
            shutil.copy2(src, target)
            files.append(f"config/{rel.as_posix()}")

    meta = {
        "name": name,
        "ly_do": ly_do,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "app_version": _APP_VERSION,
        "db_path": str(db_path),
        "files": files,
    }
    (dest / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("Đã tạo recovery point: %s (%d file).", name, len(files))
    return str(dest)


def list_recovery_points() -> list[dict]:
    """Liệt kê các recovery point, mới nhất trước."""
    ensure_dirs()
    results: list[dict] = []
    if not RECOVERY_DIR.exists():
        return results
    for point_dir in sorted(RECOVERY_DIR.iterdir(), reverse=True):
        if not point_dir.is_dir() or not _valid_point_name(point_dir.name):
            continue
        meta_path = point_dir / "meta.json"
        info: dict = {
            "name": point_dir.name,
            "duong_dan": str(point_dir),
            "ly_do": "",
            "created_at": "",
            "so_file": 0,
        }
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            info["ly_do"] = meta.get("ly_do", "")
            info["created_at"] = meta.get("created_at", "")
            info["so_file"] = len(meta.get("files", []))
        except (OSError, ValueError):
            info["ly_do"] = "(không đọc được meta.json)"
        results.append(info)
    return results


def _restore_plan(point_dir: Path) -> tuple[list[dict], Path | None]:
    """Lập kế hoạch restore: (danh sách file sẽ ghi, file db snapshot)."""
    meta = json.loads((point_dir / "meta.json").read_text(encoding="utf-8"))
    items: list[dict] = []
    db_snapshot: Path | None = None
    db_name = Path(str(settings.db_path)).name
    for rel in meta.get("files", []):
        src = point_dir / rel
        if not src.is_file():
            continue
        if rel == db_name:
            # Chỉ restore file .db chính (snapshot nhất quán); bỏ qua sidecar
            # (-wal/-shm) để SQLite tự quản lý, tránh ghi đè trạng thái dở.
            db_snapshot = src
            items.append({"nguon": str(src), "dich": str(Path(str(settings.db_path))),
                          "loai": "database"})
        elif rel.startswith("config/"):
            target = CONFIG_DIR / Path(rel).relative_to("config")
            items.append({"nguon": str(src), "dich": str(target), "loai": "config"})
        else:
            items.append({"nguon": str(src), "dich": "", "loai": "khac",
                          "ghi_chu": "bỏ qua (chỉ khôi phục database + config)"})
    return items, db_snapshot


def restore_recovery_point(name: str, dry_run: bool = False) -> dict:
    """Khôi phục database + config từ một recovery point.

    Luôn chụp recovery point của trạng thái hiện tại trước khi ghi
    (chỉ khi restore thật). ``dry_run=True`` chỉ liệt kê, không ghi.
    """
    if not _valid_point_name(name):
        return {"ok": False, "error_vi": f"Tên recovery point không hợp lệ: {name}"}
    point_dir = RECOVERY_DIR / name
    if not point_dir.is_dir():
        return {"ok": False, "error_vi": f"Không tìm thấy recovery point: {name}"}
    if not (point_dir / "meta.json").is_file():
        return {"ok": False, "error_vi": "Recovery point thiếu meta.json."}

    try:
        items, db_snapshot = _restore_plan(point_dir)
    except (OSError, ValueError) as exc:
        return {"ok": False, "error_vi": f"Không đọc được meta.json: {exc}"}

    se_khoi_phuc = [it for it in items if it["loai"] in ("database", "config")]
    if dry_run:
        return {"ok": True, "dry_run": True,
                "data": {"point": name, "se_khoi_phuc": se_khoi_phuc,
                         "ghi_chu": "Chế độ thử (dry-run): chưa ghi file nào."}}

    safety_point = create_recovery_point(f"truoc-khi-khoi-phuc-{name}")
    da_khoi_phuc = 0
    try:
        for item in se_khoi_phuc:
            src, target = Path(item["nguon"]), Path(item["dich"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            da_khoi_phuc += 1
    except OSError as exc:
        log.error("Restore recovery point thất bại: %s", exc)
        return {"ok": False,
                "error_vi": f"Khôi phục thất bại giữa chừng: {exc}. "
                            f"Điểm an toàn đã tạo tại: {safety_point}",
                "data": {"safety_point": safety_point, "da_khoi_phuc": da_khoi_phuc}}

    log.info("Đã khôi phục recovery point %s (%d file).", name, da_khoi_phuc)
    return {"ok": True, "dry_run": False,
            "data": {"point": name, "da_khoi_phuc": da_khoi_phuc,
                     "safety_point": safety_point}}


def cleanup_retention(giu_lai: int = 10) -> dict:
    """Xóa các recovery point cũ nhất, chỉ giữ lại ``giu_lai`` point mới nhất."""
    if giu_lai < 1:
        return {"ok": False, "error_vi": "Số lượng giữ lại phải >= 1."}
    points = list_recovery_points()  # đã sắp mới nhất trước
    to_delete = points[giu_lai:]
    deleted: list[str] = []
    for info in to_delete:
        try:
            shutil.rmtree(info["duong_dan"])
            deleted.append(info["name"])
        except OSError as exc:
            log.error("Không xóa được recovery point %s: %s", info["name"], exc)
    log.info("Retention: giữ %d, đã xóa %d recovery point.", giu_lai, len(deleted))
    return {"ok": True, "data": {"giu_lai": giu_lai, "da_xoa": deleted,
                                 "con_lai": len(points) - len(deleted)}}
