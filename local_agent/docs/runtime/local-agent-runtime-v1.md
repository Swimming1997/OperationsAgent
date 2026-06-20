# Local Agent Runtime V1

Local Agent 运行在员工电脑，只通过 HTTP JSON 与中央服务器通信。

本文描述当前 Runtime V1（P0/P1 已验收基线）的中央 Job 模式。P2 的 Local-First 本地采存看闭环是下一阶段目标，入口见 `central_server/docs/guidance/p2-development-plan.md`。

## 启动与停止

```powershell
cd local_agent
.\scripts\start.ps1
```

```powershell
cd local_agent
.\scripts\stop.ps1
```

仓库根目录快捷脚本：

```powershell
.\start-local-agent.ps1
```

直接运行（调试）：

```powershell
cd local_agent
..\.venv\Scripts\python.exe scripts\run_local_agent.py --config configs\local_agent.employee.example.toml
```

只执行一轮 claim 后退出：加 `--once`。

## 默认配置

```text
local_agent\configs\local_agent.employee.example.toml
```

默认中央地址：`http://127.0.0.1:8000`

启动前检查 `http://127.0.0.1:8000/api/health`。不可达时输出中文提示并退出。

## P2 本地存储

配置文件加载时默认启用：

```toml
[local_storage]
enabled = true
database_path = "data/local_intelligence.db"
```

数据库默认位于 `local_agent\data\local_intelligence.db`，连接启用 WAL、`busy_timeout=5000`、`synchronous=NORMAL` 和外键约束。

当前采用双写过渡：

1. feed/search/creator、detail、comments、search suggestions 归一化结果先写本地库。
2. 继续调用现有中央 ingestion，保持 P0/P1 契约兼容。
3. 中央上报失败时写入 `ingestion_outbox`，后续 Runtime 轮询自动重试。

## P2 本地工作台

Local Bridge 根路径提供本地工作台。正式 Runtime 默认生成进程级临时 token，请复制启动日志中的完整地址：

```text
http://127.0.0.1:18765/#token=<本进程临时令牌>
```

token 首次通过 Bearer 鉴权换成本机 `HttpOnly + SameSite=Strict` 会话 Cookie，随后从地址栏清除；不写入 SQLite 或 Web Storage。Local Bridge 同时拒绝非 localhost 的跨域请求。

中央素材库登录弹窗允许员工填写中央服务地址。默认值来自 `center_url`；成功登录后仅持久化服务地址到本地 SQLite，密码和 JWT 继续只保存在当前进程内存。

能力：

- 提交小红书关键词搜索并查看 queued/running/success/failed 状态。
- 创建对标博主定时监控，查看新内容数并标记已读。
- 推荐流立即刷新或按周期刷新。
- 任务支持立即运行、暂停和恢复；定时任务失败后保留运行错误并在下一周期重试。
- 按关键词、平台、来源筛选本地内容。
- 查看标题、作者画像、互动指标、正文、来源、图片和获客信号。
- 在内容详情手动采集评论并匹配获客关键词。
- 登录中央运营账号后把内容加入现有 `reference_library_items` 素材库。
- 中央不可用时继续提供本地页面和本地搜索，Runtime 后台重连中央。

中央素材库登录只接受 admin / supervisor / operator。密码不落盘；JWT 只保存在当前 Local Agent 进程内。素材同步失败时，本地 `material_export` 保留标签、备注和重试状态。

API：

- `POST /api/local/search`
- `POST /api/local/tasks`
- `GET /api/local/tasks`
- `GET /api/local/tasks/{id}`
- `POST /api/local/tasks/{id}/run`
- `POST /api/local/tasks/{id}/viewed`
- `POST /api/local/tasks/{id}/pause`
- `POST /api/local/tasks/{id}/resume`
- `GET /api/local/contents`
- `GET /api/local/contents/{id}`
- `POST /api/local/contents/{id}/acquisition-check`
- `POST /api/local/contents/{id}/material`
- `GET /api/local/central-session`
- `POST /api/local/central-session/login`
- `POST /api/local/central-session/logout`
- `POST /api/local/materials/retry`

## Chrome Profile

```text
local_agent\profiles\accounts\{profile_key}\
```

Local Agent 不保存或上传 Cookie 原文。`logs/`、`profiles/` 是运行数据，不作为源码。

`references/MediaCrawler` 是参考源码，不作为运行依赖。

## Local Bridge

默认启用 Local Bridge（`http://127.0.0.1:18765`），供前端「登记本地 Agent」扫描发现本机 Agent。

- 端口被占用时自动递增（18766、18767…，最多 10 个）
- 前端默认扫描 `18765–18774`（可通过 `VITE_LOCAL_BRIDGE_PORTS` 配置）
- 禁用 bridge：`--disable-bridge`

## Agent 绑定

1. 管理员在 `/agents` 将设备绑定到运营员工
2. 运营在 `/accounts` 点击「登记本地 Agent」

本地 TOML 的 `employee_id` 仅作可选覆盖，正常留空。

## 支持的 JobType

- `feed_collect` — 推荐页采集
- `creator_monitor` — 对标监控
- `detail_fetch` / `comment_fetch` — 详情与评论补采
- `search_collect` — 关键词搜索采集（真实 connector）
- `xhs_account_posted_notes` — 当前小红书账号已发布笔记
- `xhs_search_suggest` — 小红书搜索联想词采集（历史兼容）
- `search_suggest` — 平台无关搜索联想词采集

当前项目文档入口见：`central_server/docs/README.md`。协议与任务链路以中央 API、`shared_contracts/` 和本文件为准。
