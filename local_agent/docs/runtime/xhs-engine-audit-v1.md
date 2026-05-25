# XHS Engine Audit V1

## 能力分层

- `read_only_engine`：本阶段审计范围，只读取网页端可见内容或签名只读接口。
- `account_asset_read`：后续读取账号资产，不在 v1 执行。
- `operator_action`：发布、回复、点赞、收藏、关注、上传等动作能力，v1 明确不实现。

## 手动审计命令

```powershell
cd D:\AMiracle\local_agent
D:\AMiracle\.venv\Scripts\python.exe scripts\xhs_engine_audit.py --surface capabilities
D:\AMiracle\.venv\Scripts\python.exe scripts\xhs_engine_audit.py --surface self_info --config configs\local_agent.employee.example.toml
D:\AMiracle\.venv\Scripts\python.exe scripts\xhs_engine_audit.py --surface homefeed --config configs\local_agent.employee.example.toml --target-count 20
D:\AMiracle\.venv\Scripts\python.exe scripts\xhs_engine_audit.py --surface search --config configs\local_agent.employee.example.toml --keyword "SCI投稿" --limit 20
D:\AMiracle\.venv\Scripts\python.exe scripts\xhs_engine_audit.py --surface detail --config configs\local_agent.employee.example.toml --url "真实笔记URL"
D:\AMiracle\.venv\Scripts\python.exe scripts\xhs_engine_audit.py --surface comment --config configs\local_agent.employee.example.toml --url "真实笔记URL" --limit 20
D:\AMiracle\.venv\Scripts\python.exe scripts\xhs_engine_audit.py --surface creator --config configs\local_agent.employee.example.toml --creator-url "真实作者主页URL" --limit 20
D:\AMiracle\.venv\Scripts\python.exe scripts\xhs_engine_audit.py --surface smoke --config configs\local_agent.employee.example.toml --keyword "SCI投稿" --limit 10
```

`--surface smoke`（v2 闭环验收）：自动执行 `self_info → search →（必要时 homefeed 补 xsec）→ detail → comment`，从 search/homefeed **新鲜卡片**选 URL，不再使用 MediaCrawler 过期示例 URL。

`--surface all` 只跑 `self_info`、`homefeed`、`search`、`detail`、`comment`、`creator`。缺少 URL 的 detail/comment/creator 会写入 `P4_INFO` 跳过记录。

## Smoke 模式说明（v2）

用途：验证登录态 + 搜索/推荐发现 + 详情/评论 API 的真实闭环，避免手工粘贴过期 URL。

流程：

1. 获取 CDP session（需 `--config`，Chrome 已登录）。
2. `self_info` 确认登录账号字段。
3. `search` 按 `--keyword` 抓卡片；若卡片无 `xsec_token`，fallback `homefeed` 选带 xsec 的笔记。
4. 必要时 `enrich_xhs_context_from_page` 从页面跳转补齐 xsec。
5. 用新鲜 URL 跑 `detail` + `comment`，汇总为 smoke 记录。

**不要**再使用 `references/MediaCrawler` 里的过期 `--url` 做 detail/comment 验收；单项 detail/comment 仅调试时使用当前 session 刚抓到的 URL。

## 性能统计口径（v2）

- `total_ms` = 该 surface 从开始到结束的 wall-clock 时间（`PerfTimer` 包裹整段 collect/fetch）。
- `page_goto_ms` / `initial_wait_ms` / `scroll_ms` / `dom_extract_ms` 来自 probe 分段计时，合并进 summary 但**不覆盖** wall-clock `total_ms`。
- `items_per_second = normalized_items / (total_ms / 1000)`；无结果时为 `0`。
- CDP `probe_only` 模式下 homefeed 若不在 explore 页会先 `page_goto`，计入 `page_goto_ms`。

## Severity

- `P0_FATAL`：会话不可用、浏览器无法连接。
- `P1_BLOCKER`：登录态失效、手动验证、签名失败导致能力不可用。
- `P2_MAJOR`：surface 不可用、字段覆盖严重不足、核心字段不对齐。
- `P3_MINOR`：有 fallback 或少量字段缺失。
- `P4_INFO`：正常信息或跳过说明。

## 日志

审计日志写入：

```text
local_agent\logs\audit\xhs_engine\YYYYMMDD\engine_audit_<run_id>.ndjson
local_agent\logs\audit\xhs_engine\YYYYMMDD\engine_audit_<run_id>.summary.json
local_agent\logs\audit\xhs_engine\YYYYMMDD\engine_audit_<run_id>.summary.md
```

写入前统一脱敏，不记录 cookie、xsec_token、X-S、X-T、x-S-Common 原文。

## 性能字段

- `session_acquire_ms`
- `page_goto_ms`
- `initial_wait_ms`
- `scroll_ms`
- `api_ms`
- `network_capture_ms`
- `dom_extract_ms`
- `normalize_ms`
- `ingestion_ms`
- `total_ms`
- `items_per_second`

## 常见问题

- 登录态失效：重新完成小红书网页登录后重试。
- 手动验证：在本地 Chrome 处理安全验证。
- 缺少 xsec_token：从推荐流、搜索或作者页重新获取带上下文的 URL。
- API 签名失败：检查 `xhshow` 依赖和 cookie 中的 `a1`。
- 评论区不可见：记录 `comment_surface_unavailable`，不强行重型 DOM fallback。
- DOM 结构变化：检查 baseline 和 probe 字段覆盖。
- 性能过慢：优先看 `page_goto_ms`、`scroll_ms`、`api_ms` 和 `items_per_second`。

## 当前真实验收状态（v2）

| surface | capability_key | 当前状态 | 最高 severity | 主要问题 | 下一步 |
|---|---|---|---|---|---|
| capabilities | xhs.engine.capabilities | pass | P4_INFO | 无 | 维持 |
| self_info | xhs.account.self_info | **pass** | P4_INFO | 已修复 basic_info 字段映射 | 维持 |
| homefeed | xhs.feed.home_recommend | pass | P4_INFO | xsec 上下文齐全；含 page_goto | 维持 |
| search | xhs.search.notes | pass | P4_INFO | DOM 卡片常无 xsec；需 homefeed fallback | 增强搜索页 xsec 捕获 |
| detail | xhs.note.detail | **pass（smoke）** | P4_INFO | 单项手工 URL 仍可能失败 | 统一走 smoke |
| comment | xhs.note.comments | **pass（smoke）** | P4_INFO | API 成功跳过 DOM fallback | 维持 |
| smoke | xhs.engine.smoke | **pass** | P4_INFO | search 无 xsec 时走 homefeed | 维持 |
| creator | xhs.creator.posted_notes | pass | P4_INFO | network_capture 偏慢 | 可选优化 |

最近一次 smoke run_id：`20260524_ab15b74013ea`（目录 `local_agent\logs\audit\xhs_engine\20260524\`）。

### 性能快照（v2 真实跑数，run ab15b74013ea）

| surface | total_ms | items_per_second | 主要 stage |
|---|---:|---:|---|
| self_info | 1495 | 0.669 | api_ms |
| search | 4735 | 2.112 | page_goto + scroll + dom_extract |
| homefeed | 3557 | 2.812 | page_goto + dom_extract |
| detail | 1055 | 0.948 | api_ms |
| comment | 1149 | 8.702 | api_ms |
| smoke 整链 | 13262 | — | 含上述子链路 |
