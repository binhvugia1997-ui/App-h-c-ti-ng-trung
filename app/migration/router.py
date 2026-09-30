"""Router /api/migration: export / import / verify / dry-run."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel

from app.logging_config import get_logger
from app.migration.dry_run import bao_cao_dry_run
from app.migration.export import create_export_package
from app.migration.import_ import import_package
from app.migration.verify import verify_installation
from app.paths import DATA_DIR

log = get_logger(__name__)

router = APIRouter(prefix="/api/migration")


class ExportBody(BaseModel):
    dich: str = ""  # thư mục đích; trống = data/migration-exports


class DryRunBody(BaseModel):
    package_path: str = ""  # đường dẫn gói migration (để thử import)
    dich: str = ""          # thư mục đích (để thử export)


@router.post("/export")
def api_export(body: ExportBody):
    """Xuất gói migration. Trả về đường dẫn gói + tóm tắt manifest."""
    try:
        manifest = create_export_package(body.dich or None)
        return {"ok": True,
                "data": {"package_path": manifest.get("package_path"),
                         "migration_version": manifest.get("migration_version"),
                         "exported_at": manifest.get("exported_at"),
                         "groups": {name: {"trang_thai": info.get("trang_thai")}
                                    for name, info in manifest.get("groups", {}).items()}}}
    except Exception as exc:  # noqa: BLE001
        log.error("POST /api/migration/export lỗi: %s", exc)
        return {"ok": False, "error_vi": f"Không xuất được gói migration: {exc}"}


@router.post("/import")
async def api_import(file: UploadFile = File(...),
                     dry_run: bool = Query(default=False)):
    """Nhập gói migration từ file .zip upload. ``?dry_run=true`` để thử."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="hanngu-migration-upload-"))
    try:
        zip_path = tmp_dir / (file.filename or "package.zip")
        with open(zip_path, "wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
        if not zipfile.is_zipfile(zip_path):
            return {"ok": False,
                    "error_vi": "File upload phải là .zip chứa gói migration."}
        report = import_package(zip_path, dry_run=dry_run)
        return report
    except Exception as exc:  # noqa: BLE001
        log.error("POST /api/migration/import lỗi: %s", exc)
        return {"ok": False, "error_vi": f"Không nhập được gói migration: {exc}"}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/verify")
def api_verify():
    """Kiểm chứng cài đặt sau migration (PASS/PARTIAL/FAIL/NOT_TESTED)."""
    try:
        return verify_installation()
    except Exception as exc:  # noqa: BLE001
        log.error("GET /api/migration/verify lỗi: %s", exc)
        return {"ok": False, "error_vi": "Không chạy được kiểm chứng, vui lòng thử lại."}


@router.post("/dry-run")
def api_dry_run(body: DryRunBody):
    """Chạy thử export/import: liệt kê việc sẽ làm, không ghi file nào."""
    try:
        if not body.package_path and not body.dich:
            return {"ok": False,
                    "error_vi": "Cần cung cấp package_path (thử import) "
                                "hoặc dich (thử export)."}
        dich = body.dich or None
        package = body.package_path or None
        if package and not Path(package).exists():
            return {"ok": False,
                    "error_vi": f"Không tìm thấy gói migration: {package}"}
        return bao_cao_dry_run(package_path=package, dich=dich)
    except Exception as exc:  # noqa: BLE001
        log.error("POST /api/migration/dry-run lỗi: %s", exc)
        return {"ok": False, "error_vi": f"Không chạy thử được: {exc}"}


# Thư mục export mặc định (để frontend gợi ý).
@router.get("/export-dir")
def api_export_dir():
    return {"ok": True, "data": {"mac_dinh": str(DATA_DIR / "migration-exports")}}
