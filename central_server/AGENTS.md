# AGENTS.md

1. 使用仓库根目录的 `.venv`，Python 路径为 `..\.venv\Scripts\python.exe`（或仓库根 `.venv\Scripts\python.exe`）。
2. 读写文件统一使用 UTF-8；PowerShell / bat 脚本必须设置 UTF-8 输出，避免中文乱码。
3. 本目录只实现中央服务器职责：FastAPI、Web 前端、数据库、Alembic、任务中心、Job 队列、调度、ingestion、用户角色、账号和规则中心。
4. 不 import `local_agent_runtime`，不管理员工电脑 Chrome，不直接操作 Local Agent profile。
5. Local Agent 只通过 HTTP JSON 调用中央 API；中央保留完整 Pydantic schemas 和 DB model。
6. `data/`、`logs/`、`frontend/node_modules/`、`frontend/dist/` 是运行或生成数据，不作为源码。
7. 必须遵循仓库根 `AGENTS.md` 的稳定性、可维护性、可拓展性强约束。
8. 新增产品 API 不得继续堆入 `api/product_routes.py`；应放入对应 `api/product_*_routes.py` 或独立 route 模块，并复用 `api/product_common.py` 中共享 helper。
9. 新增 DB model 不得继续堆入 `db/models.py`；应放入对应领域模型文件，并仅在 `db/models.py` 中做兼容导出或集中索引注册。
10. Job 生命周期相关改动必须通过 `storage/repositories/job_repository.py` 或 `intelligence_engine/jobs/`，不得在路由或服务中直接写状态字段。
