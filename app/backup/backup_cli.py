"""CLI backup: ``python -m app.backup.backup_cli [--dry-run] [--ghi-chu "..."]``."""

from __future__ import annotations

import argparse
import sys

from app.backup.backup import create_backup, plan_backup
from app.logging_config import get_logger

log = get_logger(__name__)


def _fmt_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tạo bản sao lưu dữ liệu Hán Ngữ Server."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Chỉ liệt kê những gì sẽ backup, không tạo file.")
    parser.add_argument("--ghi-chu", default="",
                        help="Ghi chú đính kèm bản backup.")
    args = parser.parse_args(argv)

    try:
        if args.dry_run:
            result = plan_backup()
            data = result["data"]
            print("=== KẾ HOẠCH BACKUP (thử, chưa tạo file) ===")
            print(f"Tổng số file : {data['file_count']}")
            print(f"Tổng dung lượng (ước tính): {_fmt_size(data['total_bytes'])}")
            print("Các nhóm:")
            groups: dict[str, int] = {}
            for item in data["files"]:
                groups[item["group"]] = groups.get(item["group"], 0) + 1
            for group, count in sorted(groups.items()):
                print(f"  - {group}: {count} file")
            return 0

        result = create_backup(ghi_chu=args.ghi_chu)
        print("=== TẠO BACKUP THÀNH CÔNG ===")
        print(f"File        : {result['backup_path']}")
        print(f"Số file    : {result['file_count']}")
        print(f"Dung lượng : {_fmt_size(result['total_bytes'])}")
        if args.ghi_chu:
            print(f"Ghi chú     : {args.ghi_chu}")
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI in lỗi thân thiện
        print(f"LỖI: Không tạo được backup: {exc}", file=sys.stderr)
        log.error("backup_cli thất bại: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
