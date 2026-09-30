"""Module migration: xuất / nhập / kiểm chứng gói di chuyển máy.

- ``export``: tạo gói migration (thư mục) từ máy cũ.
- ``import_``: nhập gói vào máy mới (có dry-run, rollback).
- ``verify``: kiểm chứng cài đặt sau migration (PASS/PARTIAL/FAIL/NOT_TESTED).
- ``dry_run``: kế hoạch export/import thử, liệt kê việc cần làm thủ công.
"""

from app.migration.dry_run import bao_cao_dry_run, ke_hoach_export, ke_hoach_import
from app.migration.export import create_export_package
from app.migration.import_ import import_package
from app.migration.verify import verify_installation

__all__ = [
    "bao_cao_dry_run",
    "create_export_package",
    "import_package",
    "ke_hoach_export",
    "ke_hoach_import",
    "verify_installation",
]
