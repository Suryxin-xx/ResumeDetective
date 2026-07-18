# 本地数据模板

这个目录只用于说明数据结构，可以安全提交到 GitHub；程序不会在这里保存真实数据。

源码模式下，数据库、简历、Excel 镜像、聊天记录和 API Key 默认保存在：

```text
%LOCALAPPDATA%\ResumeDetective\Development
```

开发者可以在仓库根目录创建不会被 Git 跟踪的 `.resumedetective.local.json`：

```json
{
  "data_dir": "D:\\PrivateData\\ResumeDetective"
}
```

也可以使用环境变量 `RESUME_DETECTIVE_DATA_DIR`。优先级为：环境变量、本地配置文件、系统默认目录。

API Key 由 Windows DPAPI 加密后写入个人数据目录的 `secret.json.enc`。Reasonix 调用时，程序会在同一外置目录的 `reasonix/.env` 中生成 CLI 所需变量；这两个文件都不会进入源码仓库。
