# Central Server

中央服务器包含 FastAPI、Web 前端、数据库、Alembic migration、任务中心、Job 队列和 ingestion API。

## 启动与停止

启动：

```powershell
cd central_server
.\scripts\start.ps1
```

停止：

```powershell
cd central_server
.\scripts\stop.ps1
```

重启：

```powershell
cd central_server
.\scripts\restart.ps1
```

中央脚本只管理 FastAPI `8000` 和 Vite `5173`，不停止 Local Agent，不停止普通 Chrome。

默认 SQLite 数据库路径为 `central_server\data\intelligence_engine.db`。`data/` 和 `logs/` 是运行数据。

## 本地开发（默认 SQLite，无需 Docker）

1. 复制环境变量（可选，不复制则使用代码内默认值）：

```powershell
cd central_server
Copy-Item .env.example .env
```

2. 应用数据库迁移：

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
```

3. 跑测试：

```powershell
..\.venv\Scripts\python.exe -m pytest
```

`INTEL_ENGINE_DATABASE_URL` 未设置时即为 `sqlite:///./data/intelligence_engine.db`。万级列表 P95 压测脚本可在 SQLite 上做冒烟（见 `tests/test_intelligence_list_perf_smoke.py`）；计划中的 1 万条 P95 盖章需 PostgreSQL 时再启 `docker compose` 并改连接串，日常功能开发不必依赖。

生产 PostgreSQL 的环境变量、迁移、备份校验和恢复演练见
`docs/operations/postgresql-production.md`。

## 前端角色与导航

| 页面 | 路径 | 可见角色 |
|------|------|----------|
| 情报中心 | `/intelligence` | operator, sales, admin, supervisor |
| 对标作品库 | `/reference-library` | operator, sales, admin, supervisor |
| 任务模板 | `/tasks` | operator, admin, supervisor |
| 我的运行 | `/my-runs` | operator |
| 运行中心 | `/operations` | admin, supervisor |
| 账号管理 | `/accounts` | operator, admin, supervisor |
| Agent 管理 | `/agents` | admin, supervisor |
| 组织管理 | `/organization` | admin, supervisor |

当前文档入口：`docs/README.md`。

阶段口径：

- P0/P1 已验收基线：见 `docs/guidance/p0-intelligence-center-design-v1.md`、`docs/guidance/p0-acceptance-results.md`、`docs/guidance/p1-development-plan.md`、`docs/guidance/p1-acceptance-results.md`。
- P2 当前开发入口：`docs/guidance/p2-development-plan.md`。P2 目标是 Local-First，本文件仍描述当前中央服务的启动与运行方式。
