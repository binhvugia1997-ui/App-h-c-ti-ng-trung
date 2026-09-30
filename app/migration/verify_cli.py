"""CLI verify migration: ``python -m app.migration.verify_cli``."""

from __future__ import annotations

import argparse
import sys

from app.logging_config import get_logger
from app.migration.verify import verify_installation

log = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Kiểm chứng cài đặt Hán Ngữ Server sau migration.")
    parser.parse_args(argv)
    try:
        result = verify_installation()
        data = result["data"]
        print("=== KIỂM CHỨNG CÀI ĐẶT ===")
        print(f"App root : {data['app_root']}")
        print(f"Kiểm tra lúc: {data['generated_at']}")
        print("-" * 60)
        for name, group in data["groups"].items():
            print(f"[{group['trang_thai']:>10}] {name}")
            print(f"           {group['chi_tiet']}")
        print("-" * 60)
        tom_tat = data["tom_tat"]
        parts = [f"{k}={v}" for k, v in sorted(tom_tat.items())]
        print("Tóm tắt: " + ", ".join(parts))
        if tom_tat.get("FAIL"):
            return 1
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"LỖI: Không chạy được kiểm chứng: {exc}", file=sys.stderr)
        log.error("verify_cli thất bại: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
