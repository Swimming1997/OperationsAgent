# Local Agent Runtime V1

> 员工侧精简版见：`local_agent/docs/runtime/local-agent-runtime-v1.md`。本文档为中央侧完整说明。

## 架构

Local Agent Runtime 是员工电脑上的常驻执行端。它只保存本机浏览器连接信息，不上传真实 Cookie。

运行链路：

```text
Task Template / Scheduler
-> Job
-> Local Agent claim
-> XHS connector
-> ingestion API
-> Job complete/fail
-> Intelligence Pool
```

## 启动

在 `local_agent` 目录下，使用项目虚拟环境：

```powershell
cd local_agent
..\.venv\Scripts\python.exe scripts\run_local_agent.py --config configs\local_agent.employee.example.toml
```

只执行一轮 claim 后退出：

```powershell
..\.venv\Scripts\python.exe scripts\run_local_agent.py --config configs\local_agent.employee.example.toml --once
```

一键脚本（推荐）：

```powershell
cd local_agent
.\scripts\start.ps1
```

日志默认写入：

```text
local_agent/logs/local_agent/local_agent.log
```

## Local Bridge

Local Agent 默认启动 Local Bridge HTTP 服务，供运营端「登记本地 Agent」发现本机设备。

- 默认端口：`18765`（占用时自动递增至 `18774`）
- 健康检查：`GET http://127.0.0.1:18765/healthz`
- CLI 覆盖：`--bridge-port`、`--bridge-token`、`--disable-bridge`

## 本地配置文件

示例文件：

```text
local_agent/configs/local_agent.employee.example.toml
local_agent/configs/local_agent.example.toml
```

核心字段：

```toml
center_url = "http://127.0.0.1:8000"
agent_id = ""
device_name = "WIN-1"
machine_fingerprint = "win-1-demo-fingerprint"
project_root = "."
claim_interval_seconds = 5
heartbeat_interval_seconds = 30
max_concurrent_jobs = 1
cdp_url = "http://127.0.0.1:9222"  # 可选；账号登录使用 per-account Chrome
supported_job_types = [
  "feed_collect", "creator_monitor", "detail_fetch",
  "comment_fetch", "search_collect",
]
```

`agent_id` 为空时 Runtime 会调用 `/api/agents/register` 自动注册。注册后可以把返回的 agent id 固定写入配置。

## Chrome Profile 与账号登录

Profile 路径：

```text
local_agent/profiles/accounts/{profile_key}/
```

Stage 3F 账号登录流程（推荐）：

1. 管理员 `/agents` 绑定设备到运营员工
2. 运营 `/accounts` 登记本地 Agent
3. 运营创建小红书账号 → 发起登录
4. Agent claim 登录会话 → 自动启动独立 Chrome → 员工在浏览器内登录

Legacy 手动 CDP 映射（可选，在 `[accounts]` 中配置）：

```toml
"<platform_account_id>" = { platform = "xhs", session_mode = "cdp", cdp_url = "http://127.0.0.1:9222" }
```

中心可以保存 `account_sessions.session_meta_json`，但真实 Cookie 不上传。Runtime 优先使用登录会话 claim 拉起的 per-account Chrome；legacy 映射作兜底。

## 通信协议

Runtime 调用：

- `POST /api/agents/register`
- `POST /api/agents/{agent_id}/heartbeat`
- `POST /api/agents/{agent_id}/jobs/claim`
- `POST /api/jobs/{job_id}/start`
- `POST /api/jobs/{job_id}/progress`
- `POST /api/jobs/{job_id}/complete`
- `POST /api/jobs/{job_id}/fail`
- `POST /api/agents/{agent_id}/login-sessions/claim`（账号登录）
- `GET /api/accounts/{account_id}/sessions/ready`（legacy 兜底）
- `POST /api/ingestion/feed-candidates`
- `POST /api/ingestion/creator-monitor-items`
- `POST /api/ingestion/content-detail`
- `POST /api/ingestion/comments`
- `POST /api/ingestion/xhs-search-suggestions`（搜索联想词）

## 支持的 JobType

| JobType | 状态 | 说明 |
|---------|------|------|
| `feed_collect` | 已支持 | 推荐页采集 |
| `creator_monitor` | 已支持 | 对标监控 |
| `detail_fetch` | 已支持 | 详情补采 |
| `comment_fetch` | 已支持 | 评论补采 |
| `search_collect` | 已支持 | 关键词搜索采集（`XhsSearchProbe`） |
| `xhs_search_suggest` | 已支持 | 搜索联想词（`XhsSearchSuggestProbe`） |

## 任务到真实采集

推荐页任务：

```text
recommendation_feed_task
-> feed_collect job
-> Runtime claim
-> XhsHomeFeedProbe
-> /api/ingestion/feed-candidates
-> detail_fetch job enqueue
-> complete
```

关键词搜索任务：

```text
keyword_search_task
-> search_collect job
-> Runtime claim
-> XhsSearchProbe
-> /api/ingestion/feed-candidates
-> complete
```

对标监控任务：

```text
creator_monitor_task
-> creator_monitor job
-> Runtime claim
-> XhsCreatorConnector
-> /api/ingestion/creator-monitor-items
-> content_identity / discovery_event / creator_monitor_event / detail_fetch job
-> complete
```

## 失败语义

Runtime 将以下失败回传到 `/api/jobs/{job_id}/fail`：

- `session_connect_failed`
- `session_expired`
- `manual_verify_required`
- `missing_xsec_context`
- `internal_engine_error`

评论网页不可浏览时返回 `partial_success`，并在 `result_summary.error_code` 中写入 `comment_surface_unavailable`。

## 当前未支持

- 不支持抖音。
- 不支持复杂多并发调度，V1 默认 `max_concurrent_jobs = 1`。
- 不上传或托管 Cookie。
- 不做任务运行记录大页面（运营用 `/my-runs`，管理员用 `/operations`）。

## 相关文档

- 客户首跑手册：`docs/demo/clean-start-customer-test-playbook.md`
- Stage 3F 启动：`docs/demo/stage-3f-local-agent-startup.md`
- Agent 池化调度：`docs/guidance/account-agent-pool-rollout.md`
