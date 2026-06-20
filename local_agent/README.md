# Local Agent

Local Agent 运行在员工电脑，负责本机 Chrome / CDP / Profile、领取中央 Job、执行采集并通过 HTTP JSON 上报中央 API。

本文描述当前 Runtime V1（P0/P1 已验收基线）的运行方式。P2 的 Local-First 目标是把全量采集流水优先写入员工本地库，只在素材库精华、账号/Agent、配置同步等场景联机；P2 细节以 `..\central_server\docs\guidance\p2-development-plan.md` 为准。

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

直接运行：

```powershell
cd local_agent
..\.venv\Scripts\python.exe scripts\run_local_agent.py --config configs\local_agent.employee.example.toml --once
```

默认中央地址为 `http://127.0.0.1:8000`。启动前会检查 `/api/health`。

## P2 本地存储

通过配置文件启动时默认启用本地 SQLite：

```toml
[local_storage]
enabled = true
database_path = "data/local_intelligence.db"
```

当前为兼容过渡模式：采集归一化结果先写本地库，再调用现有中央 ingestion。中央暂时不可用时，上报请求保存在本地 `ingestion_outbox`，后续轮询自动重试。

启动真实本地工作台最简单的方式是直接双击：

```text
..\启动本地工作台.bat
```

脚本会启动专用 Chrome/Edge、真实 Local Agent 和真实本地数据库，然后打开工作台。系统不会生成模拟内容；页面初始为空，完成真实搜索采集后才会出现内容。使用结束后双击项目根目录的 `停止本地工作台.bat`。

Local Agent 启动后，本地工作台与 Local Bridge 共用端口。请使用启动日志输出的完整 `local_workspace` 地址：

```text
http://127.0.0.1:18765/#token=<本进程临时令牌>
```

页面首次加载会把令牌换成本机 `HttpOnly + SameSite=Strict` 会话 Cookie，随后自动清除 URL fragment；令牌不写入 SQLite、localStorage 或 sessionStorage。支持本地关键词搜索、异步任务状态、内容筛选、列表和详情。若默认端口被占用，以启动日志输出地址为准。中央不可用时，本地工作台仍保持运行并后台重连。

本地调度支持：

- 对标博主定时监控、新内容计数和标记已读。
- 推荐流立即刷新或定时刷新。
- 任务立即运行、暂停和恢复。
- 作者粉丝数、获赞收藏、作品数、认证、简介和 IP 属地等主页画像。

内容详情支持：

- 手动采集 XHS/抖音评论并匹配“怎么买、多少钱、求链接”等获客关键词。
- 使用中央运营账号登录后，把精选内容加入现有中央素材库。
- 设置素材类型、评级、标签和备注。
- 中央不可用或未完成内容同步时保留本地收藏意图，后续重试。

点击右上角“登录中央”后，可以在弹窗中填写中央服务地址、用户名和密码。中央服务地址默认取配置文件中的 `center_url`；修改并成功登录后会保存到本地 SQLite，下次打开自动带出。密码和中央 JWT 不落盘。

中央登录密码和访问令牌均不写入本地数据库；访问令牌只存在当前 Local Agent 进程内。

## P2 账号保护

`[risk_control]` 默认启用本地持久化账号保护，状态写入
`data/account_risk.db`。当前支持：

- 同账号任务最低执行间隔；
- UTC 自然日任务额度；
- 重试型失败指数退避；
- 人工验证类错误长冷却；
- heartbeat 上报账号健康摘要。

可通过 `[risk_control.accounts."<account_id>"]` 为高风险账号设置更严格的间隔和额度。

XHS 推荐流和搜索采集优先复用页面自身请求返回的 JSON，不额外发起平台请求；
当响应结构不可用或数量不足时，自动回退到现有 DOM 卡片提取。运行报告中的
`source_path`、`api_payload_count` 和 `dom_fallback_used` 可用于判断实际采集路径。

抖音已接入统一只读采集模型：

- detail Job 拦截作品详情响应并写入统一详情快照；
- comment Job 按需打开评论区、拦截评论响应并写入统一评论模型；
- creator monitor Job 拦截主页作品响应，写入统一内容和作者画像。

失败分类由 `shared_contracts/failure_policy.py` 统一定义，Local Agent 的账号退避和
Central Job 失败事件使用同一口径。XHS 审计命令可追加 `--export-zip`，把 summary、
NDJSON、明细和媒体清单打成一个归档包：

```powershell
..\.venv\Scripts\python.exe scripts\xhs_engine_audit.py --surface all --export-zip
```

空闲 Agent 使用带抖动的指数 claim 退避，默认从 5 秒逐步增加到 30 秒；领取到任务后
立即恢复基础间隔。可通过 `idle_poll_max_seconds`、`idle_poll_multiplier` 和
`idle_poll_jitter_ratio` 调整，最大值建议不超过 heartbeat 周期。

开发预览：

```powershell
cd local_agent
.\scripts\start_local_workspace.ps1
```

## Agent 绑定流程

1. 管理员在 `/agents` 将设备绑定到运营员工
2. 运营在 `/accounts` 点击「登记本地 Agent」（依赖本机 Local Bridge，默认端口 18765）

Local Agent 不直接访问中央数据库，不 import 中央 storage / db / services。协议模型保存在 `local_agent_runtime/contracts.py` 和 `local_agent_runtime/enums.py`。

Chrome Profile 保留在本机 `profiles/accounts/{profile_key}/`。不保存或上传 Cookie 原文。

`references/MediaCrawler` 只作参考源码，不是运行依赖。

详细说明：`docs/runtime/local-agent-runtime-v1.md`。
