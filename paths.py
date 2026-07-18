"""项目资源与个人运行数据路径。

源码目录可以直接作为 Git 仓库；数据库、API 密钥、简历和运行缓存默认放在
仓库之外。打包后的便携版仍把数据放在 EXE 旁边，保持原有使用方式。
"""

import json
import os
import shutil
import sys
from pathlib import Path


if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parent

LOCAL_SETTINGS_FILE = ROOT_DIR / ".resumedetective.local.json"
LEGACY_DATA_DIR = ROOT_DIR / "data"


def _source_data_dir() -> Path:
    override = os.environ.get("RESUME_DETECTIVE_DATA_DIR", "").strip()
    if override:
        return Path(os.path.expandvars(override)).expanduser().resolve()

    try:
        settings = json.loads(LOCAL_SETTINGS_FILE.read_text(encoding="utf-8"))
        configured = str(settings.get("data_dir") or "").strip()
        if configured:
            return Path(os.path.expandvars(configured)).expanduser().resolve()
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        pass

    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local_app_data) if local_app_data else Path.home() / ".resumedetective"
    return (base / "ResumeDetective" / "Development").resolve()


# 便携版继续使用 EXE 旁 data；源码开发数据默认位于仓库外。
DATA_DIR = (ROOT_DIR / "data") if getattr(sys, "frozen", False) else _source_data_dir()
CONFIG_FILE = DATA_DIR / "config.json"
DB_FILE = DATA_DIR / "data.db"
APPLICATION_MIRROR_FILE = DATA_DIR / "秋招投递追踪.xlsx"
RESUMES_DIR = DATA_DIR / "Resumes"
ATTACHMENTS_DIR = DATA_DIR / "Attachments"
REASONIX_DATA_DIR = DATA_DIR / "reasonix"
SKILL_DIR = ROOT_DIR / "skills"
REASONIX_CLI_DIR = ROOT_DIR / "Reasonix Cli"
REASONIX_CLI_EXE = REASONIX_CLI_DIR / "reasonix.exe"


def ensure_data_directories() -> None:
    for directory in (DATA_DIR, RESUMES_DIR, ATTACHMENTS_DIR, REASONIX_DATA_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def migrate_legacy_data_if_needed() -> tuple[bool, str]:
    """首次切换到外置目录时只复制旧数据，不删除或覆盖原目录。"""
    if getattr(sys, "frozen", False) or DATA_DIR == LEGACY_DATA_DIR:
        return False, "无需迁移"
    if not LEGACY_DATA_DIR.is_dir() or not any(LEGACY_DATA_DIR.iterdir()):
        return False, "没有旧数据"
    if DATA_DIR.exists() and any(DATA_DIR.iterdir()):
        return False, "目标数据目录已有内容，未自动覆盖"
    try:
        DATA_DIR.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(LEGACY_DATA_DIR, DATA_DIR, dirs_exist_ok=False)
        return True, f"已复制旧数据到 {DATA_DIR}；原目录仍保留"
    except OSError as exc:
        return False, f"旧数据迁移失败：{exc}"


def resolve_data_path(stored_path: str | Path) -> Path:
    """解析数据库中的路径，兼容旧的 data/... 和绝对路径记录。"""
    candidate = Path(stored_path)
    if candidate.is_absolute():
        # 旧附件可能存了仓库 data 的绝对路径，外置后自动映射到新目录。
        try:
            relative = candidate.resolve().relative_to(LEGACY_DATA_DIR.resolve())
            migrated = DATA_DIR / relative
            if migrated.exists() or not candidate.exists():
                return migrated
        except (OSError, ValueError):
            pass
        return candidate

    parts = candidate.parts
    if parts and parts[0].lower() == "data":
        return DATA_DIR.joinpath(*parts[1:])
    return ROOT_DIR / candidate


def stored_data_path(path: str | Path) -> str:
    """以兼容格式保存托管文件路径，不把本机绝对路径写入数据库或 Excel。"""
    candidate = Path(path).resolve()
    try:
        relative = candidate.relative_to(DATA_DIR.resolve())
    except ValueError:
        return str(candidate)
    return (Path("data") / relative).as_posix()
