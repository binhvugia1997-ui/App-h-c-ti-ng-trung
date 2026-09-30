"""Adapter cho module độc lập ``process_video.py``.

``process_video.py`` là file độc lập do người dùng tự cập nhật lên bản FINAL.
Module này TUYỆT ĐỐI KHÔNG tạo/sửa file đó dưới mọi hình thức — chỉ nạp
(lazy import) và gọi các hàm của nó qua adapter này. Adapter không đoán
implementation bên trong: mọi hàm được gọi theo tên stage, thiếu hàm nào
thì báo rõ ràng thay vì bịa kết quả.
"""

import importlib.util
import sys
from pathlib import Path

from app.logging_config import get_logger
from app.paths import APP_ROOT

log = get_logger(__name__)

MODULE_NAME = "process_video"

# Thông báo chuẩn khi module FINAL chưa được cài đặt.
NOT_READY_MESSAGE = (
    "Module xử lý video bản FINAL chưa được cài đặt. "
    "Vui lòng cập nhật file process_video.py."
)


class VideoModuleNotReady(Exception):
    """Ném ra khi ``process_video.py`` chưa sẵn sàng / thiếu stage yêu cầu."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or NOT_READY_MESSAGE)


def _candidate_paths() -> list[Path]:
    """Các vị trí có thể chứa file process_video.py (theo thứ tự ưu tiên)."""
    return [
        APP_ROOT / "process_video.py",
        APP_ROOT / "app" / "process_video.py",
    ]


def _load_from(path: Path):
    """Nạp module từ đường dẫn file. Lỗi -> VideoModuleNotReady."""
    try:
        spec = importlib.util.spec_from_file_location(MODULE_NAME, path)
        if spec is None or spec.loader is None:
            raise VideoModuleNotReady()
        module = importlib.util.module_from_spec(spec)
        # Đăng ký trước để module tự import lại chính nó không bị lặp.
        sys.modules[MODULE_NAME] = module
        spec.loader.exec_module(module)
        log.info("Đã tải module process_video từ %s", path)
        return module
    except VideoModuleNotReady:
        raise
    except Exception as exc:  # noqa: BLE001 - mọi lỗi nạp đều quy về "chưa sẵn sàng"
        sys.modules.pop(MODULE_NAME, None)
        log.error("Không tải được process_video từ %s: %s", path, exc)
        raise VideoModuleNotReady()


def get_module():
    """Trả về module ``process_video`` đã nạp, hoặc raise VideoModuleNotReady."""
    existing = sys.modules.get(MODULE_NAME)
    if existing is not None:
        return existing
    for path in _candidate_paths():
        try:
            if path.is_file():
                return _load_from(path)
        except VideoModuleNotReady:
            raise
        except Exception as exc:  # noqa: BLE001 - phòng thủ
            log.warning("Bỏ qua process_video tại %s: %s", path, exc)
            continue
    raise VideoModuleNotReady()


def is_available() -> bool:
    """True nếu ``process_video.py`` tồn tại và nạp được; mọi exception -> False."""
    try:
        get_module()
        return True
    except Exception:  # noqa: BLE001
        return False


def run_stage(stage_name: str, **kwargs):
    """Gọi hàm tương ứng ``stage_name`` của process_video với kwargs truyền qua.

    Không đoán implementation bên trong: chỉ gọi đúng tên hàm được yêu cầu.
    Raise VideoModuleNotReady nếu module chưa cài hoặc không có hàm đó.
    """
    module = get_module()  # raise VideoModuleNotReady nếu chưa sẵn sàng
    func = getattr(module, stage_name, None)
    if not callable(func):
        raise VideoModuleNotReady(
            f"Module process_video chưa hỗ trợ stage '{stage_name}'. "
            "Vui lòng cập nhật file process_video.py bản FINAL."
        )
    return func(**kwargs)


def list_supported_stages() -> list[str]:
    """Liệt kê tên các hàm public của process_video (introspect an toàn).

    Trả về [] khi module chưa được cài đặt hoặc introspect thất bại.
    """
    try:
        module = get_module()
    except Exception:  # noqa: BLE001
        return []
    try:
        try:
            from app.video.checkpoints import STAGES as _KNOWN_STAGES
        except Exception:  # noqa: BLE001
            _KNOWN_STAGES = []
        names: list[str] = []
        for name in dir(module):
            if name.startswith("_"):
                continue
            try:
                obj = getattr(module, name)
            except Exception:  # noqa: BLE001
                continue
            if not callable(obj):
                continue
            if name in _KNOWN_STAGES or name.startswith(("stage_", "run_", "process_")):
                names.append(name)
        return sorted(names)
    except Exception as exc:  # noqa: BLE001
        log.warning("Không introspect được process_video: %s", exc)
        return []
