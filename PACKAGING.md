# ResumeDetective v4 发布说明

## 单根目录结构

| 目录 | 用途 | 是否提交 Git |
| --- | --- | --- |
| `Gadgets\ResumeDetective` | 唯一源码仓库，也是本机测试根目录 | 是（仅跟踪源码） |
| `ResumeDetective\data` | 真实数据库、简历、`.env` 与配置 | 否 |
| `ResumeDetective\backups` | 自动/手动备份与唯一 Python v3 归档 | 否 |
| `ResumeDetective\releases\vX.Y.Z` | GitHub Release 发布物 | 否 |

日常只在 `Gadgets\ResumeDetective` 提交 Git；`.gitignore` 与安全脚本会拦截运行数据、根目录 EXE、备份和发布物。

## 提交源码前

```powershell
cd E:\Agent\Project\Job\Gadgets\ResumeDetective
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_repository_safety.ps1
git status
git add -A
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_repository_safety.ps1 -Staged
git diff --cached --check
```

确认没有 `data`、`.env`、数据库、简历、备份、Reasonix CLI 或发布 ZIP 后，再提交到当前维护的 `main` 分支。Python v3.3.1 历史源码保留在 `main-python`，不要将新版 PR 合并回该分支。

## 一键打包

双击或在终端运行兼容入口：

```powershell
.\scripts\atuo.bat -Version 4.3.1
```

也可以直接运行实际构建脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1 -Version 4.3.1
```

脚本依次执行仓库安全扫描、前端构建、Go 测试、`go vet`、Windows GUI EXE 构建、图标/版本资源写入、ZIP 压缩和 SHA-256 生成。`atuo.bat` 如果发现同版本目录，会在新包完整生成后把旧目录移入 `releases\archive\vX.Y.Z-时间戳`，不会覆盖或删除旧发布物；构建失败时旧目录保持原位。

直接运行 `build_windows.ps1` 时默认仍会拒绝覆盖。确实需要重建同一版本可显式使用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1 -Version 4.3.1 -ArchiveExisting
```

## 输出结构

```text
ResumeDetective\releases\v4.3.1\
├── ResumeDetective\
│   ├── ResumeDetective.exe
│   ├── ResumeDetective.exe.sha256
│   ├── README.md
│   ├── LICENSE
│   ├── data\
│   │   └── resume_detective.db（由虚构样例生成，可在总览一键清除）
│   ├── screenshots\
│   └── data.example\
├── ResumeDetective-windows-x64.zip
└── ResumeDetective-windows-x64.zip.sha256
```

## GitHub Release 上传什么

只需上传：

1. `ResumeDetective-windows-x64.zip`
2. `ResumeDetective-windows-x64.zip.sha256`

不要上传整个 `releases\v4.3.1\ResumeDetective` 文件夹、真实 `data`、`backups` 或 `.env`。GitHub 会自动提供 Source code ZIP/TAR，不需要再手工打源码包。

自动更新器按 `ResumeDetective + windows/win + x64/amd64 + .zip` 识别资产，因此不要随意修改 ZIP 名称。发布后应在一台能访问 GitHub API 的机器上先检查更新，再验证下载、校验、替换与回滚。

## 本机测试版

本机只使用仓库根目录的 `ResumeDetective.exe`。修改后运行 `scripts\build_local.ps1` 生成测试 EXE，它始终读取同级 `data`；正式打包不会覆盖本机测试 EXE 或数据。升级前仍建议在设置页点击“立即备份”。
