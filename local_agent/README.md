# Local Agent

Local Agent 运行在员工电脑，负责本机 Chrome / CDP / Profile、领取中央 Job、执行采集并通过 HTTP JSON 上报中央 API。

## 启动停止

```bat
cd D:\AMiracle\local_agent; .\scripts\start.ps1
cd D:\AMiracle\local_agent; .\scripts\stop.ps1
```

直接运行：

```powershell
cd D:\AMiracle\local_agent
D:\AMiracle\.venv\Scripts\python.exe scripts\run_local_agent.py --config configs\local_agent.employee.example.toml --once
```

默认中央地址为 `http://127.0.0.1:8000`。启动前会检查 `/api/health`。

Local Agent 不直接访问中央数据库，不 import 中央 storage / db / services。协议模型保存在 `local_agent_runtime/contracts.py` 和 `local_agent_runtime/enums.py`。

Chrome Profile 保留在本机 `profiles/accounts/{profile_key}/`。不保存或上传 Cookie 原文。

`references/MediaCrawler` 只作参考源码，不是运行依赖。
