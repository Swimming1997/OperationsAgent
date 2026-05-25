# Central Startup

启动：

```bat
cd D:\AMiracle\central_server; .\scripts\start.ps1
```

停止：

```bat
cd D:\AMiracle\central_server; .\scripts\stop.ps1
```

脚本只管理：

- FastAPI `127.0.0.1:8000`
- Vite `127.0.0.1:5173`

PID 文件写入 `central_server\logs\runtime\`，日志写入 `central_server\logs\`。

数据库默认路径：

```text
sqlite:///./data/intelligence_engine.db
```

对应文件为 `central_server\data\intelligence_engine.db`。
