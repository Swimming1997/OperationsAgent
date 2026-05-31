# AGENTS.md

1. 使用仓库根目录的 `.venv`，Python 路径为 `..\.venv\Scripts\python.exe`（或仓库根 `.venv\Scripts\python.exe`）。
2. 读写文件统一使用 UTF-8；PowerShell / bat 脚本必须设置 UTF-8 输出，避免中文乱码。
3. 本目录只实现员工电脑 Local Agent 职责：注册、心跳、claim job、Chrome/CDP/Profile 管理、XHS 采集、normalize、HTTP JSON 上报。
4. 不 import `central_server.intelligence_engine.db`、`central_server.intelligence_engine.storage`、`central_server.intelligence_engine.services`、`central_server.intelligence_engine.main`，不直接访问中央数据库。
5. 正式 runtime 只通过中央 API 通信；legacy DB-coupled smoke tool 只允许放在 `scripts/dev_legacy/`。
6. 不保存或上传 Cookie 原文。Chrome Profile 保留在本机 `profiles/accounts/{profile_key}/`。
7. `references/MediaCrawler` 只作参考源码，不作为运行依赖。
8. `logs/`、`profiles/` 是运行数据，不作为源码。
