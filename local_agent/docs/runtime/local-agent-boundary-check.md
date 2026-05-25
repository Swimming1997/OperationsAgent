# Local Agent Boundary Check

## 扫描范围

- `D:\AMiracle\local_agent\local_agent_runtime`
- `D:\AMiracle\local_agent\scripts\run_local_agent.py`
- `D:\AMiracle\local_agent\scripts\start.ps1`
- `D:\AMiracle\local_agent\tests`

`D:\AMiracle\local_agent\scripts\dev_legacy` 不属于正式 runtime，单独列为 legacy 例外。

## 禁止项

- `central_server`
- `intelligence_engine.db`
- `intelligence_engine.storage`
- `intelligence_engine.services`
- `SessionLocal`
- `sqlalchemy`
- `alembic`
- `Repository`

## 执行命令

```powershell
rg -n "central_server|intelligence_engine\.db|intelligence_engine\.storage|intelligence_engine\.services|SessionLocal|sqlalchemy|alembic|Repository" local_agent\local_agent_runtime local_agent\scripts\run_local_agent.py local_agent\scripts\start.ps1 local_agent\tests --glob "!**/dev_legacy/**" --glob "!**/__pycache__/**"
```

## 发现结果

未发现命中。正式 Local Agent runtime、正式启动脚本和正式测试不包含中央 DB / storage / services 依赖，也不直接引用 SQLAlchemy、SessionLocal、Alembic 或 Repository。

小红书正式采集、signed API client、probe、normalizer 和审计框架位于：

- `local_agent\local_agent_runtime\connectors\xhs\`
- `local_agent\local_agent_runtime\audit\`

Local Agent 与中央之间仍只通过 HTTP JSON 协议通信，不 import `central_server` 或中央 DB/service/repository。

## Legacy 例外

以下历史 DB-coupled smoke runner 保留在 `scripts/dev_legacy/`，不属于正式 runtime：

- `local_agent\scripts\dev_legacy\fake_runner.py`
- `local_agent\scripts\dev_legacy\xhs_comment_probe_runner.py`
- `local_agent\scripts\dev_legacy\xhs_creator_monitor_runner.py`
- `local_agent\scripts\dev_legacy\xhs_detail_probe_runner.py`
- `local_agent\scripts\dev_legacy\xhs_intelligence_loop_runner.py`
- `local_agent\scripts\dev_legacy\xhs_main_chain_smoke_runner.py`
- `local_agent\scripts\dev_legacy\xhs_manual_comment_probe_runner.py`
