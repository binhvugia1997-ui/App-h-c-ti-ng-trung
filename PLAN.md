# PLAN — Hán Ngữ Server

Ngày: 2026-09-30. Repo trống → xây mới theo MASTER PROMPT (60 mục).

## 1. Stack

- Backend: **FastAPI** + **uvicorn**, DB **SQLite** qua **stdlib `sqlite3`** (không ORM, không over-engineer)
- AI: **Qwen qua Ollama** (`QWEN_BASE_URL`, `QWEN_MODEL` configurable), 1 client duy nhất
- Frontend: HTML/CSS/JS tĩnh trong `web/`, tiếng Việt
- Dependencies: `fastapi`, `uvicorn[standard]`, `python-dotenv`, `httpx`

## 2. Cây thư mục

```
hanngu-server/
  app/
    __init__.py
    paths.py            # source of truth cho mọi path
    config.py           # đọc .env → đối tượng `settings`
    logging_config.py   # get_logger(name), rotation, không log secret
    db/
      __init__.py
      database.py       # get_conn(), init_core(), ensure_column()
    main.py             # FastAPI app, tự động mount mọi app/*/router.py
    startup.py          # startup sequence 8 bước (mục 40)
    health.py           # router /api/health (core vs external)
    qwen/
      __init__.py
      client.py         # QwenClient DUY NHẤT, get_qwen_client()
    ai_exercises/
      __init__.py, tables.py, viet_trung.py, trung_viet.py, router.py
    video/
      __init__.py, adapter_process_video.py, ffmpeg.py, checkpoints.py,
      jobs.py, pipeline.py, tables.py, router.py
    vocab/
      __init__.py, tables.py, srs.py, router.py
    dashboard/
      __init__.py, tables.py, stats.py, router.py
    shadowing/
      __init__.py, tables.py, router.py
    pronunciation/
      __init__.py, tables.py, calibration.py, router.py
    dictation/
      __init__.py, tables.py, router.py
    backup/
      __init__.py, backup.py, backup_cli.py
    recovery/
      __init__.py, recovery.py
    trash/
      __init__.py, trash.py, router.py
    migration/
      __init__.py, export.py, import_.py, verify.py, dry_run.py,
      export_cli.py, import_cli.py, verify_cli.py, router.py
    settings_router.py  # GET/PUT /api/settings (nằm trong core)
  web/
    index.html, style.css, app.js
  scripts/
    START_APP.bat, BACKUP.bat, MIGRATE_EXPORT.bat, MIGRATE_IMPORT.bat,
    VERIFY_MIGRATION.bat
  .env.example
  requirements.txt
  README.md, AUDIT.md, PLAN.md, TEST_RESULTS.md
```

## 3. HỢP ĐỒNG TÍCH HỢP (mọi module BẮT BUỘC tuân thủ)

### 3.1 `app/paths.py` (core tạo)

```python
APP_ROOT: Path        # = thư mục chứa app/ (repo root), resolve từ __file__
DATA_DIR = APP_ROOT / "data"
MEDIA_DIR = DATA_DIR / "media"
RECORDINGS_DIR = DATA_DIR / "recordings"
RECOVERY_DIR = DATA_DIR / "recovery"
TRASH_DIR = DATA_DIR / "trash"
CONFIG_DIR = DATA_DIR / "config"
BACKUP_DIR = DATA_DIR / "backups"
MODEL_DIR = DATA_DIR / "models"
LOGS_DIR = DATA_DIR / "logs"
def ensure_dirs() -> None  # tạo mọi thư mục trên nếu thiếu, không xóa dữ liệu
```

Mọi path trong app PHẢI import từ `app.paths`. CẤM hard-code `D:\...`, `C:\...`.

### 3.2 `app/config.py` (core tạo)

`from app.config import settings` — object với thuộc tính:
`host` (127.0.0.1), `port` (8000), `db_path` (DATA_DIR/hanngu.db),
`ffmpeg_path` ("" = tự detect), `qwen_base_url` ("http://127.0.0.1:11434"),
`qwen_model` ("qwen2.5:7b"), `log_level` ("INFO"),
`media_dir`, `recordings_dir`, `backup_dir` (ghi đè DATA_DIR/* nếu set).
Đọc `.env` ở APP_ROOT (dùng `python-dotenv` nếu có, fallback parser stdlib).
KHÔNG hard-code IP/secret.

### 3.3 `app/db/database.py` (core tạo)

```python
from contextlib import contextmanager
@contextmanager
def get_conn():  # sqlite3.Connection, row_factory=Row, tự commit/rollback, check_same_thread=False
    ...
def ensure_column(conn, table: str, column: str, ddl: str): ...
```

### 3.4 Quy ước init DB của module

Mỗi module có dữ liệu riêng tạo `app/<module>/tables.py` với:

```python
def init_db(conn) -> None:  # CREATE TABLE IF NOT EXISTS + ensure_column khi nâng cấp
    ...
```

`startup.py` tự gọi `init_db` của mọi module (không cần đăng ký thủ công).

### 3.5 Router auto-discovery (core tạo trong `main.py`)

Mọi module tạo `app/<module>/router.py` với biến `router = APIRouter(prefix="/api/...")`.
`main.py` quét `app/*/router.py`, import và `include_router`. Serve `web/` tĩnh ở `/`.

### 3.6 Logging

`from app.logging_config import get_logger; log = get_logger(__name__)`.
CẤM log secret/token.

### 3.7 Qwen client (module qwen tạo) — các module khác dùng

```python
from app.qwen.client import get_qwen_client, QwenError
client = get_qwen_client()
client.check() -> {"ok": bool, "message_vi": str, "model": str|None, "latency_ms": int|None}
client.chat_json(system: str, user: str, timeout: float = 60) -> dict
    # parse/repair JSON; lỗi → raise QwenError("Máy AI hiện không kết nối được. Vui lòng kiểm tra máy Qwen.")
client.chat_text(system: str, user: str, timeout: float = 60) -> str
```

### 3.8 Quy ước response JSON

- Thành công: `{"ok": true, "data": ...}`
- Lỗi thân thiện tiếng Việt: `{"ok": false, "error_vi": "..."}` (không lộ stack trace)
- Metric không tính được → `null`, KHÔNG bịa số.

### 3.9 Prefix API

| Module | Prefix |
|---|---|
| health | `/api/health` |
| settings | `/api/settings` |
| dashboard | `/api/dashboard` |
| vocab | `/api/vocab` |
| video | `/api/video` |
| ai_exercises | `/api/exercises` |
| shadowing | `/api/shadowing` |
| pronunciation | `/api/pronunciation` |
| dictation | `/api/dictation` |
| trash | `/api/trash` |
| backup | `/api/backup` |
| migration | `/api/migration` |

## 4. Phân công subagent (song song)

1. **core**: paths, config, logging_config, db/database, main, startup, health, settings router
2. **qwen-ai**: qwen/client + ai_exercises (viet_trung, trung_viet, tables, router)
3. **video**: adapter_process_video (KHÔNG tạo process_video.py), ffmpeg, checkpoints, jobs, pipeline, tables, router
4. **learning**: vocab (+srs), dashboard, shadowing, pronunciation (+calibration), dictation — tables + router mỗi module
5. **data-mgmt**: backup (+cli), recovery, trash (+router), migration (export/import/verify/dry_run + 3 cli + router)
6. **frontend-pkg**: web/ (index.html, style.css, app.js — 9 tab tiếng Việt), scripts/*.bat, .env.example, requirements.txt, README.md (12 mục theo prompt 53)

## 5. TEST (coordinator tự chạy sau khi 6 module xong)

- App startup, DB init, portable path (giả lập di chuyển APP_ROOT)
- ffmpeg detect, Qwen offline fallback (không crash)
- backup/restore dry-run, migration export/import/verify dry-run
- Quét hard-coded path (`D:\`, `C:\`, `HanNguServer`) và secret
- Ghi `TEST_RESULTS.md` trung thực — không PASS giả

## 6. Nguyên tắc nhắc lại

- KHÔNG tạo/sửa `process_video.py` dưới mọi hình thức.
- Tôn trọng marker FINAL/DO NOT MODIFY/LOCKED.
- Không hard-code path/IP/key/secret. Không bịa score. Không PASS giả.
- Mọi file code hoàn chỉnh, không patch/diff.
