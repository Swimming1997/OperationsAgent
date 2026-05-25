# Central Server

中央服务器包含 FastAPI、Web 前端、数据库、Alembic migration、任务中心、Job 队列和 ingestion API。

## 启动停止

```powershell
cd D:\AMiracle\central_server
..\.venv\Scripts\python.exe -m pytest
```

实际命令不要在 `..\.venv` 中加入空格；也可以使用：

```powershell
D:\AMiracle\.venv\Scripts\python.exe -m pytest
```

启动：

```bat
cd D:\AMiracle\central_server; .\scripts\start.ps1
```

停止：

```bat
cd D:\AMiracle\central_server; .\scripts\stop.ps1
```

中央脚本只管理 FastAPI `8000` 和 Vite `5173`，不停止 Local Agent，不停止普通 Chrome。

默认 SQLite 数据库路径为 `central_server\data\intelligence_engine.db`。`data/` 和 `logs/` 是运行数据。
