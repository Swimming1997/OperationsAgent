# 情报中心前端契约与运行入口 V1

## 1. Task Template 表单字段

### recommendation_feed_task

创建接口：

`POST /api/task-templates/recommendation-feed`

更新接口：

`PATCH /api/task-templates/recommendation-feed/{template_id}`

字段：

| 字段 | 类型 | 必填 | 允许 null | 说明 |
|---|---|---:|---:|---|
| name | string | 是 | 否 | 任务模板名称 |
| business_account_type_id | string | 是 | 否 | 业务类型 ID |
| enabled | boolean | 否 | 否 | 是否启用，默认 true |
| feed_type | enum | 是 | 否 | 当前主要使用 xhs_home_feed |
| target_count | integer | 否 | 否 | 1-500，默认 50 |
| refresh_rounds | integer | 否 | 否 | 1-20，默认 2 |
| per_round_scroll_target | integer | 否 | 否 | 1-500，默认 50 |
| rule_set_id | string | 否 | 是 | 规则集 ID |
| behavior_profile_id | string | 否 | 是 | 行为策略 |
| network_egress_profile_id | string | 否 | 是 | 网络出口策略 |
| risk_policy_id | string | 否 | 是 | 风险预算策略 |

### creator_monitor_task

创建接口：

`POST /api/task-templates/creator-monitor`

更新接口：

`PATCH /api/task-templates/creator-monitor/{template_id}`

字段：

| 字段 | 类型 | 必填 | 允许 null | 说明 |
|---|---|---:|---:|---|
| name | string | 是 | 否 | 任务模板名称 |
| enabled | boolean | 否 | 否 | 是否启用，默认 true |
| business_account_type_id | string | 是 | 否 | 业务类型 ID |
| benchmark_group_id | string | 是 | 否 | 对标账号组 ID |
| auto_detail_fetch | boolean | 否 | 否 | 是否后续自动补详情，默认 true |
| behavior_profile_id | string | 否 | 是 | 行为策略 |
| network_egress_profile_id | string | 否 | 是 | 网络出口策略 |
| risk_policy_id | string | 否 | 是 | 风险预算策略 |

### keyword_search_task

创建接口：

`POST /api/task-templates/keyword-search`

更新接口：

`PATCH /api/task-templates/keyword-search/{template_id}`

字段：

| 字段 | 类型 | 必填 | 允许 null | 说明 |
|---|---|---:|---:|---|
| name | string | 是 | 否 | 任务模板名称 |
| enabled | boolean | 否 | 否 | 是否启用，默认 true |
| business_account_type_id | string | 是 | 否 | 业务类型 ID |
| platform | enum | 是 | 否 | 平台，当前前端只启用 xhs |
| keywords | string[] | 是 | 否 | 搜索关键词，不能为空 |
| max_items | integer | 否 | 否 | 1-500，默认 50 |
| rule_set_id | string | 否 | 是 | 规则集 ID |
| behavior_profile_id | string | 否 | 是 | 行为策略 |
| network_egress_profile_id | string | 否 | 是 | 网络出口策略 |
| risk_policy_id | string | 否 | 是 | 风险预算策略 |

通用详情接口：

`GET /api/task-templates/{template_id}`

通用列表接口：

`GET /api/task-templates/list`

列表项额外字段：`business_account_type_name`、`created_by_display_name`、`permissions`（`can_edit` / `can_run` / `can_schedule`）。

### 运行与就绪

- `GET /api/task-templates/{template_id}/readiness`：模板配置就绪（不含执行账号）
- `GET /api/task-templates/{template_id}/run-readiness?executor_account_id=`：选定账号后的运行就绪
- `POST /api/task-templates/{template_id}/run`：body `{ "executor_account_id": "..." }`（必填）

### 定时调度

- `POST /api/task-schedules`：body 含 `task_template_id`、`executor_account_id`、`schedule_type`、`interval_seconds` 等
- `PATCH /api/task-schedules/{schedule_id}`：可更新 `executor_account_id` / `enabled` 等
- `GET /api/task-templates/{template_id}/schedules`：某模板下的调度列表

operator 仅可编辑自己创建的模板；可为自有模板创建调度，且 `executor_account_id` 必须是本人有权限的采集账号。

## 2. 情报中心列表与详情接口

列表接口：

`GET /api/intelligence/contents/product`

筛选参数：

- `platform`
- `source_surface`
- `candidate_bucket`
- `workflow_status`
- `assigned_to_user_id`
- `business_keyword`
- `discovered_after`
- `discovered_before`
- `page`
- `page_size`

列表 DTO 字段：

| 字段 | 允许 null | 来源 |
|---|---:|---|
| content_id | 否 | content_identity.id |
| platform | 否 | content_identity.platform |
| content_type | 否 | content_identity.content_type |
| title | 是 | latest content_snapshots.title，回退 metadata.feed_title_or_summary |
| cover_url | 是 | latest content_snapshots.cover_url，回退 metadata.cover_url |
| author_name | 是 | latest content_snapshots.author_name，回退 metadata.author_name |
| latest_snapshot_time | 是 | content_snapshots.fetched_at |
| like_count | 是 | content_snapshots.like_count，回退 metadata.visible_like_count |
| comment_count | 是 | content_snapshots.comment_count |
| collect_count | 是 | content_snapshots.collect_count |
| candidate_bucket | 是 | candidate_decisions.candidate_bucket |
| workflow_status | 否 | content_workflow_states.workflow_status |
| assigned_to_user_id | 是 | content_workflow_states.assigned_to_user_id |
| assigned_to_user_display_name | 是 | users.display_name |
| latest_operator_note | 是 | content_workflow_states.latest_operator_note |
| discovery_sources_summary | 否 | content_discovery_events 聚合 |
| first_seen_at | 否 | content_identity.first_seen_at |
| last_seen_at | 否 | content_identity.last_seen_at |

详情接口：

`GET /api/intelligence/contents/{content_id}/product-detail`

详情 DTO：

- `identity`
- `latest_snapshot`
- `latest_candidate_decision`
- `workflow_state`
- `notes`
- `assignment_history`
- `discovery_events_summary`

## 3. Options API

推荐前端启动时调用：

`GET /api/product/options`

返回：

- `roles`
- `platforms`
- `feed_types`
- `task_template_types`
- `workflow_statuses`
- `candidate_buckets`
- `account_statuses`
- `agent_statuses`

也可按需调用：

- `GET /api/product/options/roles`
- `GET /api/product/options/platforms`
- `GET /api/product/options/feed-types`
- `GET /api/product/options/task-template-types`
- `GET /api/product/options/workflow-statuses`
- `GET /api/product/options/candidate-buckets`
- `GET /api/product/options/account-statuses`
- `GET /api/product/options/agent-statuses`

## 4. 权限约定

开发阶段使用 Header 注入身份：

```http
X-User-Id: <user_id>
X-Role: admin
```

或：

```http
X-User-Roles: admin,supervisor
```

最小权限边界：

- `admin / supervisor`：用户、员工、账号类型、对标组、任务模板、策略配置、任务手动运行、调度 materialize。
- `operator`：查看分配给自己的情报，处理内容，写备注。
- `sales`：预留，当前不展开页面权限。

未带角色 Header 访问受保护产品 API 会返回 `403`。

## 5. Scheduler 部署方式

当前阶段不启常驻 scheduler。使用 CLI 作为 Windows Task Scheduler 或 cron 的执行入口：

```powershell
.\.venv\Scripts\python.exe scripts\materialize_due_schedules.py
```

只检查不生成任务：

```powershell
.\.venv\Scripts\python.exe scripts\materialize_due_schedules.py --dry-run
```

输出 JSON：

- `schedule_count`
- `job_count`
- `materialized`

异常时返回非 0 exit code，并向 stderr 输出错误 JSON。

保留管理 API：

`POST /api/task-schedules/materialize-due`

## 6. Stage 3 前端依赖接口

任务中心页面：

- typed task template create/update/detail/list
- task schedule create/list
- manual run
- options

情报中心页面：

- product intelligence list
- product detail
- assign/select/discard/archive
- notes add/list
- options

管理下拉数据：

- product accounts
- business account types
- benchmark groups
- behavior profiles
- network egress profiles
- risk policies
- business account type rule sets
