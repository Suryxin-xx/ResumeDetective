"""
文件安全操作。
用户资料文件删除时优先移入系统回收站；失败时保留原文件。
"""

from pathlib import Path


def recycle_path(path) -> tuple[bool, str]:
    """将文件或目录移入回收站。返回 (是否成功, 说明)。"""
    target = Path(path)
    if not target.exists():
        return True, "文件不存在，无需处理"

    try:
        from send2trash import send2trash
    except ImportError:
        send2trash = None

    if send2trash is not None:
        try:
            send2trash(str(target))
            return True, "已移入回收站"
        except Exception as exc:
            return False, f"移入回收站失败：{exc}"

    try:
        import ctypes
        from ctypes import wintypes
    except ImportError as exc:
        return False, f"当前系统不支持回收站操作：{exc}"

    if not hasattr(ctypes, "windll"):
        return False, "当前系统不支持 Windows 回收站操作"

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.USHORT),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 0x0003
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_SILENT = 0x0004
    FOF_NOERRORUI = 0x0400

    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = str(target.resolve()) + "\0\0"
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if result == 0 and not op.fAnyOperationsAborted:
        return True, "已移入回收站"
    return False, f"移入回收站失败，系统返回码：{result}"
