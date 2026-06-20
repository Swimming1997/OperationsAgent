# PostgreSQL 生产部署、迁移与备份

Central Server 生产环境使用 PostgreSQL 16；SQLite 仅保留本地开发和测试默认。

## 启动与迁移

复制环境变量模板并修改密码：

```powershell
Copy-Item .env.postgres.example .env.postgres
docker compose --env-file .env.postgres up -d postgres
$env:INTEL_ENGINE_DATABASE_URL = "postgresql+psycopg://intel:REPLACE_ME@127.0.0.1:55432/intelligence_engine"
..\.venv\Scripts\python.exe -m alembic upgrade head
```

上线前必须执行：

```powershell
..\.venv\Scripts\python.exe -m alembic current
..\.venv\Scripts\python.exe -m pytest -q
```

应用升级顺序为：备份数据库、执行 Alembic、启动新应用、检查 `/api/health`。
不得使用 `Base.metadata.create_all()` 代替生产迁移。

## 备份

工具使用 PostgreSQL custom archive，并在写入后自动执行 `pg_restore --list` 校验：

```powershell
..\.venv\Scripts\python.exe scripts\postgres_ops.py backup
```

默认输出到 `backups/intelligence_engine_YYYYMMDD_HHMMSS.dump`。生产环境建议每天全量备份，
并把文件同步到不与数据库共盘的受控存储。

## 恢复演练

先校验：

```powershell
..\.venv\Scripts\python.exe scripts\postgres_ops.py verify --file backups\intelligence_engine_xxx.dump
```

恢复到空数据库：

```powershell
$env:INTEL_ENGINE_DATABASE_URL = "postgresql+psycopg://intel:REPLACE_ME@127.0.0.1:55432/intelligence_engine_restore"
..\.venv\Scripts\python.exe scripts\postgres_ops.py restore --file backups\intelligence_engine_xxx.dump
..\.venv\Scripts\python.exe -m alembic current
```

只有在确认目标数据库允许覆盖时才使用 `--clean`。每个发布周期至少做一次独立库恢复演练。

## SQLite 迁移到 PostgreSQL

当前仓库不提供自动跨数据库数据搬运，以避免 JSON、时区和唯一约束被静默转换。
需要迁移历史 SQLite 数据时，应使用一次性 ETL：

1. 对 SQLite 文件做只读副本；
2. PostgreSQL 执行 `alembic upgrade head`；
3. 按领域表顺序导入并保留原 UUID；
4. 校验内容、Job、素材库、权限和审计行数；
5. 运行后端全量测试与情报列表抽样；
6. 切换连接串前再次做 PostgreSQL 备份。

