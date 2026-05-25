# Central / Local Agent Split Audit

## 当前耦合点

- `intelligence_engine/local_agent/*` 同时包含正式 HTTP runtime 和历史 DB-coupled runner。
- `xhs_comment_probe_run.py`、`xhs_detail_probe_run.py`、`xhs_main_chain_smoke_run.py`、`xhs_intelligence_loop_run.py` 等历史脚本直接 import `SessionLocal`、DB model、repository。
- XHS connector 中的浏览器采集、Playwright、CDP probe 属于 Local Agent；中央侧仍保留 ingestion、repository、schemas 和少量存储侧 URL/context 处理。
- Local Agent 原先复用 `intelligence_engine.domain.enums`、`intelligence_engine.domain.schemas`，造成运行包依赖中央包。

## 迁移后归属

- `central_server/intelligence_engine`：中央 API、DB、domain schemas、filtering、jobs、security、services、storage、main/config。
- `local_agent/local_agent_runtime`：正式 Local Agent runtime、CenterClient、config、Chrome launcher、account login executor、XHS sessions/connectors、最小协议模型。
- `local_agent/local_agent_runtime/contracts.py` 和 `enums.py`：Local Agent 需要的最小 HTTP JSON 协议模型与枚举，序列化保持中央 ingestion API 兼容。
- `central_server/frontend`：中央 Web 前端。
- `central_server/alembic`：中央 migration。
- `local_agent/references/MediaCrawler`：参考源码，不作为运行依赖。

## Legacy 脚本

- `central_server/scripts/dev_legacy/` 保留旧 DB-coupled smoke entrypoint 和旧 runner 备份。
- `local_agent/scripts/dev_legacy/` 保留已识别为 DB-coupled 的旧 runner 副本；这些文件不属于正式 Local Agent Runtime。

## 已消除的 import

- 正式 `local_agent_runtime` 不再 import `intelligence_engine.db`、`intelligence_engine.storage`、`intelligence_engine.services`、`intelligence_engine.main`。
- 正式 `local_agent/scripts/run_local_agent.py` 只把 `local_agent` 根目录加入 `sys.path`，不加入 `central_server`。
- 中央服务代码不 import `local_agent_runtime`。
