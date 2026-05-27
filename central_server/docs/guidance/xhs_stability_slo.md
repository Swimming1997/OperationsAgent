# XHS 引擎稳定性 SLO（阶段 6）

## 指标口径

| 指标 | 目标 | 说明 |
|------|------|------|
| 任务成功率 | >= 90% | 推荐流 / 搜索 / 详情 / 评论四类 job，`SUCCESS + PARTIAL_SUCCESS` / 终态 |
| 登录失效停派 | 5 分钟内 | 账号 `auth_status` 进入失效态后不再派新 job（由账号状态机保障） |
| Stale running job | 30 分钟内处理 | `POST /api/operations/jobs/fail-stale-running` 或调度入口 |
| 错误码 | 复用 `ErrorCode` | 运行中心展示 `last_error_code` / message |

## 本地报告脚本

```powershell
cd central_server
# 默认 SQLite（无需 Docker）：
..\.venv\Scripts\python.exe scripts/xhs_slo_report.py --window-hours 24

# 可选：连接 docker compose Postgres
# $env:INTEL_ENGINE_DATABASE_URL = "postgresql+psycopg://intel:intel@localhost:55432/intelligence_engine"
```

JSON 输出：

```powershell
..\.venv\Scripts\python.exe scripts/xhs_slo_report.py --window-hours 24 --json
```

## 验收夹具（无 Local Agent 历史时）

```powershell
..\.venv\Scripts\python.exe scripts/seed_xhs_slo_fixture.py --per-type 55 --success-rate 0.92
..\.venv\Scripts\python.exe scripts/xhs_slo_report.py --window-hours 24
```

每类 job ≥50 条终态、成功率可调；**生产环境**仍应以 Agent 实跑数据为准（见 `p0-acceptance-results.md`）。

## 探针与压测

- 详情/评论探针：`tests/test_xhs_detail_probe.py`、`tests/test_xhs_comment_probe.py`
- 主链路 smoke：`scripts/dev_legacy/local_agent_db_runners/xhs_main_chain_smoke_runner.py`（需 Local Agent 环境）

## 运行中心

- 失败 job 列表：`GET /api/operations/jobs`
- 批量标记超时 running：`POST /api/operations/jobs/fail-stale-running`
