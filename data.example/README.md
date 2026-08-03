# 本地数据目录模板

ResumeDetective 首次启动会在 EXE 旁自动创建 `data`，通常不需要手工复制本目录。

如需直接配置 AI，可把 `.env.example` 复制为 `data/.env`，再填写密钥。真实 `.env`、数据库、简历和日志都不得提交 Git；手动与自动备份统一保存在 EXE 同级的 `backups`，同样不会进入 Git。

`sample-data.json` 提供一套完全虚构的投递、意向、待办、个人资料与经历案例。正式打包脚本会据此生成发布 ZIP 内的全新演示数据库；本地测试 EXE 和已有 `data` 不会自动导入它。
