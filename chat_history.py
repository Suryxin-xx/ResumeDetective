"""
聊天历史管理器
保存/读取/删除对话记录，支持导出 Markdown
"""

import json
from datetime import datetime
from pathlib import Path

import paths
import file_ops

CHAT_DIR = paths.DATA_DIR / "chat_history"


def _ensure_dir():
    CHAT_DIR.mkdir(parents=True, exist_ok=True)


def _chat_path(chat_id):
    return CHAT_DIR / f"{chat_id}.json"


def _gen_id():
    return datetime.now().strftime("chat_%Y%m%d_%H%M%S")


def new_chat():
    """创建新对话，返回 chat_id"""
    _ensure_dir()
    chat_id = _gen_id()
    data = {"id": chat_id, "title": "新对话", "messages": [], "created": chat_id}
    save_chat(chat_id, data)
    return chat_id


def save_chat(chat_id, data):
    """保存对话"""
    _ensure_dir()
    with open(_chat_path(chat_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_chat(chat_id):
    """加载对话"""
    p = _chat_path(chat_id)
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def list_chats():
    """列出所有对话（按创建时间倒序）"""
    _ensure_dir()
    chats = []
    for f in sorted(CHAT_DIR.glob("chat_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text("utf-8"))
            title = data.get("title", f.stem)
            preview = data.get("preview", "")
            if not preview:
                msgs = data.get("messages", [])
                if msgs:
                    preview = msgs[0].get("content", "")[:60]
            chats.append({"id": f.stem, "title": title, "preview": preview})
        except Exception:
            continue
    return chats


def rename_chat(chat_id, new_title):
    """重命名对话"""
    data = load_chat(chat_id)
    if data is None:
        return False
    data["title"] = new_title
    save_chat(chat_id, data)
    return True


def delete_chat(chat_id):
    """删除对话文件：移入回收站，失败时保留文件。"""
    p = _chat_path(chat_id)
    if p.exists():
        ok, msg = file_ops.recycle_path(p)
        if not ok:
            print(f"[聊天记录] {msg}: {p}")


def add_message(chat_id, role, content):
    """添加一条消息（自动带时间戳）"""
    data = load_chat(chat_id)
    if data is None:
        return
    ts = datetime.now().strftime("%m-%d %H:%M")
    data["messages"].append({"role": role, "content": content, "timestamp": ts})
    # 用第一条用户消息做标题和预览
    if role == "user" and data.get("title") == "新对话":
        data["title"] = content[:30]
        data["preview"] = content[:60]
    save_chat(chat_id, data)


def export_md(chat_id):
    """导出为 Markdown（含时间戳，角色用 --- 分隔）"""
    data = load_chat(chat_id)
    if data is None:
        return ""
    title = data.get("title", "对话记录")
    lines = [f"# {title}\n", f"> 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
    for m in data.get("messages", []):
        role = m["role"]
        name = "你" if role == "user" else "AI"
        ts = m.get("timestamp", "")
        lines.append(f"\n---\n### {name}  [{ts}]\n")
        lines.append(m.get("content", ""))
    lines.append("\n---\n")
    return "\n".join(lines)


def get_balance(api_key):
    """查询 DeepSeek 余额"""
    if not api_key:
        return None
    import requests
    try:
        r = requests.get(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("balance_infos", [{}])[0].get("total_balance", "?")
    except Exception:
        return None
