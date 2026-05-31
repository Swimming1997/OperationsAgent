# Local Agent Runtime V1

Local Agent 运行在员工电脑，只通过 HTTP JSON 与中央服务器通信。

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
- `xhs_search_suggest` — 搜索联想词采集

详细协议与任务链路见：`central_server/docs/runtime/local-agent-runtime-v1.md`（中央侧副本，内容更完整）。
