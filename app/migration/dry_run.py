"""Dry-run migration: dùng chung logic export/import với dry_run=True.

- ``ke_hoach_export(dich)``: liệt kê file sẽ copy, dung lượng ước tính.
- ``ke_hoach_import(package_path)``: liệt kê file sẽ copy, path sẽ remap,
  dependency thiếu, việc cần làm thủ công (external setup).
- ``bao_cao_dry_run(...)``: gộp cả hai thành một báo cáo tiếng Việt.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.config import settings
from app.logging_config import get_logger
from app.migration.export import create_export_package
from app.migration.import_ import import_package
from app.migration.verify import _check_dependencies, _check_ffmpeg, _check_qwen

log = get_logger(__name__)


def ke_hoach_export(dich: str | Path | None = None) -> dict:
    """Kế hoạch export (không ghi file nào)."""
    manifest = create_export_package(dich, dry_run=True)
    groups = manifest.get("groups", {})
    tong_file, tong_bytes = 0, 0
    for name in ("media", "recordings"):
        files = groups.get(name, {}).get("files", [])
        tong_file += len(files)
        tong_bytes += sum(f.get("size", 0) for f in files)
    return {"ok": True,
            "data": {"che_do": "dry-run export",
                     "se_copy_file": tong_file,
                     "tong_dung_luong_uoc_tinh": tong_bytes,
                     "nhom": {name: {"trang_thai": info.get("trang_thai"),
                                     "so_file": info.get("so_file",
                                                         len(info.get("files", [])))}
                              for name, info in groups.items()},
                     "manifest": manifest}}


def ke_hoach_import(package_path: str | Path) -> dict:
    """Kế hoạch import (không ghi file nào) + việc cần làm thủ công."""
    report = import_package(package_path, dry_run=True)

    # Dependency thiếu (kiểm tra thật).
    deps = _check_dependencies()
    thieu_dep = [c.split(":")[0] for c in deps.get("muc_kiem_tra", [])
                 if "THIẾU" in c]

    # Việc cần làm thủ công bên ngoài.
    can_thiet_lap: list[str] = []
    ffmpeg = _check_ffmpeg()
    if ffmpeg["trang_thai"] != "PASS":
        can_thiet_lap.append("Cài đặt ffmpeg và đảm bảo có trong PATH "
                             "(cần cho xử lý video/audio).")
    qwen = _check_qwen()
    if qwen["trang_thai"] == "FAIL":
        can_thiet_lap.append("Cài/khởi động Ollama và pull model Qwen "
                             f"({settings.qwen_model}) nếu muốn dùng AI.")
    elif qwen["trang_thai"] == "NOT_TESTED":
        can_thiet_lap.append("Kiểm tra lại kết nối Qwen/Ollama sau khi "
                             "module qwen sẵn sàng.")
    # Secret đã redact → cần đăng nhập lại.
    try:
        manifest_files = None
        pkg = Path(package_path)
        manifest_path = pkg / "manifest.json" if pkg.is_dir() else None
        if manifest_path and manifest_path.is_file():
            import json as _json
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
            redacted = (manifest.get("groups", {}).get("config", {})
                        .get("khoa_da_redact", []))
            if redacted:
                can_thiet_lap.append(
                    f"Đăng nhập lại các tài khoản/dịch vụ ({len(redacted)} khóa "
                    "đã redact thành 'REAUTH REQUIRED').")
    except (OSError, ValueError):
        pass
    can_thiet_lap.append("Tải/cài lại model AI trên máy mới "
                         "(gói migration chỉ mang manifest model).")
    can_thiet_lap.append("Kiểm tra quyền ghi vào thư mục dữ liệu mới.")

    report["thieu_dependency"] = thieu_dep
    report["can_thiet_lap_thu_cong"] = can_thiet_lap
    return report


def bao_cao_dry_run(package_path: str | Path | None = None,
                    dich: str | Path | None = None) -> dict:
    """Báo cáo dry-run tổng hợp: export plan và/hoặc import plan."""
    data: dict = {"che_do": "dry-run"}
    if dich or package_path is None:
        data["export"] = ke_hoach_export(dich).get("data", {})
    if package_path:
        data["import"] = ke_hoach_import(package_path)
    return {"ok": True, "data": data}
