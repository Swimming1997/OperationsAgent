# P0 运营情报中心 — 阶段 0 设计摘要与验收清单

> 定稿日期：2026-05-26（权限增补：2026-05-30）  
> 依据：`待开发计划/运营情报中心V1开发计划_20260526.md` §4.3、§7.5、§10.1、§11  
> 实现对照：`alembic/versions/0005_*`～`0007_*`、`BenchmarkSelectionService`、`IntelligencePage`、`BenchmarkLibraryPage`、`intelligence_access.py`

---

## 1. 强制决策（阶段 0）

| 决策项 | 结论 | 实现位置 |
|--------|------|----------|
| 对标库模型 | **扩展** `ReferenceLibraryItem` / `ReferenceLibraryEvent`，禁止 `BenchmarkItem` 平行表 | `0005_p0_reference_library_foundation.py` |
| 库类型 | `lead` / `non_lead` / `uncategorized`（旧值迁移） | `domain/enums.py`、`normalize_library_type` |
| 选中来源 | `selection_sources_json`：`manual` / `ai`（`ai` = 规则自动，非 LLM） | 见 §2.4 计划 |
| 作品等级 | `poor` / `medium` / `good` / `watching` | 评级走 `RuleProfile.config_json` |
| 每 content 单条 active | 部分唯一索引 + 服务层 `get_active_item` | migration `0005` |
| 机器规则 vs 运营条文 | 关键词 → `KeywordRule*`；经验条文 → `OperationRule`（P1 API，已提前落库） | §4.4 计划 |

---

## 2. 状态机（§4.3）

```text
[无 active 条目] --manual_select--> active + selection_locked_by_manual=true
[无 active 条目] --ai_select_by_rules--> active（metadata: ai_reason, rule_profile_*）
[active + manual 锁] --ai_select_by_rules--> 跳过（skipped_manual_locked）
[active] --re-evaluate--> 更新库类型/评级/命中词（未 manual 锁）
[active] --archive--> archived（事件 archived）；主管/管理员移出
[active] --revoke--> archived（事件 revoked）；运营 24h 内撤回本人入库
再次入库 → 新 created 事件
```

**幂等**：`ai_evaluation_keys` = `content_id:rule_profile_id:version:trigger_source`  
**触发源**：`feed_ingestion` | `detail_ingestion` | `comment_ingestion` | `manual_re_evaluate`

---

## 3. P0 API 合同（已实现路径）

基路径：`/api`（`product_routes.py`）。分页默认 `page_size≤50`，最大 100。

| 能力 | 方法 | 路径 | 角色 |
|------|------|------|------|
| 情报列表 | GET | `/intelligence/contents/product` | admin/supervisor/operator/**sales**（只读） |
| 情报详情 | GET | `/intelligence/contents/{id}/product-detail` | 同上 |
| 场景筛选偏好列表/读取 | GET | `/product/me/intelligence/scenario-filters`（含 `{scenario}`） | 同上（只读） |
| 场景筛选偏好保存/删除 | PUT/DELETE | `/product/me/intelligence/scenario-filters/{scenario}` | admin/supervisor/operator |
| 手动入库 | POST | `/intelligence/contents/{id}/reference-library-items` | admin/supervisor/operator |
| 批量入库 | POST | `/reference-library/items/bulk` | 同上；`Idempotency-Key`；`?atomic=true` 仅 admin |
| 对标库列表 | GET | `/reference-library/items` | admin/supervisor/operator/**sales**（只读） |
| 更新条目 | PATCH | `/reference-library/items/{id}` | admin/supervisor/operator |
| 移出对标库（主管） | POST | `/reference-library/items/{id}/archive` | admin/supervisor |
| 撤回入库（运营） | POST | `/reference-library/items/{id}/revoke` | operator（本人 + 24h 内） |
| 规则重评 | POST | `/reference-library/items/re-evaluate` | admin/supervisor |
| 事件列表 | GET | `/reference-library/items/{id}/events` | admin/supervisor/operator/sales |
| RuleProfile 列表 | GET | `/benchmark-rule-profiles` | admin/supervisor/operator |
| RuleProfile 更新 | PUT | `/benchmark-rule-profiles/{id}` | admin/supervisor |
| 运营规则（P1 提前） | GET/POST/PATCH | `/operation-rules` | 读 operator+；写 admin/supervisor |

列表项关键字段：`content_id`, `platform`, `title`, `like_count`, `comment_count`, `candidate_bucket`, `in_reference_library`, `matched_keywords`, `reference_ai_reason`（前端）/ `metadata.ai_reason`（库内）。

OpenAPI：启动服务后访问 `/docs` 查看完整 schema（`product_schemas.py`）。

---

## 4. 权限矩阵（后端强制）

| 能力 | admin | supervisor | operator | sales |
|------|:-----:|:----------:|:--------:|:-----:|
| 情报池 / 对标库 / 场景筛选 **只读** | Y | Y | Y | Y |
| 场景筛选 **保存/删除** | Y | Y | Y | N |
| 手动/批量入库 | Y | Y | Y | N |
| 改分类/评级/标签/备注 | Y | Y | Y | N |
| 移出对标库 `archive` | Y | Y | N | N |
| 撤回入库 `revoke`（24h、本人） | — | — | Y | N |
| 规则重评 | Y | Y | N | N |
| 配置 RuleProfile | Y | Y | N | N |
| 运营规则 CRUD | Y | Y | N | N |

**采集自动分配**（`WorkflowRepository.maybe_auto_assign_from_discovery_account`）：

- 写入 `ContentDiscoveryEvent` 后，若 `account_id` 对应 `PlatformAccount.employee_id` 且员工已绑定 `user_id`，则将情报 **自动 assign** 给该用户（备注：「自动分配：由负责账号采集发现」）。
- 若条目已有 `assigned_to_user_id`（含主管手动分配），**不覆盖**。
- 运营在情报中心列表（含 **内容搜索**）可见范围：**分配给我** 或 **由本人负责平台账号的 `discovery_event.account_id` 发现**（二者满足其一即可）；不因搜索而扩大至全池。新采集仍会尝试自动 assign。

**运营撤回规则**（`ensure_can_revoke_reference_library_item`）：

- 仅 `operator` 可调用 `POST .../revoke`；
- `created_by_user_id` 须为当前用户；
- `created_at` 距今 ≤ 24 小时；
- 审计事件 `event_type=revoked`（与主管 `archived` 区分）。

**销售（sales）**：可浏览情报中心、对标作品库、读取个人场景筛选偏好；所有写接口返回 403。前端隐藏写操作按钮。

生产：`INTEL_ENGINE_ALLOW_HEADER_AUTH=false`（默认）；测试/本地可 `true`。验收：`tests/test_auth_api.py`、`tests/test_reference_library_permissions.py`。

---

## 5. P2 预留：销售写权限（未实现）

> **状态**：仅文档约定，**不在 P0/P1 实现**。

| 能力 | 计划角色 | 说明 |
|------|----------|------|
| 客资列表 / 提醒只读 | sales | 看待分配与跟进队列 |
| 跟进状态更新 | sales | 如 `contacted` / `qualified` / `closed`，**不改**对标库条目 |
| 领取/释放客资 | sales（部分） | 与主管分配策略联动 |

**边界**：销售的写操作落在 **客资/跟进域** 的新 API 与页面，不开放 `reference-library` 的 PATCH/入库/归档/撤回，避免污染运营资产库。

建议 P2 路径草案：`/api/leads/*` 或 `/api/customer-intents/*`（以实现阶段 PRD 为准）。

---

## 6. 批量操作（§7.5.3）

- 上限 50 条；响应 `succeeded` / `failed[{ id, code, message }]`
- 默认 partial success；`atomic=true` 仅 admin 全批回滚
- 成功条目写 `ReferenceLibraryEvent`

---

## 7. 前端信息架构

| 页面 | 路由 | 说明 |
|------|------|------|
| 情报中心 | `/intelligence` | 筛选 URL 持久化、批量入库、已入库条目可 **撤回入库**（运营） |
| 对标作品库 | `/reference-library` | 平台 → 选中来源 → 库类型；运营撤回 / 主管移出 |
| 规则管理 | `/rules` | 关键词规则集 + **运营规则** Tab |

**导航**：`sales` 仅见「情报中心」「对标作品库」（`canAccessRoute`）。

UI 文案：`ai` 枚举仍用 API 值，展示为 **「规则自动」**（非大模型）。

---

## 8. 性能与稳定性验收 Runbook

### 8.1 日常开发（SQLite，默认）

```powershell
cd central_server
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m pytest tests/test_intelligence_list_perf_smoke.py -q
```

冒烟：约 150 条种子，列表 P95 &lt; 500ms（`test_intelligence_list_perf_smoke.py`）。

### 8.2 P0 盖章（PostgreSQL 1 万条，可选）

```powershell
docker compose up -d
$env:INTEL_ENGINE_DATABASE_URL = "postgresql+psycopg://intel:intel@localhost:55432/intelligence_engine"
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe scripts/seed_intelligence_perf.py --count 10000
..\.venv\Scripts\python.exe scripts/bench_intelligence_list.py --samples 30
```

目标：情报列表 P95 &lt; 500ms。索引见 `0006_intelligence_perf_indexes.py`。实测结果见 `p0-acceptance-results.md`。

### 8.3 XHS SLO（阶段 6）

见 `docs/guidance/xhs_stability_slo.md`。SQLite 可跑报告脚本；成功率盖章需真实 job 数据：

```powershell
..\.venv\Scripts\python.exe scripts/xhs_slo_report.py --window-hours 24
```

---

## 9. P0 验收勾选清单（§11）

- [x] `ReferenceLibraryItem` 扩展，无平行双库
- [x] 情报筛选 + 手动/批量入库 + 事件追溯
- [x] 对标库三层管理 + manual 锁 + 批量规范
- [x] `RuleProfile` + 规则重评 + `ai_reason` / 命中词
- [x] 权限矩阵后端 enforced + sales 只读 + 运营 revoke
- [x] Central / Local Agent 边界（采集经 Job，中央不碰 Profile）
- [x] PostgreSQL **1 万条** 列表 P95 &lt; 500ms（见 `p0-acceptance-results.md`：p95≈236ms）
- [x] XHS 四类 job **≥90%** 成功率（夹具 55/类 + 报告 PASS；生产建议 Local Agent 实跑复核）

**P0 非目标（勿计入上表）**：底图库 UI、仿写/仿画工作流、Lead 表与 sales 写跟进、私信、自动发布、LLM 调用。

---

## 10. Service 迁移清单（阶段 2）

| 服务（计划） | 实际落点 |
|--------------|----------|
| `BenchmarkSelectionService` | `services/benchmark_selection.py` |
| `RuleProfileService` | `services/rule_profile.py` |
| `LeadDetectionService` | 合并在 `BenchmarkSelectionService._evaluate_target` + `CandidateDecision` 命中词 |
| `ContentScreeningService` | `filtering/candidate_classifier.py` + 情报池可见性阈值 |

Ingestion 触发：`api/routes.py`（feed/detail/comment commit 后 `ai_select_by_rules`）。
