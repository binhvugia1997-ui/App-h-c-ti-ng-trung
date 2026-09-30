"""CLI export migration: ``python -m app.migration.export_cli --out <dir>``."""

from __future__ import annotations

import argparse
import sys

from app.logging_config import get_logger
from app.migration.export import create_export_package

log = get_logger(__name__)


def _fmt_size(num_bytes: int) -> str:
    value = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Xuất gói migration Hán Ngữ Server (để chuyển sang máy mới).")
    parser.add_argument("--out", default="",
                        help="Thư mục đích chứa gói migration "
                             "(mặc định: data/migration-exports).")
    args = parser.parse_args(argv)
    try:
        manifest = create_export_package(args.out or None)
        print("=== XUẤT GÓI MIGRATION THÀNH CÔNG ===")
        print(f"Gói           : {manifest['package_path']}")
        print(f"Phiên bản     : {manifest['migration_version']}")
        print(f"Xuất lúc      : {manifest['exported_at']}")
        print("Các nhóm:")
        for name, info in manifest["groups"].items():
            extra = ""
            if name in ("media", "recordings"):
                extra = (f" ({info.get('so_file', 0)} file, "
                         f"{_fmt_size(info.get('tong_dung_luong', 0))})")
            elif name == "db":
                extra = (f" ({len(info.get('bang', []))} bảng, "
                         f"{info.get('tong_dong', 0)} dòng)")
            elif name == "learning":
                extra = f" ({info.get('tong_bang', 0)} bảng)"
            elif name == "models":
                extra = f" ({info.get('so_model', 0)} model, chỉ manifest)"
            print(f"  - {name}: {info.get('trang_thai')}{extra}")
        redacted = manifest["groups"]["config"].get("khoa_da_redact", [])
        if redacted:
            print(f"Đã redact {len(redacted)} khóa secret "
                  "(sang máy mới cần đăng nhập lại).")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"LỖI: Không xuất được gói migration: {exc}", file=sys.stderr)
        log.error("export_cli thất bại: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
