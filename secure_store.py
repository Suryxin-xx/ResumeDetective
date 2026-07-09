"""
secure_store.py — 加密存储模块
使用 Windows DPAPI (CryptProtectData) 加密敏感信息
密钥绑定到当前 Windows 用户账号，无需额外密码或依赖。

本机加密，不解密到任何地方，仅运行时在内存中保持明文。
"""

import base64
import json
import ctypes
import ctypes.wintypes
from pathlib import Path

from paths import DATA_DIR

SECRET_FILE = DATA_DIR / "secret.json.enc"

# ── Windows DPAPI ──

CRYPTPROTECT_UI_FORBIDDEN = 0x01


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _crypt_protect(data: bytes) -> bytes:
    """使用 Windows DPAPI 加密数据（绑定当前用户）。"""
    blob_in = DATA_BLOB(len(data), ctypes.cast(data, ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
    ):
        raise RuntimeError("CryptProtectData 失败")
    result = ctypes.string_at(blob_out.pbData, int(blob_out.cbData))
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return result


def _crypt_unprotect(data: bytes) -> bytes:
    """使用 Windows DPAPI 解密数据。"""
    blob_in = DATA_BLOB(len(data), ctypes.cast(data, ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
    ):
        raise RuntimeError("CryptUnprotectData 失败")
    result = ctypes.string_at(blob_out.pbData, int(blob_out.cbData))
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return result


# ── 加密 JSON 存储 ──


def _load_secrets() -> dict:
    """加载并解密存储的敏感信息，返回 dict。"""
    if not SECRET_FILE.exists():
        return {}
    try:
        raw = SECRET_FILE.read_bytes()
        if not raw:
            return {}
        decrypted = _crypt_unprotect(raw)
        return json.loads(decrypted.decode("utf-8"))
    except Exception:
        # 文件损坏等极端情况：返回空，不抛出以免阻塞启动
        return {}


def _save_secrets(data: dict):
    """加密并保存敏感信息到文件。"""
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    encrypted = _crypt_protect(raw)
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRET_FILE.write_bytes(encrypted)


# ── 公开 API ──


def has_api_key() -> bool:
    """检查是否已设置 API Key（不返回 Key 本身）。"""
    return bool(_load_secrets().get("api_key", ""))


def get_api_key() -> str:
    """获取明文 API Key，返回空字符串表示未设置。"""
    return _load_secrets().get("api_key", "")


def set_api_key(key: str) -> bool:
    """
    设置 API Key（加密存储）。
    返回 True 表示成功。
    """
    try:
        secrets = _load_secrets()
        secrets["api_key"] = key
        _save_secrets(secrets)
        return True
    except Exception:
        return False


def clear_api_key():
    """删除加密存储的 API Key。"""
    secrets = _load_secrets()
    secrets.pop("api_key", None)
    _save_secrets(secrets)


def upgrade_from_legacy(legacy_getter) -> bool:
    """
    从旧的明文配置迁移 API Key。
    legacy_getter：无参数可调用，返回 (api_key: str) 或 None/空
    迁移成功后返回 True，失败返回 False。
    """
    try:
        old_key = legacy_getter()
        if old_key:
            ok = set_api_key(old_key)
            if ok:
                return True
        return False
    except Exception:
        return False
