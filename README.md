<div align="center">

# 📋 Resume Detective

**本地优先的求职工作台** — 投递追踪 / 意向公司 / 资料库 / AI 辅助，一站式搞定

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

---

</div>

## 📌 简介

Resume Detective 是一个**本地优先**的求职管理桌面工具，帮助你在秋招/社招中高效管理投递进度。数据全部存储在本地 SQLite，不联网也能使用全部核心功能。

### 它能做什么？

- 📋 **投递看板** — 拖拽切换状态，一目了然所有投递进度
- 🗂️ **意向公司** — 收集目标公司与 JD，一键转为投递记录
- 📚 **资料库** — 维护个人简历素材，生成简历初稿
- 🤖 **AI 助手** — JD 分析、匹配度评估、简历重写
- 🛠️ **小工具** — PDF ⇄ 图片转换、Excel 导入导出

## ✨ 功能特性

| 模块 | 特性 | 说明 |
|------|------|------|
| 📋 **投递看板** | 🎯 泳道视图 | 9 列状态（已投递→筛选→面试→…→已入职），拖拽切换 |
| | 📊 表格视图 | 高密度列表，支持搜索过滤与列排序 |
| | 📎 附件管理 | 每份投递可添加简历/作品/反馈附件，删除自动进回收站 |
| | 🏙️ 城市字段 | 记录目标城市，看板卡片 tooltip 实时展示 |
| 🎯 **意向公司** | 📋 目标池 | 维护目标公司与岗位 JD，支持优先级标记 |
| | 🔄 一键转投递 | 分析完成直接转为投递记录 |
| 📚 **资料库** | 👤 个人信息 | 姓名/学校/专业/技能/目标城市等，AI 生成时自动引用 |
| | 📝 经历碎片 | 项目/竞赛/实习经历，支持标签分类，随时调用 |
| 🤖 **AI 助手** | 🔗 API 直连 | 支持 DeepSeek API，Key 本地加密保存（DPAPI） |
| | 🧩 4 个业务按钮 | JD 分析 / 简历初稿 / 重写经历 / 自我介绍，一键生成 |
| | 🗣️ 自由对话 | 直接提问，上下文关联投递卡片或意向公司 |
| 🛠️ **工具** | 📄 PDF → 图片 | 将 PDF 每页导出为图片（可选项） |
| | 🖼️ 图片 → PDF | 图片合成为图片版 PDF |
| | 📊 Excel 导入 | 批量导入投递记录 |

## 🖥️ 界面截图

> 截图请放入 `screenshots/` 文件夹。

| 页面 | 预览 |
|------|------|
| 📋 投递看板 | `screenshots/board.png` |
| 📚 资料库 | `screenshots/materials.png` |
| 🤖 AI 助手 | `screenshots/ai.png` |
| 🎯 意向公司 | `screenshots/targets.png` |
| 🛠️ 小工具 | `screenshots/tools.png` |

## 📦 下载

> 前往 [Releases](https://github.com/Suryxin-xx/ResumeDetective/releases) 下载最新版

| 文件 | 说明 |
|------|------|
| `ResumeDetective_v1.0.zip` | 完整发布包，解压即用（推荐） |

**系统要求：** Windows 10/11，64 位

> ⚠️ 不要只拿走 `ResumeDetective.exe`，请将整个文件夹解压后再运行。
> 首次使用需自行输入 API Key，程序会在本机加密保存。

## 🚀 快速开始

### 普通用户

1. 从 [Releases](https://github.com/Suryxin-xx/ResumeDetective/releases) 下载最新版 zip
2. 解压到任意文件夹
3. 双击运行 `ResumeDetective.exe`
4. 第一次使用 → 进入 AI 页面 → 输入 DeepSeek API Key

### 源码运行

适合有 Python 环境的开发者：

```bash
# 1. 克隆仓库
git clone https://github.com/Suryxin-xx/ResumeDetective.git
cd ResumeDetective

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行
python main.py
```

> Python 版本要求：3.11 及以上

## 🤖 AI 配置

程序支持两种 AI 通道：

| 方式 | 说明 | 配置 |
|------|------|------|
| **API 直连** | ✅ 推荐，配置最简单 | 输入 DeepSeek API Key 即可 |
| **Reasonix CLI** | ⚡ 可选增强模式 | 将 `reasonix.exe` 放入 `Reasonix Cli/` 目录 |

- 发布包不会内置任何 API Key
- 用户第一次输入后，Key 使用 Windows DPAPI 加密保存
- Reasonix CLI 仅识别程序目录内的可控副本，不扫描系统路径

## 🏗️ 技术栈

| 组件 | 用途 |
|------|------|
| [Python](https://www.python.org/) | 编程语言 |
| [PyQt6](https://pypi.org/project/PyQt6/) | GUI 框架 |
| [SQLite](https://www.sqlite.org/) | 本地数据库 |
| [requests](https://pypi.org/project/requests/) | AI API 调用 |
| [openpyxl](https://pypi.org/project/openpyxl/) | Excel 导入导出 |
| [PyMuPDF](https://pypi.org/project/PyMuPDF/) | PDF 处理 |
| [Pillow](https://python-pillow.org/) | 图片处理 |
| [comtypes](https://pypi.org/project/comtypes/) | Windows COM 接口 |
| [PyInstaller](https://pyinstaller.org/) | 打包为 exe |

## 🗂️ 项目结构

```
ResumeDetective/
├── main.py                 # 程序入口
├── main_window.py          # 主窗口（5 Tab 导航）
├── board_widget.py         # 投递看板（泳道视图 + 卡片拖拽）
├── table_view.py           # 表格视图
├── detail_dialog.py        # 投递详情弹窗（含附件管理）
├── dialogs.py              # 通用对话框
├── materials_widget.py     # 资料库 + 个人信息
├── job_targets_widget.py   # 意向公司管理
├── ai_service.py           # AI 服务（流式 API + 脱敏 + Prompt 组装）
├── cli_ai.py               # Reasonix CLI 适配层
├── db_manager.py           # 数据库管理（6 张表 + 迁移）
├── config_manager.py       # 配置管理
├── secure_store.py         # 加密存储（DPAPI）
├── chat_history.py         # 聊天记录
├── io_export.py            # Excel 导入导出
├── file_ops.py             # 文件操作（回收站、附件）
├── tools_pdf2img.py        # PDF → 图片
├── tools_imgpdf.py         # 图片 → PDF
├── paths.py                # 路径常量
├── scripts/                # 构建/发布脚本
├── screenshots/            # 截图
└── data/                   # 运行时数据（不提交 Git）
```

## 🔨 自行打包

```powershell
# 1. 安装依赖
pip install -r requirements.txt

# 2. 一键打包（需 PyInstaller）
.\scripts\build_release.ps1
```

打包后的文件位于 `build/release-src/`，脚本会自动排除本机测试数据、聊天记录和密钥。

## 📄 许可证

本项目使用 [MIT License](LICENSE) — 欢迎 fork、修改、分发。

## 🤝 贡献

有问题或建议？欢迎提交 [Issue](https://github.com/Suryxin-xx/ResumeDetective/issues) 或 Pull Request。

---

<div align="center">

**如果这个工具对你有帮助，欢迎 ⭐ Star 支持！**

</div>
