"""CLI import migration: ``python -m app.migration.import_cli --in <package> [--dry-run]``."""

from __future__ import annotations

import argparse
import sys

from app.logging_config import get_logger
from app.migration.import_ import import_package

log = get_logger(__name__)

_ICON = {"ok": "✓", "skip": "…", "fail": "✗"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Nhập gói migration Hán Ngữ Server vào máy mới.")
    parser.add_argument("--in", dest="package", required=True,
                        help="Đường dẫn gói migration (thư mục hoặc file .zip).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Chế độ thử: chỉ liệt kê, không ghi file nào.")
    args = parser.parse_args(argv)
    try:
        report = import_package(args.package, dry_run=args.dry_run)
        mode = "THỬ (dry-run)" if args.dry_run else "THẬT"
        print(f"=== NHẬP GÓI MIGRATION [{mode}] ===")
        for step in report.get("steps", []):
            icon = _ICON.get(step.get("trang_thai"), "?")
            print(f"[{icon}] {step['buoc']}: {step.get('chi_tiet', '')}")
        if report.get("recovery_point"):
            print(f"Recovery point: {report['recovery_point']}")
        if report.get("da_rollback"):
            print("Đã rollback về recovery point do import thất bại.")
        if not report.get("ok"):
            print(f"LỖI: {report.get('error_vi', 'import thất bại')}", file=sys.stderr)
            return 1
        print("Hoàn tất.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"LỖI: Không nhập được gói migration: {exc}", file=sys.stderr)
        log.error("import_cli thất bại: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
