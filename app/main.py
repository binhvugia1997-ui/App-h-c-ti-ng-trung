"""Điểm vào FastAPI.

- Khi start: gọi ``run_startup()`` (lifespan).
- Tự động phát hiện mọi ``app/<module>/router.py`` và gắn ``router``
  (import lỗi → log warning, app vẫn chạy).
- Serve thư mục ``web/`` tĩnh ở ``/``; nếu thiếu thì trả trang chờ
  đơn giản, không crash.
- Handler lỗi chung trả ``{"ok": false, "error_vi": "..."}`` tiếng Việt,
  không lộ stack trace.
"""
from __future__ import annotations

import importlib
import pkgutil
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import app as _app_pkg
from app.logging_config import get_logger
from app.paths import APP_ROOT

log = get_logger(__name__)

WEB_DIR = APP_ROOT / "web"
INDEX_FILE = WEB_DIR / "index.html"

_WAITING_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head><meta charset="utf-8"><title>Hán Ngữ Server</title></head>
<body style="font-family:sans-serif;text-align:center;padding:64px;">
<h1>\U0001f004 Hán Ngữ Server</h1>
<p>Backend đã chạy. Giao diện web chưa được cài đặt (thiếu thư mục <code>web/</code>).</p>
<p>Kiểm tra trạng thái hệ thống tại <a href="/api/health">/api/health</a>.</p>
</body></html>
"""


def _discover_routers(fastapi_app: FastAPI) -> None:
    """Quét ``app/*/router.py`` và gắn mọi ``router`` tìm được."""
    for _finder, name, is_pkg in pkgutil.iter_modules(_app_pkg.__path__):
        if not is_pkg:
            continue
        module_name = f"app.{name}.router"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue  # module không có router.py: bỏ qua
        except Exception:
            log.warning(
                "Bỏ qua router '%s': import lỗi, app vẫn chạy.\n%s",
                module_name,
                traceback.format_exc(limit=3),
            )
            continue
        router = getattr(module, "router", None)
        if router is not None:
            fastapi_app.include_router(router)
            log.info("Đã gắn router: %s", module_name)


def _mount_health(fastapi_app: FastAPI) -> None:
    """Gắn router health (nằm ở app/health.py, không phải package)."""
    try:
        from app.health import router as health_router

        fastapi_app.include_router(health_router)
        log.info("Đã gắn router: app.health")
    except Exception:
        log.warning(
            "Không gắn được router health, app vẫn chạy.\n%s",
            traceback.format_exc(limit=3),
        )


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    from app.startup import run_startup

    run_startup()
    yield


app = FastAPI(title="Hán Ngữ Server", version="0.1.0", lifespan=lifespan)

_discover_routers(app)
_mount_health(app)

if WEB_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
    log.info("Serve thư mục web tĩnh: %s", WEB_DIR)
else:
    log.warning(
        "Thiếu thư mục web/ (%s): trang chủ sẽ hiển thị trang chờ.", WEB_DIR
    )


@app.get("/", include_in_schema=False)
def index():
    """Trang chủ: file web/index.html nếu có, ngược lại trang chờ."""
    if INDEX_FILE.is_file():
        return FileResponse(str(INDEX_FILE), media_type="text/html")
    return HTMLResponse(_WAITING_PAGE)


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "error_vi": "Dữ liệu gửi lên không hợp lệ. Vui lòng kiểm tra lại.",
        },
    )


@app.exception_handler(Exception)
async def _unhandled_error_handler(request: Request, exc: Exception):
    log.error("Lỗi chưa xử lý tại %s: %r", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error_vi": "Đã xảy ra lỗi hệ thống. Vui lòng thử lại sau.",
        },
    )


def run() -> None:
    """Chạy server uvicorn với host/port từ settings."""
    from app.config import settings

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
