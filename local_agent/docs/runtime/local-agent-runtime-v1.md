# Local Agent Runtime V1

Local Agent 运行在员工电脑，只通过 HTTP JSON 与中央服务器通信。

启动：

```bat
cd D:\AMiracle\local_agent; .\scripts\start.ps1
```

停止：

```bat
cd D:\AMiracle\local_agent; .\scripts\stop.ps1
```

默认配置：

```text
local_agent\configs\local_agent.employee.example.toml
```

默认中央地址：

```text
http://127.0.0.1:8000
```

启动前检查 `http://127.0.0.1:8000/api/health`。不可达时输出中文提示并退出。

Chrome Profile 位于：

```text
local_agent\profiles\accounts\{profile_key}\
```

Local Agent 不保存或上传 Cookie 原文。`logs/`、`profiles/` 是运行数据，不作为源码。

`references/MediaCrawler` 是参考源码，不作为运行依赖。
