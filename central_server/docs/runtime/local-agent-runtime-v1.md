# Local Agent Runtime V1

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

使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe scripts\run_local_agent.py --config configs\local_agent.example.toml
```

只执行一轮 claim 后退出：

```powershell
.\.venv\Scripts\python.exe scripts\run_local_agent.py --config configs\local_agent.example.toml --once
```

覆盖 CDP 地址：

```powershell
.\.venv\Scripts\python.exe scripts\run_local_agent.py --config configs\local_agent.example.toml --cdp-url http://127.0.0.1:9222
```

日志默认写入：

```text
logs/local_agent/local_agent.log
```

## 本地配置文件

示例文件：

```text
configs/local_agent.example.toml
```

核心字段：

```toml
center_url = "http://127.0.0.1:8000"
agent_id = ""
machine_fingerprint = "amiracle-local-agent-001"
claim_interval_seconds = 5
heartbeat_interval_seconds = 30
max_concurrent_jobs = 1
cdp_url = "http://127.0.0.1:9222"
supported_job_types = ["feed_collect", "creator_monitor", "detail_fetch", "comment_fetch", "search_collect"]

[accounts]
"<platform_account_id>" = { platform = "xhs", session_mode = "cdp", cdp_url = "http://127.0.0.1:9222" }
```

`agent_id` 为空时 Runtime 会调用 `/api/agents/register` 自动注册。注册后可以把返回的 agent id 固定写入配置。

## XHS 账号绑定

1. 在员工电脑启动独立 Chrome，并开启 CDP，例如 `9222`。
2. 在该 Chrome Profile 中登录小红书。
3. 在后台创建或确认一个 `platform_accounts.id`。
4. 在本地配置 `[accounts]` 下添加：

```toml
"<platform_accounts.id>" = { platform = "xhs", session_mode = "cdp", cdp_url = "http://127.0.0.1:9222" }
```

中心可以保存 `account_sessions.session_meta_json`，但真实 Cookie 不上传。Runtime 优先使用本地配置中的 `account_id -> cdp_url` 映射；没有本地映射时再查询中心 ready session metadata；最后才使用全局 `cdp_url` 兜底。

## 通信协议

Runtime 调用：

- `POST /api/agents/register`
- `POST /api/agents/{agent_id}/heartbeat`
- `POST /api/agents/{agent_id}/jobs/claim`
- `POST /api/jobs/{job_id}/start`
- `POST /api/jobs/{job_id}/progress`
- `POST /api/jobs/{job_id}/complete`
- `POST /api/jobs/{job_id}/fail`
- `GET /api/accounts/{account_id}/sessions/ready`
- `POST /api/ingestion/feed-candidates`
- `POST /api/ingestion/creator-monitor-items`
- `POST /api/ingestion/content-detail`
- `POST /api/ingestion/comments`

## 支持的 JobType

V1 重点支持：

- `feed_collect`
- `creator_monitor`

已纳入自动消费：

- `detail_fetch`
- `comment_fetch`

占位支持：

- `search_collect`：当前返回 `partial_success`，不执行真实搜索。

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
- 不支持真实 keyword search connector。
- 不支持复杂多并发调度，V1 默认 `max_concurrent_jobs = 1`。
- 不上传或托管 Cookie。
- 不做任务运行记录大页面。
