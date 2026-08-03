# ResumeDetective

ResumeDetective 是一个本地优先的 Windows 求职进度工作台，用来管理意向岗位、投递流转、待办、面试复盘、关联简历与 JD。v4 由 Go + React 重构，发布版是单个 EXE，不要求用户安装 Python、Go、Node.js 或 SQLite。

<p align="center"><img src="screenshots/v4-overview.png" alt="ResumeDetective 总览" width="100%"></p>

## 主要功能

- 表格化投递管理：按环节、状态、标签和关键词筛选，在当前行展开编辑。
- 专注型总览：集中展示需要行动的事项、四组流程进展和最近状态变化，避免被过细的阶段图表淹没。
- 明亮高对比界面：采用语义化颜色、较大正文字号与固定页脚，长时间使用仍能快速找到重点。
- 流转详情：保留“已投递 → 测评 → 业务面试 → 终止”等历史，便于复盘在哪一环节流失。
- 意向清单：先收集公司与岗位，确认后可一键转为正式投递。
- 简历与 JD 归档：岗位关闭后仍可查看当时的 JD；简历汇总支持列表/卡片切换，只呈现岗位、标签和对应简历等核心信息。
- 行动清单和面试复盘：将后续准备与具体投递关联。
- 本地 AI：支持 DeepSeek API 直连与 Reasonix CLI 两种模式，只提供 JD 匹配、简历建议和面试准备等求职相关能力。
- 个人资料与经历库：项目、实习、校园经历只维护一次，AI 分析自动结合真实素材，不必重复粘贴。
- 便携数据与备份：数据位于根目录 `data`，备份统一进入 `backups`，兼容 Python v3 数据迁移与错位数据自修复。
- Excel 单向镜像：新增、修改、删除投递或记录面试后，自动重建 `data/秋招投递追踪.xlsx`；SQLite 仍是唯一事实源，Excel 用于脱离网页快速查看与筛选。
- 托盘、自启与更新：后台静默运行，可选登录 Windows 后启动，可从托盘或设置页重启、退出，并支持可信 Release 更新。

<table>
  <tr><td width="50%"><strong>投递管理</strong></td><td width="50%"><strong>个人资料与经历库</strong></td></tr>
  <tr><td><img src="screenshots/v4-applications.png" alt="投递管理"></td><td><img src="screenshots/v4-profile.png" alt="个人资料与经历库"></td></tr>
</table>

## 下载与使用

1. 从 [GitHub Releases](https://github.com/Suryxin-xx/ResumeDetective/releases) 下载 `ResumeDetective-windows-x64.zip`。
2. 可用同名 `.sha256` 校验压缩包，然后解压到自己有写入权限的文件夹。
3. 双击 `ResumeDetective.exe`。发布包自带一套完全虚构的演示数据，并打开 `http://127.0.0.1:8765`。
4. 关闭浏览器不会退出后台服务；请从托盘菜单选择“退出”，或在设置页退出。

首次打开可直接浏览完整流程。准备记录真实求职信息时，在总览点击“清除演示数据”；程序只删除带发布演示标记的记录，不会删除之后自行创建的数据。本地源码测试版不会自动注入演示数据。

端口默认固定为 `8765`，可在设置中修改，保存后重启生效。服务只监听 `127.0.0.1`，不会向局域网开放。

## 数据与迁移

```text
ResumeDetective.exe
data/
  resume_detective.db
  秋招投递追踪.xlsx
  config.json
  .env
  resumes/
  attachments/
  updates/
backups/
  automatic-*.db
  ResumeDetective-Python-v3-legacy.zip
releases/
  vX.Y.Z/
```

- v4 不直接修改 Python v3 数据库。设置页的“一键导入”会先备份，再把旧数据复制到新库。
- 正式 ZIP 内的 `data/resume_detective.db` 只含 `data.example/sample-data.json` 生成的虚构案例；本地构建与已有数据目录不会被填充。
- 更新数据库结构时由程序执行兼容迁移；仍建议在升级前点击“立即备份”。
- Excel 镜像由程序自动生成，不建议直接回写；如果同步时工作簿正被 Excel 占用，关闭文件后重启 ResumeDetective 即会再次同步。
- `data`、`.env`、数据库、简历和备份已被 `.gitignore` 与提交前安全检查双重拦截。
- `.env` 只是避免密钥进入 Git，并非加密保险箱；不要共享该文件或整个 `data` 目录。

## AI 配置

### DeepSeek API

在“设置 → AI Provider”中选择 DeepSeek API，填写 API Key 并测试连接。密钥写入本机 `data/.env`，不会返回网页，也不会写入应用日志。设置页可手动查询账户余额；只有点击时才请求 DeepSeek，余额与查询时间不会保存。只有用户主动点击 AI 分析时，相关 JD、个人资料与经历库文本才会发送到配置的 API；手机号、出生日期等敏感字段不会加入默认分析上下文。

### Reasonix CLI

自行从 [DeepSeek-Reasonix](https://github.com/esengine/DeepSeek-Reasonix) 下载 Reasonix，在设置中选择其可执行文件。ResumeDetective 通过 CLI 的非交互 JSON 输出调用它；Reasonix 仍使用自己的模型与密钥配置。设置页可查看 Reasonix 官方 Release 更新。

AI 输出仅作为求职材料建议，不会编造经历，也不应代替用户核对事实。

## 从源码运行与打包

开发环境需要 Go 1.25+、MinGW GCC、Node.js 24+。最终发布包不包含这些开发依赖。

```powershell
npm --prefix frontend ci
npm --prefix frontend run build
go test ./...
go run ./cmd/resumedetective --data-dir .\local-data --no-browser
```

Windows 正式构建：

```powershell
.\scripts\atuo.bat -Version 4.1.0
```

脚本会执行安全扫描、前端构建、Go 测试与静态检查，写入图标和版本信息，再输出 ZIP 与 SHA-256。若同版本目录已存在，一键入口会在新包构建成功后将旧目录归档到 `releases/archive`，不会覆盖或删除旧发布物。直接调用 `build_windows.ps1` 默认仍拒绝覆盖，可显式添加 `-ArchiveExisting` 重建同一版本。

## 安全边界

- 本机 HTTP 接口绑定 `127.0.0.1`，修改类请求检查同源信息。
- 更新只信任固定 GitHub 仓库、HTTPS 下载地址和 Release 资产 SHA-256 digest。
- 简历与数据库始终由用户管理；卸载程序不会主动删除 `data`。
- 本项目当前未提供代码签名。首次下载时 Windows 可能显示未知发布者，应从官方 Release 下载并核对 SHA-256。

## 配套工具

PDF 转换功能已拆分为独立小工具，减少 ResumeDetective 的体积与攻击面：

- [ImagePDFConverter](https://github.com/Suryxin-xx/ImagePDFConverter)
- [Word_PDF2Image](https://github.com/Suryxin-xx/Word_PDF2Image)

## 开发与致谢

- 开发者：[Suryxin-xx](https://github.com/Suryxin-xx) · Finlandxxu@outlook.com
- 仓库：[Suryxin-xx/ResumeDetective](https://github.com/Suryxin-xx/ResumeDetective)
- ChatGPT 与 DeepSeek 参与需求分析、代码实现和测试，最终取舍与发布由开发者人工负责。
- AI 接入参考并兼容 [esengine/DeepSeek-Reasonix](https://github.com/esengine/DeepSeek-Reasonix) 的 CLI 使用方式。
- Excel 单向镜像使用 [Excelize](https://github.com/xuri/excelize) 生成，避免要求用户安装 Office 或 Python 运行库。
- 产品与网页交互设计参考了 [xuuuu-cpu/offerFlow-llm-feature](https://github.com/xuuuu-cpu/offerFlow-llm-feature) 的部分思路；代码实现为本项目独立重构。
- 明亮主题的语义色层级参考了 [GitHub Primer](https://primer.style/) 与 [Microsoft Fluent 2](https://fluent2.microsoft.design/design-tokens) 的公开设计令牌方法，未复制组件代码。

## License

[MIT](LICENSE)
