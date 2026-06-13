# Central Boundary Check

## 扫描范围

- `central_server\intelligence_engine`
- `central_server\scripts`

`central_server\scripts\dev_legacy` 不属于正式中央运行路径，单独列为 legacy 例外。

## 禁止 import

- `local_agent_runtime`
- `local_agent`
- `intelligence_engine.connectors.xhs` 真实采集 runtime

中央业务模型中出现的字段名，例如 `local_agent_id`、`LocalAgent` 数据表/API model，属于中央服务协议和数据模型，不是对 Local Agent runtime 的代码依赖。

## 执行命令

```powershell
rg -n "^\s*(from|import)\s+.*(local_agent_runtime|local_agent)" central_server\intelligence_engine central_server\scripts --glob "!**/dev_legacy/**" --glob "!**/__pycache__/**"
rg -n "intelligence_engine\.connectors\.xhs" central_server\intelligence_engine central_server\tests --glob "!**/__pycache__/**"
```

## 发现结果

未发现命中。正式中央服务代码和正式中央脚本不 import `local_agent_runtime`，也不 import Local Agent 运行包。

正式中央服务代码和正式中央测试不再 import `intelligence_engine.connectors.xhs`。中央只保留 `intelligence_engine.domain.xhs_context` 作为协议上下文合并、URL 解析与任务 payload 补全工具。

## Legacy 例外

`central_server\scripts\dev_legacy\` 保留历史 smoke/debug 工具和旧 runner 备份，部分文件包含旧 `intelligence_engine.local_agent` import 或 DB-coupled runner。该目录不属于正式中央运行路径。

历史中央 XHS runtime 采集副本已移动到：

- `central_server\scripts\dev_legacy\xhs_runtime_duplicate\xhs\`

该副本不属于正式运行路径，不作为后续开发基线。
