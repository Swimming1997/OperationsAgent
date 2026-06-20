# P2 验收流程

> 适用范围：P2 Local-First 开发验收与部署验收。  
> 原则：自动化通过不代替真实平台账号、真实并发和生产 PostgreSQL 恢复演练。

## 1. 验收结论分级

- **开发验收通过**：代码边界、三端测试、前端构建、本地工作台和离线重试均通过。
- **部署验收通过**：真实账号 smoke、20+ Agent 联机观察、生产 PostgreSQL 备份恢复均通过。
- **P2 最终验收通过**：开发验收和部署验收全部通过，且无 P0/P1 契约回归。

## 2. 开发验收

### 2.1 工作区与边界

在仓库根目录执行：

```powershell
git status --short
rg -n "^\s*(from|import)\s+.*(central_server\.intelligence_engine\.(db|storage|services|main)|intelligence_engine\.(db|storage|services|main))" local_agent --glob "*.py" --glob "!local_agent/references/**" --glob "!local_agent/scripts/dev_legacy/**"
rg -n "^\s*(from|import)\s+.*(local_agent_runtime|local_agent)" central_server\intelligence_engine central_server\scripts --glob "!**/dev_legacy/**" --glob "!**/__pycache__/**"
```

通过标准：

- 两次边界扫描均无正式运行代码命中。
- P2 改动未进入 `product_routes.py`、`db/models.py` 等聚合文件。
- Job 状态、claim、checkpoint、result、retry、lease 改动只经过 `JobRepository` 或 `intelligence_engine.jobs`。

### 2.2 三端全量回归

```powershell
cd central_server
..\.venv\Scripts\python.exe -m pytest

cd ..\local_agent
..\.venv\Scripts\python.exe -m pytest

cd ..\central_server\frontend
npm test
npm run build
```

通过标准：

- Central Server、Local Agent、前端测试均为 0 failed。
- TypeScript 编译和 Vite 生产构建成功。
- `git diff --check` 无空白错误。

### 2.3 Local-First 数据闭环

最简单的方式是直接双击：

```text
启动本地工作台.bat
```

脚本会启动真实 Local Agent 和专用平台浏览器，并自动打开工作台。不会生成模拟内容。验收结束后双击项目根目录的 `停止本地工作台.bat`。

PowerShell 方式：

```powershell
cd local_agent
.\scripts\start_local_workspace.ps1
```

先在自动打开的 Chrome/Edge 中完成小红书登录，再使用工作台。启动输出中的完整 `local_workspace` URL 必须包含 `#token=...`。

依次检查：

1. URL 打开后地址栏中的 token fragment 自动消失，并建立 `HttpOnly + SameSite=Strict` 本机会话。
2. 首次启动页面为空，不出现任何模拟内容。
3. 输入真实关键词完成采集后，列表、详情、来源和作者信息正常展示。
4. 浏览器刷新后仍可读取已采集的本地数据。
5. 390px 宽移动视口无横向滚动，控制台无 error/warn。
6. 不携带 Bearer token 直接访问 `/api/local/contents` 返回 401。
7. 非 localhost Origin 的 CORS 预检返回 403。

### 2.4 离线与幂等

执行 Local Agent 全量测试后，重点确认：

- 同一 `platform + platform_content_id` 重复采集只保留一条内容。
- 中央不可用时内容先写本地，`ingestion_outbox` 保留 pending。
- 中央恢复后 outbox 可重放并变为 sent。
- 素材库同步失败不丢失本地收藏意图。
- 密码、中央 JWT 和 Bridge token 均不写入 SQLite、localStorage 或 sessionStorage；Bridge token 仅允许进入 HttpOnly 本机会话 Cookie。

## 3. 真实平台账号 smoke

使用刚登录且可正常访问的小红书账号：

```powershell
cd local_agent
..\.venv\Scripts\python.exe scripts\xhs_engine_audit.py --surface smoke --config configs\local_agent.employee.toml --keyword "测试关键词" --export-zip
```

通过标准：

- homefeed/search 能抓到新鲜内容，禁止使用历史过期 URL。
- detail 可获取正文、作者、互动和媒体字段。
- comment 返回评论或明确的 `comment_surface_unavailable`，不得伪造成功。
- creator 可返回作者画像和作品列表。
- 审计 ZIP 可生成，且不包含 Cookie、JWT、Bridge token 等敏感值。
- 无 manual verify、remote blocked、signature invalid 等风控错误；如出现，必须按账号保护策略进入冷却，不能连续重试。

## 4. 20+ Agent 联机验收

准备 20 个独立 Agent 实例或进程，每个实例使用不同：

- `device_name`
- `machine_fingerprint`
- Bridge 端口
- 本地数据库路径
- risk state 路径

持续运行至少 30 分钟，期间保持 Job 队列既有空闲时段也有任务时段。

通过标准：

- 无重复 claim，同一 Job 不被多个 Agent 执行。
- 无明显同步轮询尖峰；空闲 Agent 的 claim 间隔逐步退避并带 jitter。
- heartbeat 按配置周期稳定上报，不随 claim 空转成倍增加。
- stale claimed 可重排队；stale running 按 retry budget 自动恢复或终态失败。
- Central API 无持续 5xx，数据库连接池、CPU 和响应时间无持续恶化。
- 记录 30 分钟内 claim、heartbeat、5xx、重复 Job、stale Job 数量作为验收附件。

## 5. PostgreSQL 生产恢复演练

按 `docs/operations/postgresql-production.md` 准备隔离的恢复库：

```powershell
cd central_server
..\.venv\Scripts\python.exe scripts\postgres_ops.py backup --database-url $env:PRODUCTION_DATABASE_URL --file .\backups\p2.dump
..\.venv\Scripts\python.exe scripts\postgres_ops.py verify --file .\backups\p2.dump
..\.venv\Scripts\python.exe scripts\postgres_ops.py restore --database-url $env:RESTORE_DATABASE_URL --file .\backups\p2.dump --clean
```

恢复后执行：

```powershell
$env:INTEL_ENGINE_DATABASE_URL=$env:RESTORE_DATABASE_URL
..\.venv\Scripts\python.exe -m alembic current
..\.venv\Scripts\python.exe scripts\bench_intelligence_list.py --samples 30
```

通过标准：

- backup、verify、restore 全部成功。
- Alembic revision 为最新版本。
- 用户、账号、Agent、Job、素材库数据量与源库抽查一致。
- 恢复库 API 可启动，素材库和情报列表可读。
- 恢复耗时、备份文件大小、操作者和时间记录进验收附件。

## 6. 最终签署清单

- [ ] 开发验收全部通过。
- [ ] 真实平台账号 smoke 通过并附审计 ZIP。
- [ ] 20+ Agent 运行至少 30 分钟并附监控记录。
- [ ] PostgreSQL 备份恢复演练通过。
- [ ] P2 文档中的实现路径、测试数量和实际代码一致。
- [ ] 所有阻塞问题关闭后，由验收人记录日期、commit SHA 和环境信息。
