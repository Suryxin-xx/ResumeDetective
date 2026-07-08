# 打包说明

## 前置条件

```bash
pip install pyinstaller
```

## 打包命令

```bash
cd ResumeDetective
pyinstaller ResumeDetective.spec
```

产物在 `dist/ResumeDetective/` 目录，包含 `ResumeDetective.exe` 及所有依赖。

## 数据结构说明

程序启动时会自动在 exe **旁边** 创建 `data/` 目录（含 `data.db`、`config.json`、`Resumes/` 子目录等）。

源码运行时：`data/` 创建在源码目录下。
Exe 运行时：`data/` 创建在 exe 所在目录下（见 `paths.py` 的 `sys.frozen` 判断）。

## 文件清单（GitHub 仓库）

| 文件 | 说明 |
|------|------|
| `main.py` | 入口 |
| `resumedetective/main_window.py` | 主窗口（5 Tab） |
| `resumedetective/board_widget.py` | 泳道看板 |
| `resumedetective/table_view.py` | 表格视图 |
| `resumedetective/detail_dialog.py` | 投递详情弹窗（含附件区） |
| `resumedetective/dialogs.py` | 新增投递弹窗 |
| `resumedetective/job_targets_widget.py` | 意向公司管理 |
| `resumedetective/materials_widget.py` | 资料库 |
| `resumedetective/ai_service.py` | AI 服务 |
| `resumedetective/cli_ai.py` | Reasonix CLI 适配 |
| `resumedetective/chat_history.py` | 聊天历史 |
| `resumedetective/io_export.py` | Excel 导入导出 |
| `resumedetective/config_manager.py` | 配置管理 |
| `resumedetective/secure_store.py` | DPAPI 加密存储 |
| `resumedetective/db_manager.py` | SQLite CRUD |
| `resumedetective/file_ops.py` | 回收站删除 |
| `resumedetective/models.py` | 数据类 |
| `resumedetective/paths.py` | 路径常量 |
| `resumedetective/tools_pdf2img.py` | PDF→图片 |
| `resumedetective/tools_imgpdf.py` | 图片→PDF |
| `install.bat` | 依赖安装脚本 |
| `ResumeDetective.spec` | PyInstaller 配置 |
| `data/config.json` | 默认配置模板 |
| `data/` | 空目录占位 |
| `.gitignore` | Git 忽略规则 |
| `README.md` | 项目说明 |
| `PACKAGING.md` | 本文件 |

## GitHub Release 建议

1. 打包后压缩 `dist/ResumeDetective/` 为 `ResumeDetective-v1.0.zip`
2. 在 GitHub Releases 页面上传 zip 作为 release asset
3. 源码仓库只跟踪 `.py` + 文档，不提交打包产物
