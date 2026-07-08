# Resume Detective (简历侦探)

> \*\*本地优先的 AI 求职工作台\*\* — 投递管理 · 意向追踪 · AI 简历助手  
> 面向秋招/社招的 100% 离线桌面工具。

\---

## ✨ 功能

|功能|说明|
|-|-|
|📋 **泳道看板**|7 列状态泳道，鼠标拖拽切换阶段|
|📊 **表格视图**|信息密度更高的表格模式，支持排序/筛选|
|📝 **投递详情**|双击卡片弹出详情，含城市/附件/JD/自动保存|
|📎 **附件管理**|每个投递可挂载多个附件，一键打开/回收站删除|
|🏢 **意向公司**|独立页面维护 JD 池，优先级排序，一键转投递|
|🤖 **AI 助手**|DeepSeek 流式对话，JD 分析/简历初稿/匹配分析/经历重写/自我介绍|
|📚 **资料库**|个人经历碎片管理 + 个人信息表单|
|🛠 **工具集成**|PDF→图片、文档→图片版 PDF 内嵌工具|
|🔒 **API Key 加密**|Windows DPAPI 加密存储，不写明文|

## 🚀 快速开始

### 方式一：下载 EXE（推荐）

1. 从 [Releases](https://github.com/your-username/ResumeDetective/releases) 下载最新版 `ResumeDetective.zip`
2. 解压到任意目录，进入 `ResumeDetective/` 文件夹，运行 `ResumeDetective.exe`
3. （可选）将 [Reasonix CLI](https://github.com/your-username/reasonix-cli) 放入 `Reasonix Cli/reasonix.exe` 获得增强 AI 能力

### 方式二：源码运行

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/ResumeDetective.git
cd ResumeDetective

# 2. 安装依赖
pip install PyQt6 openpyxl PyMuPDF requests Pillow

# 3. 启动
python main.py
```

## ⚙️ AI 配置

AI 助手支持两种模式：

|模式|说明|需要|
|-|-|-|
|**API 直连（推荐）**|直接调用 DeepSeek API|DeepSeek API Key（AI 页面设置）|
|**Reasonix CLI**|本地 CLI 调用，管理多个 Provider|自行下载 Reasonix CLI 到 `Reasonix Cli/reasonix.exe`|

## 🗂 项目结构

```
ResumeDetective/
├── main.py                 # 入口
├── resumedetective/        # 核心包（20 个模块）
│   ├── \_\_init\_\_.py
│   ├── main\_window.py      # 主窗口（5 Tab）
│   ├── board\_widget.py     # 泳道看板
│   ├── table\_view.py       # 表格视图
│   ├── detail\_dialog.py    # 投递详情弹窗
│   ├── dialogs.py          # 新增投递弹窗
│   ├── job\_targets\_widget.py # 意向公司管理
│   ├── materials\_widget.py # 资料库
│   ├── ai\_service.py       # AI 服务
│   ├── cli\_ai.py           # Reasonix CLI 适配
│   ├── config\_manager.py   # 配置管理
│   ├── secure\_store.py     # 加密存储（DPAPI）
│   ├── db\_manager.py       # SQLite CRUD
│   ├── chat\_history.py     # 聊天历史
│   ├── io\_export.py        # Excel 导入导出
│   ├── file\_ops.py         # 回收站删除
│   ├── tools\_pdf2img.py    # PDF→图片
│   ├── tools\_imgpdf.py     # 文档→图片版 PDF
│   ├── paths.py            # 路径常量
│   └── models.py           # 数据类
├── install.bat             # 一键安装脚本
├── ResumeDetective.spec    # PyInstaller 打包配置
└── data/                   # 自动创建
    ├── config.json
    ├── data.db
    ├── Resumes/
    ├── chat\_history/
    ├── Attachments/
    └── reasonix/
```

## 🧪 技术栈

* **Python 3.14** / **PyQt6** / **SQLite**
* **openpyxl**（Excel 导入导出）
* **PyMuPDF**（PDF 处理）
* **Pillow**（图片转换）
* **requests**（API 调用）
* **comtypes**（Windows 回收站）

## 📄 许可

MIT License

