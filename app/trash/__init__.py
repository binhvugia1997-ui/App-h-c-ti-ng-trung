"""Module thùng rác (trash): xóa mềm, khôi phục, xóa vĩnh viễn."""

from app.trash.trash import (
    list_trash,
    permanent_delete,
    restore_trash,
    soft_delete,
)

__all__ = ["list_trash", "permanent_delete", "restore_trash", "soft_delete"]
