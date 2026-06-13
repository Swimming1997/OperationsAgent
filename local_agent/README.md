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

## Agent 绑定流程

1. 管理员在 `/agents` 将设备绑定到运营员工
2. 运营在 `/accounts` 点击「登记本地 Agent」（依赖本机 Local Bridge，默认端口 18765）

Local Agent 不直接访问中央数据库，不 import 中央 storage / db / services。协议模型保存在 `local_agent_runtime/contracts.py` 和 `local_agent_runtime/enums.py`。

Chrome Profile 保留在本机 `profiles/accounts/{profile_key}/`。不保存或上传 Cookie 原文。

`references/MediaCrawler` 只作参考源码，不是运行依赖。

详细说明：`docs/runtime/local-agent-runtime-v1.md`。
