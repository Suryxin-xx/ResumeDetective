"""
配置管理模块
读取/写入 data/config.json（普通配置，不含敏感信息）
敏感信息（API Key 等）委托给 secure_store 模块处理
"""

import json
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
    """保存配置到 data/config.json"""
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
