"""路径常量：所有数据统一存储在 data/ 目录下"""
import sys
from pathlib import Path

# 项目根目录
#  - 源码模式：__file__ 所在目录（ResumeDetective/）
#  - PyInstaller exe 模式：exe 所在目录（避免写入只读的 _internal/）
if getattr(sys, 'frozen', False):
    ROOT_DIR = Path(sys.executable).parent
else:
    ROOT_DIR = Path(__file__).parent.parent  # 包路径 → 项目根目录

# 数据目录
DATA_DIR = ROOT_DIR / "data"

# 配置文件（普通配置，不含敏感信息）
CONFIG_FILE = DATA_DIR / "config.json"

# 数据库文件
DB_FILE = DATA_DIR / "data.db"

# 简历文件存储目录
RESUMES_DIR = DATA_DIR / "Resumes"

# 附件目录（按 application_id 分目录）
ATTACHMENTS_DIR = DATA_DIR / "Attachments"

# Reasonix 本地数据目录（配置、日志等）
REASONIX_DATA_DIR = DATA_DIR / "reasonix"

# Skill 目录（可选，用于 Reasonix CLI 扩展）
SKILL_DIR = ROOT_DIR / "skills"

# Reasonix CLI 执行文件目录（应用内可控副本）
REASONIX_CLI_DIR = ROOT_DIR / "Reasonix Cli"
REASONIX_CLI_EXE = REASONIX_CLI_DIR / "reasonix.exe"
