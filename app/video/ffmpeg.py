"""Phát hiện FFmpeg trên máy.

Thứ tự ưu tiên:
1. ``settings.ffmpeg_path`` (nếu người dùng đã cấu hình trong Cài đặt)
2. File bundled tại ``APP_ROOT/bin/ffmpeg[.exe]``
3. ``shutil.which("ffmpeg")`` (tìm trong PATH hệ thống)

Không hard-code ổ đĩa hay đường dẫn tuyệt đối nào.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from app.config import settings
from app.logging_config import get_logger
from app.paths import APP_ROOT

log = get_logger(__name__)

NOT_FOUND_VI = (
    "Không tìm thấy FFmpeg. "
    "Vui lòng cài FFmpeg hoặc cấu hình đường dẫn trong Cài đặt."
)


def _probe_version(ffmpeg_path: Path) -> str | None:
    """Chạy ``ffmpeg -version``, trích chuỗi phiên bản. Thất bại -> None."""
    try:
        proc = subprocess.run(
            [str(ffmpeg_path), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = (proc.stdout or "").splitlines()
        if not lines:
            return None
        match = re.search(r"ffmpeg version (\S+)", lines[0])
        if match:
            return match.group(1)
        return lines[0].strip()[:120] or None
    except Exception as exc:  # noqa: BLE001
        log.debug("Không đọc được phiên bản FFmpeg tại %s: %s", ffmpeg_path, exc)
        return None


def _candidate_paths() -> list[tuple[str, Path]]:
    """Danh sách (nguồn, đường dẫn) ứng viên FFmpeg theo thứ tự ưu tiên."""
    candidates: list[tuple[str, Path]] = []
    configured = (getattr(settings, "ffmpeg_path", "") or "").strip()
    if configured:
        candidates.append(("cấu hình", Path(configured)))
    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    candidates.append(("bundled", APP_ROOT / "bin" / exe_name))
    which_path = shutil.which("ffmpeg")
    if which_path:
        candidates.append(("PATH", Path(which_path)))
    return candidates


def detect_ffmpeg() -> dict:
    """Trả về {"ok", "path", "version", "message_vi"}.

    Thiếu FFmpeg -> ok=False, message_vi hướng dẫn cài đặt bằng tiếng Việt.
    """
    seen: set[str] = set()
    for source, candidate in _candidate_paths():
        try:
            key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            if candidate.is_file():
                version = _probe_version(candidate)
                log.info("Tìm thấy FFmpeg (%s): %s", source, candidate)
                return {
                    "ok": True,
                    "path": str(candidate),
                    "version": version,
                    "message_vi": "Đã tìm thấy FFmpeg.",
                }
        except Exception as exc:  # noqa: BLE001
            log.debug("Bỏ qua FFmpeg (%s) tại %s: %s", source, candidate, exc)
            continue
    return {
        "ok": False,
        "path": None,
        "version": None,
        "message_vi": NOT_FOUND_VI,
    }
