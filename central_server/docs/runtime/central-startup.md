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

## 媒体文件（封面图）

详情入库时会探测小红书 CDN；探测失败时封面会落盘到：

```text
central_server\data\media\{content_id}\cover.{webp|jpg|png}
```

可通过环境变量覆盖目录：

```text
INTEL_ENGINE_MEDIA_ROOT=./data/media
```

部署到服务器时请与数据库一并做**持久化卷挂载与备份**（至少包含 `data/intelligence_engine.db` 与 `data/media/`）。多实例负载均衡前需共享 `media_root` 或迁移到对象存储。

前端通过签名 URL 访问封面：`GET /api/media/cover/{content_id}?e=...&s=...`（不依赖 Bearer，供 `<img>` 使用）。
