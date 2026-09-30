"""Thùng rác (trash): xóa mềm file/thư mục, khôi phục, xóa vĩnh viễn.

Mỗi mục trong thùng rác là một thư mục::

    DATA_DIR/trash/<item_id>/
        meta.json   {item_id, original_path, deleted_at, is_dir, ten, kich_thuoc}
        data/...    nội dung gốc, giữ cấu trúc tương đối

Sử dụng::

    from app.trash import soft_delete, list_trash, restore_trash, permanent_delete
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.logging_config import get_logger
from app.paths import APP_ROOT, DATA_DIR, TRASH_DIR, ensure_dirs

log = get_logger(__name__)

_ITEM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _valid_item_id(item_id: str) -> bool:
    """Chống path traversal: item_id chỉ gồm ký tự an toàn."""
    return bool(_ITEM_ID_RE.match(item_id or ""))


def _relative_for_trash(src: Path) -> Path:
    """Cấu trúc tương đối được giữ trong trash: ưu tiên theo APP_ROOT."""
    resolved = src.resolve()
    for base in (APP_ROOT, DATA_DIR):
        try:
            return resolved.relative_to(base.resolve())
        except ValueError:
            continue
    return Path(resolved.name)


def _new_item_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"


def soft_delete(duong_dan_goc: str | Path) -> dict:
    """Xóa mềm: di chuyển file/thư mục vào TRASH_DIR, giữ cấu trúc tương đối."""
    ensure_dirs()
    src = Path(duong_dan_goc)
    if not src.exists():
        return {"ok": False, "error_vi": f"Không tìm thấy đường dẫn: {src}"}

    resolved = src.resolve()
    # Không cho xóa chính thư mục trash / data / APP_ROOT.
    for protected in (TRASH_DIR.resolve(), DATA_DIR.resolve(), APP_ROOT.resolve()):
        if resolved == protected or TRASH_DIR.resolve() in resolved.parents:
            return {"ok": False,
                    "error_vi": "Không thể đưa thư mục hệ thống/thùng rác vào thùng rác."}

    rel = _relative_for_trash(src)
    item_id = _new_item_id()
    item_dir = TRASH_DIR / item_id
    data_dir = item_dir / "data"
    target = data_dir / rel
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        is_dir = src.is_dir()
        kich_thuoc = 0
        if is_dir:
            kich_thuoc = sum(f.stat().st_size for f in src.rglob("*") if f.is_file())
        else:
            kich_thuoc = src.stat().st_size
        shutil.move(str(src), str(target))
    except OSError as exc:
        return {"ok": False, "error_vi": f"Không di chuyển được vào thùng rác: {exc}"}

    meta = {
        "item_id": item_id,
        "original_path": str(resolved),
        "cau_truc_tuong_doi": rel.as_posix(),
        "deleted_at": datetime.now().isoformat(timespec="seconds"),
        "is_dir": is_dir,
        "ten": src.name,
        "kich_thuoc": kich_thuoc,
    }
    (item_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("Đã xóa mềm %s -> trash/%s.", resolved, item_id)
    return {"ok": True, "data": {"item_id": item_id,
                                "trash_path": str(item_dir),
                                "original_path": str(resolved),
                                "ten": src.name}}


def list_trash() -> list[dict]:
    """Liệt kê các mục trong thùng rác, mới nhất trước."""
    ensure_dirs()
    results: list[dict] = []
    if not TRASH_DIR.exists():
        return results
    for item_dir in sorted(TRASH_DIR.iterdir(), reverse=True):
        if not item_dir.is_dir() or not _valid_item_id(item_dir.name):
            continue
        meta_path = item_dir / "meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta["trash_path"] = str(item_dir)
        results.append(meta)
    return results


def _load_item(item_id: str) -> tuple[dict | None, Path | None, str | None]:
    """Trả về (meta, item_dir, lỗi_vi)."""
    if not _valid_item_id(item_id):
        return None, None, f"item_id không hợp lệ: {item_id}"
    item_dir = TRASH_DIR / item_id
    meta_path = item_dir / "meta.json"
    if not item_dir.is_dir() or not meta_path.is_file():
        return None, None, f"Không tìm thấy mục trong thùng rác: {item_id}"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None, "Không đọc được meta.json của mục này."
    return meta, item_dir, None


def restore_trash(item_id: str) -> dict:
    """Khôi phục mục từ thùng rác về vị trí gốc."""
    meta, item_dir, err = _load_item(item_id)
    if err:
        return {"ok": False, "error_vi": err}
    assert meta is not None and item_dir is not None

    data_dir = item_dir / "data"
    if not data_dir.exists():
        return {"ok": False, "error_vi": "Mục trong thùng rác bị thiếu dữ liệu."}

    original = Path(meta["original_path"])
    try:
        if original.exists():
            # Tránh ghi đè: đổi tên đích hiện tại.
            backup_name = f"{original.name}.cu-{datetime.now():%Y%m%d%H%M%S}"
            original.rename(original.parent / backup_name)
            log.warning("Đích %s đã tồn tại, đã đổi tên thành %s.", original, backup_name)
        original.parent.mkdir(parents=True, exist_ok=True)
        stored = data_dir / meta.get("cau_truc_tuong_doi", "")
        if not stored.exists():
            # Fallback: lấy phần tử duy nhất trong data/
            children = list(data_dir.iterdir())
            if len(children) != 1:
                return {"ok": False,
                        "error_vi": "Cấu trúc dữ liệu trong thùng rác không như mong đợi."}
            stored = children[0]
        shutil.move(str(stored), str(original))
        shutil.rmtree(item_dir)
    except OSError as exc:
        return {"ok": False, "error_vi": f"Không khôi phục được: {exc}"}

    log.info("Đã khôi phục trash/%s về %s.", item_id, original)
    return {"ok": True, "data": {"item_id": item_id,
                                "restored_to": str(original),
                                "ten": meta.get("ten", "")}}


def permanent_delete(item_id: str, xac_nhan: bool = False) -> dict:
    """Xóa vĩnh viễn một mục trong thùng rác. BẮT BUỘC ``xac_nhan=True``."""
    if not xac_nhan:
        return {"ok": False,
                "error_vi": "Xóa vĩnh viễn cần xác nhận rõ ràng (xac_nhan=True). "
                            "Hành động này không thể hoàn tác."}
    meta, item_dir, err = _load_item(item_id)
    if err:
        return {"ok": False, "error_vi": err}
    assert item_dir is not None
    try:
        shutil.rmtree(item_dir)
    except OSError as exc:
        return {"ok": False, "error_vi": f"Không xóa được: {exc}"}
    log.info("Đã xóa vĩnh viễn trash/%s.", item_id)
    return {"ok": True, "data": {"item_id": item_id,
                                "ten": (meta or {}).get("ten", ""),
                                "ghi_chu": "Đã xóa vĩnh viễn, không thể khôi phục."}}


def empty_trash(xac_nhan: bool = False) -> dict:
    """Xóa vĩnh viễn TOÀN BỘ thùng rác. BẮT BUỘC ``xac_nhan=True``."""
    if not xac_nhan:
        return {"ok": False,
                "error_vi": "Dọn sạch thùng rác cần xác nhận rõ ràng (xac_nhan=True)."}
    items = list_trash()
    da_xoa = 0
    for info in items:
        result = permanent_delete(info["item_id"], xac_nhan=True)
        if result["ok"]:
            da_xoa += 1
    return {"ok": True, "data": {"da_xoa": da_xoa, "tong": len(items)}}
