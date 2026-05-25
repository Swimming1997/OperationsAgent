# AGENTS.md

1. 使用仓库根目录的 `.venv`，Python 路径为 `..\.venv\Scripts\python.exe` 或绝对路径 `D:\AMiracle\.venv\Scripts\python.exe`。
2. 读写文件统一使用 UTF-8；PowerShell / bat 脚本必须设置 UTF-8 输出，避免中文乱码。
3. 本目录只实现中央服务器职责：FastAPI、Web 前端、数据库、Alembic、任务中心、Job 队列、调度、ingestion、用户角色、账号和规则中心。
4. 不 import `local_agent_runtime`，不管理员工电脑 Chrome，不直接操作 Local Agent profile。
5. Local Agent 只通过 HTTP JSON 调用中央 API；中央保留完整 Pydantic schemas 和 DB model。
6. `data/`、`logs/`、`frontend/node_modules/`、`frontend/dist/` 是运行或生成数据，不作为源码。
