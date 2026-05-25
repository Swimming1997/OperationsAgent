# Central / Local Agent Split Acceptance

## 1. 当前最终目录树

```text
D:\AMiracle\
  .venv\
  README.md
  .gitignore
  central_server\
    intelligence_engine\
    frontend\
    alembic\
    scripts\
    tests\
    docs\
    data\
    logs\
  local_agent\
    local_agent_runtime\
    configs\
    scripts\
    tests\
    docs\
    references\MediaCrawler\
    profiles\
    logs\
  docs\refactor\
  cd central_server; .\scripts\start.ps1
  cd central_server; .\scripts\stop.ps1
  recd central_server; .\scripts\start.ps1
  cd local_agent; .\scripts\start.ps1
  cd local_agent; .\scripts\stop.ps1
  recd local_agent; .\scripts\start.ps1
  分别运行 central_server\scripts\start.ps1 和 local_agent\scripts\start.ps1
  分别运行 local_agent\scripts\stop.ps1 和 central_server\scripts\stop.ps1
  cd central_server; .\scripts\reset.ps1
```

## 2. 中央服务命令

启动：

```powershell
cd D:\AMiracle\central_server; .\scripts\start.ps1
```

停止：

```powershell
cd D:\AMiracle\central_server; .\scripts\stop.ps1
```

测试：

```powershell
cd D:\AMiracle\central_server
D:\AMiracle\.venv\Scripts\python.exe -m pytest
```

前端：

```powershell
cd D:\AMiracle\central_server\frontend
npm install
npm test
npm run build
```

## 3. Local Agent 命令

启动：

```powershell
cd D:\AMiracle\local_agent; .\scripts\start.ps1
```

停止：

```powershell
cd D:\AMiracle\local_agent; .\scripts\stop.ps1
```

测试：

```powershell
cd D:\AMiracle\local_agent
D:\AMiracle\.venv\Scripts\python.exe -m pytest
```

最小链路：

```powershell
cd D:\AMiracle\local_agent
D:\AMiracle\.venv\Scripts\python.exe scripts\run_local_agent.py --config configs\local_agent.employee.example.toml --once
```

## 4. 前端结果

- `npm install`：通过。
- `npm test`：13 个测试文件、42 个测试通过。
- `npm run build`：通过，生成 `frontend\dist`。
- `node_modules`、`dist`、`*.tsbuildinfo` 已在 `.gitignore` 和 package 排除规则中。

## 5. Python 测试结果

- `central_server`: 92 passed。
- `local_agent`: 11 passed。

## 6. Local Agent 边界扫描结果

正式扫描范围：

- `local_agent\local_agent_runtime`
- `local_agent\scripts\run_local_agent.py`
- `local_agent\scripts\start.ps1`
- `local_agent\tests`

禁止项扫描未命中：

- `central_server`
- `intelligence_engine.db`
- `intelligence_engine.storage`
- `intelligence_engine.services`
- `SessionLocal`
- `sqlalchemy`
- `alembic`
- `Repository`

详情见 `local_agent\docs\runtime\local-agent-boundary-check.md`。

## 7. 中央反向边界扫描结果

正式扫描范围：

- `central_server\intelligence_engine`
- `central_server\scripts`

禁止 import 扫描未命中：

- `local_agent_runtime`
- `local_agent`

中央业务字段名 `local_agent_id`、中央 DB model `LocalAgent` 属于中央协议与数据模型，不是运行包 import。

详情见 `central_server\docs\runtime\central-boundary-check.md`。

## 8. Package 验收结果

生成包：

- `central_server\packages\central_server-code-20260524_101521.zip`
- `packages\AMiracle-local-agent-20260524_101529.zip`

中央包扫描未发现：

- `.venv`
- `node_modules`
- `frontend/dist`
- `data/*.db`
- `logs`
- `profiles`
- `backups`
- `packages`
- `__pycache__`
- `.pytest_cache`
- `*.tsbuildinfo`

Local Agent 包扫描未发现：

- `.venv`
- `data`
- `logs`
- `profiles`
- `node_modules`
- `__pycache__`
- `.pytest_cache`
- `references/MediaCrawler/.git`

Local Agent 包包含正式 runtime、example configs、scripts、docs、tests 和 `references/MediaCrawler` 参考源码。

## 9. Legacy 文件清单

Local Agent legacy：

- `local_agent\scripts\dev_legacy\fake_runner.py`
- `local_agent\scripts\dev_legacy\xhs_comment_probe_runner.py`
- `local_agent\scripts\dev_legacy\xhs_creator_monitor_runner.py`
- `local_agent\scripts\dev_legacy\xhs_detail_probe_runner.py`
- `local_agent\scripts\dev_legacy\xhs_intelligence_loop_runner.py`
- `local_agent\scripts\dev_legacy\xhs_main_chain_smoke_runner.py`
- `local_agent\scripts\dev_legacy\xhs_manual_comment_probe_runner.py`

Central legacy：

- `central_server\scripts\dev_legacy\local_agent_db_runners\*`
- `central_server\scripts\dev_legacy\xhs_*`
- `central_server\scripts\dev_legacy\test_fake_e2e.py`
- `central_server\scripts\dev_legacy\test_xhs_main_chain_smoke_runner.py`

## 10. 后续开发注意事项

- 中央服务不得 import `local_agent_runtime`。
- Local Agent 正式 runtime 不得 import 中央 DB、storage、services、repository 或 SQLAlchemy。
- Local Agent 与中央之间只通过 HTTP JSON 协议通信。
- Chrome Profile 保留在 `local_agent\profiles\accounts\{profile_key}\`，不保存或上传 Cookie 原文。
- `data/`、`logs/`、`profiles/`、`node_modules/`、`dist/`、`packages/` 是运行或生成数据，不作为源码。
- PowerShell 脚本保持 UTF-8 编码，根目录 bat 使用 `chcp 65001 > nul`。
