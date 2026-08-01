"""
配置管理模块
读取/写入个人数据目录中的 config.json（普通配置，不含敏感信息）
敏感信息（API Key 等）委托给 secure_store 模块处理
"""

import json
from datetime import datetime
import branding
from paths import CONFIG_FILE
import secure_store as sec


def load_config():
    """加载配置文件，返回 dict。若文件不存在返回空 dict。"""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict):
    """保存普通配置到外置个人数据目录。"""
    # 确保敏感字段不会意外写回明文 config.json
    safe = {k: v for k, v in config.items() if k != "api_key"}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2, ensure_ascii=False)


def get_api_key():
    """获取 API Key（从加密存储读取）"""
    return sec.get_api_key()


def set_api_key(key: str):
    """保存 API Key（写入加密存储）"""
    sec.set_api_key(key)


def has_api_key() -> bool:
    """检查 API Key 是否已设置"""
    return sec.has_api_key()


def clear_api_key():
    """删除加密存储的 API Key"""
    sec.clear_api_key()


def migrate_api_key_from_legacy():
    """
    迁移旧版 config.json 中的 api_key 到加密存储。
    启动时调用，自动执行。
    """
    try:
        old_cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    old_key = old_cfg.get("api_key", "")
    if not old_key:
        return False
    if sec.has_api_key():
        # 已有加密 Key，直接清理旧的
        del old_cfg["api_key"]
        save_config(old_cfg)
        return True
    ok = sec.set_api_key(old_key)
    if ok:
        # 迁移成功，从普通配置清理
        del old_cfg["api_key"]
        save_config(old_cfg)
    return ok


def get_cli_path():
    """获取自定义 CLI 路径"""
    return load_config().get("cli_path", "")


def set_cli_path(path: str):
    """保存自定义 CLI 路径"""
    cfg = load_config()
    cfg["cli_path"] = path
    save_config(cfg)


def get_tab_order():
    """读取顶部标签页顺序配置。"""
    order = load_config().get("tab_order", [])
    return order if isinstance(order, list) else []


def set_tab_order(order):
    """保存顶部标签页顺序配置。"""
    cfg = load_config()
    cfg["tab_order"] = list(order)
    save_config(cfg)


def get_window_geometry():
    """Return the last normal window geometry, if it is safe to restore."""
    value = load_config().get("window_geometry", "")
    return value if isinstance(value, str) else ""


def set_window_geometry(value):
    """Persist only UI geometry; sensitive values remain in secure_store."""
    cfg = load_config()
    cfg["window_geometry"] = value
    save_config(cfg)


def get_gateway_port() -> int:
    """获取本地网页看板端口；非法旧配置安全回退到默认值。"""
    try:
        port = int(load_config().get("gateway_port", 8765))
    except (TypeError, ValueError):
        return 8765
    return port if 1024 <= port <= 65535 else 8765


def set_gateway_port(port: int):
    """保存本地网页看板端口（仅端口号，不保存主机地址）。"""
    port = int(port)
    if not 1024 <= port <= 65535:
        raise ValueError("端口必须在 1024 到 65535 之间")
    cfg = load_config()
    cfg["gateway_port"] = port
    save_config(cfg)


def get_workspace_preferences() -> dict:
    """读取网页工作台的非敏感展示设置。"""
    cfg = load_config()
    return {
        "title": str(cfg.get("workspace_title") or "秋招工作台").strip() or "秋招工作台",
        "developer_name": branding.DEVELOPER_NAME,
        "contact_email": branding.CONTACT_EMAIL,
        "project_url": branding.PROJECT_URL,
    }


def set_workspace_preferences(title="", *_legacy_branding_values):
    """保存用户可定制的工作台标题；公开开发者信息由程序统一提供。"""
    cfg = load_config()
    cfg["workspace_title"] = str(title).strip() or "秋招工作台"
    save_config(cfg)


def get_backup_preferences() -> dict:
    """自动备份默认关闭，避免未经用户选择持续占用磁盘。"""
    cfg = load_config()
    try:
        interval_days = int(cfg.get("backup_interval_days", 7))
    except (TypeError, ValueError):
        interval_days = 7
    if interval_days not in (1, 3, 7, 14, 30):
        interval_days = 7
    return {
        "enabled": bool(cfg.get("automatic_backup_enabled", False)),
        "interval_days": interval_days,
        "last_backup_at": str(cfg.get("automatic_backup_last_at") or ""),
    }


def set_backup_preferences(enabled=False, interval_days=7):
    interval_days = int(interval_days)
    if interval_days not in (1, 3, 7, 14, 30):
        raise ValueError("自动备份间隔只支持 1、3、7、14 或 30 天")
    cfg = load_config()
    cfg["automatic_backup_enabled"] = bool(enabled)
    cfg["backup_interval_days"] = interval_days
    save_config(cfg)


def mark_automatic_backup_completed():
    cfg = load_config()
    cfg["automatic_backup_last_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    save_config(cfg)


def ensure_api_key(parent=None):
    """确保 API Key 存在，否则弹窗输入"""
    key = sec.get_api_key()
    if key:
        return key
    from PyQt6.QtWidgets import QInputDialog, QLineEdit
    k, ok = QInputDialog.getText(parent, "设置 API Key",
                                  "请输入你的 DeepSeek API Key：",
                                  QLineEdit.EchoMode.Password)
    if ok and k.strip():
        sec.set_api_key(k.strip())
        return k.strip()
    return None
