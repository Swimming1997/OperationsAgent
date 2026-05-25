# Intelligence Engine 数据库 Schema、API Contract 与执行协议 v0.1
**文件名：** `intel-engine-schema-and-api-contract-v0.1.md`  
**版本：** v0.1  
**用途：** 作为 Codex 立即开工建设 Intelligence Engine 的**落地实现基准**。  
**前置文档：**
1. `intel-center-engine-plan-v1.md`
2. `mc-capability-benchmark.md`
3. `mc-source-audit.md`
4. `intel-engine-architecture-v0.1.md`

---

# 0. 本文要解决什么

前四份文档已经回答了：

- 为什么要做自研 Intelligence Engine；
- MediaCrawler 开源版有哪些值得借鉴和必须规避的问题；
- MediaCrawlerPro 哪些公开能力要作为第一阶段对标；
- 我们自己的引擎总架构应该怎么分层。

**本文进一步把这些抽象方案压实为可以直接编码的实现契约：**

1. 数据库表结构；
2. 核心枚举与状态机；
3. API 输入输出；
4. Job 执行与 Resume 协议；
5. Local Agent 与中心服务通信协议；
6. Feed / Detail / Comment / Creator 四类核心任务的具体输入输出；
7. Codex 第一轮建项目时必须遵守的目录、依赖、迁移与测试约束。

---

# 1. 关键技术决议

## 1.1 后端技术栈

### 正式主栈
- Python 3.11+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- PostgreSQL 作为正式主库

### 开发便利策略
- 本地开发可额外提供 SQLite 兼容配置；
- **但数据库 Schema、索引、事务、租约逻辑以 PostgreSQL 为设计基准**；
- 不要为了 SQLite 牺牲正式设计。

---

## 1.2 第一阶段任务执行方式

### 选择：DB-backed Job Queue + Worker
第一阶段不要直接上 Celery / RabbitMQ / Kafka。

理由：
1. 当前最重要的是先把采集引擎跑通；
2. 任务类型清晰，数量可控；
3. DB-backed queue 足以支持：
   - pending / running / success / failed；
   - lease；
   - retry；
   - resume；
   - local agent claim；
4. 后续如果任务量扩大，再切换到 Redis Queue / Celery / 其他调度系统。

### 但要设计出可替换边界
代码中应有：
```python
class JobQueueRepository(Protocol):
    ...
```

未来替换底层队列时，Application Service 不大改。

---

## 1.3 单体中心服务 + 本地 Agent
第一阶段落地形态：

```text
Center Server
- FastAPI
- PostgreSQL
- Job Scheduler / Dispatcher
- Dedup / Lease / Query

Local Agent
- 运行在员工电脑
- 绑定 local_agent_id
- claim 指派任务
- 本地调用 Playwright/CDP 与平台 Connector
- 上报结果、错误、心跳
```

---

## 1.4 不做的事
第一阶段暂不做：
- 分布式消息队列；
- Kubernetes；
- 完整 RBAC；
- 完整前端；
- AI 深度判断；
- 视频/图片资源批量下载；
- 复杂代理池产品化；
- 平台规模化横向扩展到快手/B站等。

---

# 2. 核心枚举与常量

## 2.1 Platform

```python
class Platform(str, Enum):
    XHS = "xhs"
    DOUYIN = "douyin"
```

---

## 2.2 FeedType

```python
class FeedType(str, Enum):
    XHS_HOME_FEED = "xhs_home_feed"
    DOUYIN_VIDEO_HOME_FEED = "douyin_video_home_feed"
    DOUYIN_IMAGE_HOME_FEED = "douyin_image_home_feed"
```

---

## 2.3 SourceSurface

```python
class SourceSurface(str, Enum):
    XHS_HOME_FEED = "xhs_home_feed"
    DOUYIN_VIDEO_HOME_FEED = "douyin_video_home_feed"
    DOUYIN_IMAGE_HOME_FEED = "douyin_image_home_feed"
    SEARCH = "search"
    CREATOR_MONITOR = "creator_monitor"
    MANUAL_IMPORT = "manual_import"
```

---

## 2.4 ContentType

```python
class ContentType(str, Enum):
    IMAGE_TEXT = "image_text"
    VIDEO = "video"
    UNKNOWN = "unknown"
```

---

## 2.5 AccountStatus

```python
class AccountStatus(str, Enum):
    ACTIVE = "active"
    NEED_LOGIN = "need_login"
    NEED_MANUAL_VERIFY = "need_manual_verify"
    DEGRADED = "degraded"
    PAUSED = "paused"
    DISABLED = "disabled"
```

---

## 2.6 SessionStatus

```python
class SessionStatus(str, Enum):
    READY = "ready"
    EXPIRED = "expired"
    MANUAL_VERIFY_REQUIRED = "manual_verify_required"
    UNAVAILABLE = "unavailable"
```

---

## 2.7 AgentStatus

```python
class AgentStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
```

---

## 2.8 JobType

```python
class JobType(str, Enum):
    FEED_COLLECT = "feed_collect"
    DETAIL_FETCH = "detail_fetch"
    COMMENT_FETCH = "comment_fetch"
    CREATOR_MONITOR = "creator_monitor"
    SEARCH_COLLECT = "search_collect"
    MEDIA_DOWNLOAD = "media_download"
```

`MEDIA_DOWNLOAD` 第一阶段仅预留，不作为必做主链路。

---

## 2.9 JobStatus

```python
class JobStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    PARTIAL_SUCCESS = "partial_success"
    SUCCESS = "success"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
```

### 为什么需要 CLAIMED
Local Agent claim 任务后，任务尚未真正执行；  
如果 Agent claim 后崩溃，可根据 `claim_expires_at` 重新放回 PENDING。

---

## 2.10 LeaseResourceType

```python
class LeaseResourceType(str, Enum):
    DETAIL_FETCH = "detail_fetch"
    COMMENT_FETCH = "comment_fetch"
    CREATOR_MONITOR = "creator_monitor"
```

---

## 2.11 CandidateBucket

```python
class CandidateBucket(str, Enum):
    LEAD_CANDIDATE = "lead_candidate"
    CONTENT_CANDIDATE = "content_candidate"
    PENDING_ENRICHMENT = "pending_enrichment"
    DISCARD = "discard"
```

---

## 2.12 ErrorCode

```python
class ErrorCode(str, Enum):
    AUTH_REQUIRED = "auth_required"
    MANUAL_VERIFY_REQUIRED = "manual_verify_required"
    SESSION_EXPIRED = "session_expired"
    SESSION_CONNECT_FAILED = "session_connect_failed"
    SIGNATURE_INVALID = "signature_invalid"
    CONTENT_NOT_FOUND = "content_not_found"
    CREATOR_NOT_FOUND = "creator_not_found"
    REMOTE_BLOCKED = "remote_blocked"
    RATE_LIMITED = "rate_limited"
    STRUCTURE_CHANGED = "structure_changed"
    RETRYABLE_NETWORK_ERROR = "retryable_network_error"
    NON_RETRYABLE_PLATFORM_ERROR = "non_retryable_platform_error"
    INTERNAL_ENGINE_ERROR = "internal_engine_error"
```

---

# 3. 数据库 Schema 总览

## 3.1 表清单

### 基础主体
1. `employees`
2. `local_agents`
3. `platform_accounts`
4. `account_sessions`

### 任务与调度
5. `jobs`
6. `job_events`
7. `fetch_leases`

### 内容资产
8. `content_identity`
9. `content_discovery_events`
10. `content_snapshots`
11. `comment_snapshots`
12. `candidate_decisions`

### 对标监控
13. `creator_monitors`
14. `creator_monitor_events`

### 规则配置
15. `keyword_rule_sets`
16. `keyword_rules`

---

# 4. 表结构详细设计

---

# 4.1 employees

第一阶段先做最简员工表，不展开完整 RBAC。

```sql
CREATE TABLE employees (
    id                  UUID PRIMARY KEY,
    display_name        VARCHAR(128) NOT NULL,
    email               VARCHAR(255),
    status              VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 说明
- `status` 第一阶段可简单用 `active / disabled`；
- 后续正式权限系统再扩展角色。

---

# 4.2 local_agents

每台员工电脑上的 Agent 注册记录。

```sql
CREATE TABLE local_agents (
    id                  UUID PRIMARY KEY,
    employee_id         UUID REFERENCES employees(id),
    device_name         VARCHAR(255),
    machine_fingerprint VARCHAR(255),
    status              VARCHAR(32) NOT NULL DEFAULT 'offline',
    agent_version       VARCHAR(64),
    capabilities_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_heartbeat_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 关键索引
```sql
CREATE INDEX idx_local_agents_employee_id ON local_agents(employee_id);
CREATE INDEX idx_local_agents_status ON local_agents(status);
CREATE INDEX idx_local_agents_last_heartbeat ON local_agents(last_heartbeat_at);
```

### capabilities_json 示例
```json
{
  "platforms": ["xhs", "douyin"],
  "supports_cdp": true,
  "supports_browser_profile": true,
  "supports_request_session": true
}
```

---

# 4.3 platform_accounts

运营账号实体。

```sql
CREATE TABLE platform_accounts (
    id                  UUID PRIMARY KEY,
    employee_id         UUID REFERENCES employees(id),
    platform            VARCHAR(32) NOT NULL,
    display_name        VARCHAR(255) NOT NULL,
    external_account_id VARCHAR(255),
    business_account_type VARCHAR(128),
    status              VARCHAR(64) NOT NULL DEFAULT 'active',
    default_agent_id    UUID REFERENCES local_agents(id),
    metadata_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_success_at     TIMESTAMPTZ,
    last_failure_at     TIMESTAMPTZ,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 唯一约束
```sql
CREATE UNIQUE INDEX uq_platform_accounts_unique_external
ON platform_accounts(platform, external_account_id)
WHERE external_account_id IS NOT NULL;
```

### 关键索引
```sql
CREATE INDEX idx_platform_accounts_employee_id ON platform_accounts(employee_id);
CREATE INDEX idx_platform_accounts_platform ON platform_accounts(platform);
CREATE INDEX idx_platform_accounts_status ON platform_accounts(status);
CREATE INDEX idx_platform_accounts_agent ON platform_accounts(default_agent_id);
```

### metadata_json 示例
```json
{
  "remark": "论文代投方向账号",
  "preferred_feed_types": ["xhs_home_feed"],
  "manual_login_note": "由员工A维护"
}
```

---

# 4.4 account_sessions

账号与具体本地会话绑定。

```sql
CREATE TABLE account_sessions (
    id                  UUID PRIMARY KEY,
    account_id          UUID NOT NULL REFERENCES platform_accounts(id),
    local_agent_id      UUID NOT NULL REFERENCES local_agents(id),
    platform            VARCHAR(32) NOT NULL,
    session_type        VARCHAR(32) NOT NULL,
    profile_ref         VARCHAR(255),
    cookie_ref          VARCHAR(255),
    status              VARCHAR(64) NOT NULL DEFAULT 'unavailable',
    session_meta_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_validated_at   TIMESTAMPTZ,
    last_used_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### session_type
```text
browser
request
```

### 关键约束
同一个账号在一个 Agent 上，同一种 session_type 只允许一个活跃会话：

```sql
CREATE UNIQUE INDEX uq_account_session_per_agent_type
ON account_sessions(account_id, local_agent_id, session_type);
```

### 索引
```sql
CREATE INDEX idx_account_sessions_account_id ON account_sessions(account_id);
CREATE INDEX idx_account_sessions_agent_id ON account_sessions(local_agent_id);
CREATE INDEX idx_account_sessions_status ON account_sessions(status);
```

### profile_ref 示例
```text
profiles/xhs_acc_001
profiles/douyin_acc_003
```

---

# 4.5 jobs

任务主表。

```sql
CREATE TABLE jobs (
    id                  UUID PRIMARY KEY,
    job_type            VARCHAR(64) NOT NULL,
    status              VARCHAR(64) NOT NULL DEFAULT 'pending',
    priority            INTEGER NOT NULL DEFAULT 100,

    account_id          UUID REFERENCES platform_accounts(id),
    local_agent_id      UUID REFERENCES local_agents(id),
    creator_monitor_id  UUID,

    payload_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    checkpoint_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    retry_count         INTEGER NOT NULL DEFAULT 0,
    max_retries         INTEGER NOT NULL DEFAULT 3,
    last_error_code     VARCHAR(128),
    last_error_message  TEXT,

    claimed_by_agent_id UUID REFERENCES local_agents(id),
    claimed_at          TIMESTAMPTZ,
    claim_expires_at    TIMESTAMPTZ,

    scheduled_at        TIMESTAMPTZ,
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 索引
```sql
CREATE INDEX idx_jobs_status_priority
ON jobs(status, priority, scheduled_at);

CREATE INDEX idx_jobs_account_id ON jobs(account_id);
CREATE INDEX idx_jobs_agent_id ON jobs(local_agent_id);
CREATE INDEX idx_jobs_claim_expiry ON jobs(claim_expires_at);
CREATE INDEX idx_jobs_job_type ON jobs(job_type);
```

### creator_monitor_id 外键
可在迁移中，等 `creator_monitors` 表创建后再补：

```sql
ALTER TABLE jobs
ADD CONSTRAINT fk_jobs_creator_monitor
FOREIGN KEY (creator_monitor_id) REFERENCES creator_monitors(id);
```

---

# 4.6 job_events

记录任务执行过程。

```sql
CREATE TABLE job_events (
    id                  UUID PRIMARY KEY,
    job_id              UUID NOT NULL REFERENCES jobs(id),
    event_type          VARCHAR(128) NOT NULL,
    event_payload_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 索引
```sql
CREATE INDEX idx_job_events_job_id_created
ON job_events(job_id, created_at);
```

### event_type 建议
```text
job_created
job_claimed
job_started
checkpoint_updated
item_discovered
item_failed
job_partial_success
job_success
job_failed
job_paused
job_resumed
```

---

# 4.7 fetch_leases

用于防止内容详情、评论、对标监控被重复执行。

```sql
CREATE TABLE fetch_leases (
    id                  UUID PRIMARY KEY,
    resource_type       VARCHAR(64) NOT NULL,
    resource_key        VARCHAR(255) NOT NULL,
    owner_job_id        UUID NOT NULL REFERENCES jobs(id),
    acquired_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ NOT NULL,
    released_at         TIMESTAMPTZ,
    status              VARCHAR(32) NOT NULL DEFAULT 'active'
);
```

### 唯一约束
同一资源同时只能有一个 active lease：

```sql
CREATE UNIQUE INDEX uq_fetch_leases_active_resource
ON fetch_leases(resource_type, resource_key)
WHERE status = 'active';
```

### 资源键示例
```text
detail:xhs:{content_id}
comments:douyin:{content_id}
creator_monitor:{creator_monitor_id}
```

---

# 4.8 content_identity

内容唯一身份表。

```sql
CREATE TABLE content_identity (
    id                      UUID PRIMARY KEY,
    platform                VARCHAR(32) NOT NULL,
    platform_content_id     VARCHAR(255) NOT NULL,
    canonical_url           TEXT,
    content_type            VARCHAR(64) NOT NULL DEFAULT 'unknown',

    first_seen_at           TIMESTAMPTZ NOT NULL,
    last_seen_at            TIMESTAMPTZ NOT NULL,

    latest_snapshot_id      UUID,
    metadata_json           JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 唯一约束
```sql
CREATE UNIQUE INDEX uq_content_identity_platform_content
ON content_identity(platform, platform_content_id);
```

### 索引
```sql
CREATE INDEX idx_content_identity_last_seen ON content_identity(last_seen_at);
CREATE INDEX idx_content_identity_platform ON content_identity(platform);
CREATE INDEX idx_content_identity_content_type ON content_identity(content_type);
```

---

# 4.9 content_discovery_events

记录“谁在哪个任务、哪个推荐页、哪个账号看到过这个内容”。

```sql
CREATE TABLE content_discovery_events (
    id                      UUID PRIMARY KEY,
    content_id              UUID NOT NULL REFERENCES content_identity(id),
    job_id                  UUID REFERENCES jobs(id),
    account_id              UUID REFERENCES platform_accounts(id),

    platform                VARCHAR(32) NOT NULL,
    source_surface          VARCHAR(64) NOT NULL,
    feed_type               VARCHAR(64),
    feed_position           INTEGER,
    discovered_at           TIMESTAMPTZ NOT NULL,

    discovery_meta_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 索引
```sql
CREATE INDEX idx_discovery_content_id ON content_discovery_events(content_id);
CREATE INDEX idx_discovery_account_id ON content_discovery_events(account_id);
CREATE INDEX idx_discovery_job_id ON content_discovery_events(job_id);
CREATE INDEX idx_discovery_discovered_at ON content_discovery_events(discovered_at);
CREATE INDEX idx_discovery_surface ON content_discovery_events(source_surface);
```

---

# 4.10 content_snapshots

详情快照表。  
一个内容可以有多次快照，因为点赞/评论数会变化。

```sql
CREATE TABLE content_snapshots (
    id                      UUID PRIMARY KEY,
    content_id              UUID NOT NULL REFERENCES content_identity(id),

    title                   TEXT,
    body_text               TEXT,
    author_platform_id      VARCHAR(255),
    author_name             VARCHAR(255),
    author_avatar_url       TEXT,

    cover_url               TEXT,
    image_urls_json         JSONB NOT NULL DEFAULT '[]'::jsonb,
    video_url               TEXT,

    like_count              BIGINT,
    comment_count           BIGINT,
    collect_count           BIGINT,
    share_count             BIGINT,

    publish_time            TIMESTAMPTZ,
    fetch_source_account_id UUID REFERENCES platform_accounts(id),

    raw_payload_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at              TIMESTAMPTZ NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 索引
```sql
CREATE INDEX idx_content_snapshots_content_id
ON content_snapshots(content_id, fetched_at DESC);

CREATE INDEX idx_content_snapshots_publish_time
ON content_snapshots(publish_time);
```

### latest_snapshot_id 外键
迁移时补：

```sql
ALTER TABLE content_identity
ADD CONSTRAINT fk_content_identity_latest_snapshot
FOREIGN KEY (latest_snapshot_id) REFERENCES content_snapshots(id);
```

---

# 4.11 comment_snapshots

评论快照表。

```sql
CREATE TABLE comment_snapshots (
    id                      UUID PRIMARY KEY,
    content_id              UUID NOT NULL REFERENCES content_identity(id),
    platform_comment_id     VARCHAR(255) NOT NULL,

    parent_platform_comment_id VARCHAR(255),
    author_platform_id      VARCHAR(255),
    author_name             VARCHAR(255),
    author_avatar_url       TEXT,

    body_text               TEXT NOT NULL,
    like_count              BIGINT,
    created_time            TIMESTAMPTZ,

    raw_payload_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at              TIMESTAMPTZ NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 唯一约束
评论对同一内容的基础身份唯一：

```sql
CREATE UNIQUE INDEX uq_comment_per_content_platform_comment
ON comment_snapshots(content_id, platform_comment_id);
```

### 索引
```sql
CREATE INDEX idx_comments_content_id ON comment_snapshots(content_id);
CREATE INDEX idx_comments_fetched_at ON comment_snapshots(fetched_at);
```

---

# 4.12 candidate_decisions

内容规则筛选结果。

```sql
CREATE TABLE candidate_decisions (
    id                      UUID PRIMARY KEY,
    content_id              UUID NOT NULL REFERENCES content_identity(id),
    snapshot_id             UUID REFERENCES content_snapshots(id),

    business_keyword_hits_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    lead_keyword_hits_json     JSONB NOT NULL DEFAULT '[]'::jsonb,
    comment_keyword_hits_json  JSONB NOT NULL DEFAULT '[]'::jsonb,

    like_threshold_hit      BOOLEAN NOT NULL DEFAULT FALSE,
    comment_threshold_hit   BOOLEAN NOT NULL DEFAULT FALSE,

    candidate_bucket        VARCHAR(64) NOT NULL,
    decision_reason_json    JSONB NOT NULL DEFAULT '{}'::jsonb,

    evaluated_at            TIMESTAMPTZ NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 索引
```sql
CREATE INDEX idx_candidate_decisions_content_id
ON candidate_decisions(content_id, evaluated_at DESC);

CREATE INDEX idx_candidate_decisions_bucket
ON candidate_decisions(candidate_bucket);
```

---

# 4.13 creator_monitors

对标账号监控配置。

```sql
CREATE TABLE creator_monitors (
    id                      UUID PRIMARY KEY,
    platform                VARCHAR(32) NOT NULL,
    creator_platform_id     VARCHAR(255) NOT NULL,
    creator_display_name    VARCHAR(255),

    monitor_group_key       VARCHAR(128),
    mapped_business_account_type VARCHAR(128),

    enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
    check_interval_seconds  INTEGER NOT NULL DEFAULT 900,

    last_checked_at         TIMESTAMPTZ,
    last_success_at         TIMESTAMPTZ,
    last_error_code         VARCHAR(128),
    last_error_message      TEXT,

    last_cursor_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json           JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 唯一约束
```sql
CREATE UNIQUE INDEX uq_creator_monitor_platform_creator
ON creator_monitors(platform, creator_platform_id);
```

### 索引
```sql
CREATE INDEX idx_creator_monitors_enabled
ON creator_monitors(enabled);

CREATE INDEX idx_creator_monitors_group_key
ON creator_monitors(monitor_group_key);
```

---

# 4.14 creator_monitor_events

对标账号发现新内容事件。

```sql
CREATE TABLE creator_monitor_events (
    id                      UUID PRIMARY KEY,
    creator_monitor_id      UUID NOT NULL REFERENCES creator_monitors(id),
    content_id              UUID REFERENCES content_identity(id),

    event_type              VARCHAR(128) NOT NULL,
    event_payload_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### event_type
```text
new_content_detected
monitor_run_success
monitor_run_failed
```

---

# 4.15 keyword_rule_sets

关键词规则集合。

```sql
CREATE TABLE keyword_rule_sets (
    id                      UUID PRIMARY KEY,
    name                    VARCHAR(255) NOT NULL,
    rule_scope              VARCHAR(64) NOT NULL,
    enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
    config_json             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### rule_scope
```text
business_keywords
lead_intent_keywords
comment_lead_keywords
```

---

# 4.16 keyword_rules

具体关键词规则。

```sql
CREATE TABLE keyword_rules (
    id                      UUID PRIMARY KEY,
    rule_set_id             UUID NOT NULL REFERENCES keyword_rule_sets(id),
    keyword                 VARCHAR(255) NOT NULL,
    normalized_keyword      VARCHAR(255),
    match_mode              VARCHAR(64) NOT NULL DEFAULT 'contains',
    enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
    weight                  INTEGER NOT NULL DEFAULT 1,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### match_mode
```text
contains
exact
regex
```

---

# 5. Job 状态机

## 5.1 总体流转

```text
PENDING
  ↓ claim
CLAIMED
  ↓ start
RUNNING
  ├─→ SUCCESS
  ├─→ PARTIAL_SUCCESS
  ├─→ FAILED
  ├─→ PAUSED
  └─→ CANCELLED
```

---

## 5.2 Claim 机制

Local Agent 拉任务时：

1. Server 查找：
   - `status = pending`
   - `scheduled_at <= now()` 或 `scheduled_at is null`
   - `local_agent_id is null` 或者匹配当前 Agent
   - 账号默认 Agent 匹配当前 Agent

2. 使用事务 + 行锁 claim：
   - `status = claimed`
   - `claimed_by_agent_id = current_agent`
   - `claimed_at = now()`
   - `claim_expires_at = now() + N seconds`

3. 返回 JobSpec 给 Agent。

---

## 5.3 Claim 过期重入队
若：
```text
status = claimed
AND claim_expires_at < now()
```

则调度器将其重置：
```text
status = pending
claimed_by_agent_id = null
claimed_at = null
claim_expires_at = null
```

---

## 5.4 Running 心跳
长任务执行时，本地 Agent 需要定期上报：
- job_id
- checkpoint_json
- partial metrics
- lease renewal（如果有）

---

## 5.5 Resume
只有以下状态允许恢复：
```text
paused
failed（retry_count < max_retries 且错误可重试）
partial_success（按策略）
```

恢复后：
```text
status = pending
retry_count += 1（failed场景）
checkpoint_json 保留
```

---

# 6. 各 JobType 的 payload 与 checkpoint 契约

---

# 6.1 FEED_COLLECT

## 创建 payload

```json
{
  "feed_type": "xhs_home_feed",
  "target_count": 50,
  "refresh_rounds": 2,
  "per_round_scroll_target": 50,
  "detail_enqueue_policy": "candidate_only",
  "comment_enqueue_policy": "after_detail_filter"
}
```

## checkpoint_json

```json
{
  "current_round": 1,
  "items_seen_in_current_round": 32,
  "total_items_seen": 82,
  "unique_candidates_emitted": 64,
  "last_discovered_platform_content_ids": [
    "abc",
    "def"
  ],
  "runtime_hint": {
    "scroll_count": 11,
    "page_reload_count": 1
  }
}
```

## result_summary_json

```json
{
  "raw_items_seen": 100,
  "normalized_items": 96,
  "unique_contents_inserted": 71,
  "duplicate_contents": 25,
  "detail_jobs_enqueued": 31,
  "failed_items": 4
}
```

---

# 6.2 DETAIL_FETCH

## payload_json

```json
{
  "content_id": "uuid",
  "platform": "xhs",
  "platform_content_id": "xxx",
  "preferred_fetch_mode": "request_first_with_browser_fallback"
}
```

## checkpoint_json
详情任务通常无复杂 checkpoint，可保留：

```json
{
  "attempted_modes": ["request"],
  "last_mode": "request"
}
```

## result_summary_json

```json
{
  "snapshot_id": "uuid",
  "detail_fetch_mode_used": "request",
  "comment_job_enqueued": true,
  "candidate_decision_enqueued": true
}
```

---

# 6.3 COMMENT_FETCH

## payload_json

```json
{
  "content_id": "uuid",
  "platform": "douyin",
  "platform_content_id": "xxx",
  "max_comments": 20,
  "include_sub_comments": false
}
```

## checkpoint_json

```json
{
  "cursor": "opaque_or_page_cursor",
  "comments_fetched": 10,
  "has_more": true
}
```

## result_summary_json

```json
{
  "comments_inserted": 18,
  "comments_updated": 2,
  "lead_keyword_hits": ["求推荐", "怎么联系"]
}
```

---

# 6.4 CREATOR_MONITOR

## payload_json

```json
{
  "creator_monitor_id": "uuid",
  "platform": "xhs",
  "max_latest_items": 20
}
```

## checkpoint_json

```json
{
  "last_cursor": "opaque_cursor",
  "last_seen_platform_content_ids": ["a", "b", "c"]
}
```

## result_summary_json

```json
{
  "items_seen": 20,
  "new_contents_detected": 3,
  "new_content_ids": ["uuid1", "uuid2", "uuid3"]
}
```

---

# 6.5 SEARCH_COLLECT

## payload_json

```json
{
  "platform": "xhs",
  "account_id": "uuid",
  "keywords": ["论文代投", "sci投稿"],
  "max_items": 50
}
```

## checkpoint_json

```json
{
  "keyword_index": 0,
  "page_or_cursor": "opaque",
  "items_seen": 20
}
```

---

# 7. Fetch Lease 契约

## 7.1 何时申请 lease

### Detail Fetch
处理内容详情前申请：
```text
resource_type = detail_fetch
resource_key = detail:{platform}:{content_id}
```

### Comment Fetch
处理评论前申请：
```text
resource_type = comment_fetch
resource_key = comments:{platform}:{content_id}
```

### Creator Monitor
执行对标账号监控前申请：
```text
resource_type = creator_monitor
resource_key = creator_monitor:{creator_monitor_id}
```

---

## 7.2 lease 默认时长
第一阶段建议：

| 类型 | Lease TTL |
|---|---:|
| detail_fetch | 5 分钟 |
| comment_fetch | 10 分钟 |
| creator_monitor | 10 分钟 |

---

## 7.3 lease 获取失败
如果当前已有 active lease：
- 不重复执行；
- 当前 job 可：
  - 标记 `partial_success` 并注明 `lease_conflict`;
  - 或保留为 `pending` 延迟重试；
- 第一阶段建议：
  - Detail / Comment：当前 job 标记 `partial_success`
  - Creator Monitor：不重复执行，跳过本轮。

---

# 8. 内容去重协议

## 8.1 Feed Candidate 标准输入

```json
{
  "platform": "xhs",
  "platform_content_id": "xxxx",
  "canonical_url": "https://...",
  "content_type": "image_text",
  "title_or_summary": "xxxx",
  "cover_url": "https://...",
  "author_platform_id": "user_xxx",
  "author_name": "昵称",
  "visible_like_count": 123,
  "source_surface": "xhs_home_feed",
  "feed_type": "xhs_home_feed",
  "feed_position": 12,
  "discovered_at": "2026-05-18T12:00:00+08:00"
}
```

---

## 8.2 Server 处理流程

```text
1. 根据 (platform, platform_content_id) 查 content_identity
2. 如果不存在：
   - insert content_identity
   - 写 discovery_event
   - 根据初步规则决定是否生成 DETAIL_FETCH
3. 如果存在：
   - update last_seen_at
   - 写 discovery_event
   - 判断是否需要刷新详情快照
4. 返回 ingestion result 给 Agent
```

---

## 8.3 ingestion result

```json
{
  "accepted": true,
  "content_id": "uuid",
  "is_new_content": true,
  "discovery_event_id": "uuid",
  "detail_job_enqueued": true
}
```

---

# 9. Candidate Decision 规则契约

## 9.1 规则来源
第一阶段由数据库规则表读取：
- 业务关键词；
- 求推/求推荐/咨询意向关键词；
- 评论线索关键词。

---

## 9.2 第一阶段建议默认规则集合

### 业务关键词示例
```text
SCI
论文
期刊
投稿
代投
刊物
发表
```

### 意向关键词示例
```text
求推
求推荐
推一下
有没有渠道
怎么联系
求介绍
```

这些词仅作为默认种子，后续可后台配置。

---

## 9.3 评估时机
建议分两次：

### A. Feed-level preliminary filter
基于：
- 标题/摘要；
- 可见点赞；
- Feed 页面上能拿到的字段。

决定：
- 是否进入 DETAIL_FETCH；
- 是否直接丢弃。

### B. Detail-level final preliminary filter
基于：
- 完整正文；
- 精确点赞；
- 评论预览。

决定：
- `lead_candidate`
- `content_candidate`
- `discard`

---

# 10. API Contract

---

# 10.1 Agent 注册与心跳

## POST `/api/agents/register`

### Request
```json
{
  "employee_id": "uuid",
  "device_name": "员工A电脑",
  "machine_fingerprint": "sha256:...",
  "agent_version": "0.1.0",
  "capabilities": {
    "platforms": ["xhs", "douyin"],
    "supports_cdp": true,
    "supports_browser_profile": true
  }
}
```

### Response
```json
{
  "agent_id": "uuid",
  "status": "online"
}
```

---

## POST `/api/agents/{agent_id}/heartbeat`

### Request
```json
{
  "status": "online",
  "running_job_ids": ["uuid1", "uuid2"],
  "session_health": [
    {
      "account_id": "uuid",
      "session_status": "ready"
    }
  ]
}
```

### Response
```json
{
  "accepted": true,
  "server_time": "2026-05-18T12:00:00+08:00"
}
```

---

# 10.2 账号接口

## POST `/api/accounts`

### Request
```json
{
  "employee_id": "uuid",
  "platform": "xhs",
  "display_name": "小红书A号",
  "external_account_id": null,
  "business_account_type": "A",
  "default_agent_id": "uuid",
  "metadata": {
    "remark": "员工A负责"
  }
}
```

### Response
```json
{
  "account_id": "uuid",
  "status": "active"
}
```

---

## GET `/api/accounts`

支持 query：
- `employee_id`
- `platform`
- `status`

---

## POST `/api/accounts/{account_id}/sessions`

### Request
```json
{
  "local_agent_id": "uuid",
  "session_type": "browser",
  "profile_ref": "profiles/xhs_acc_001",
  "status": "ready",
  "session_meta": {
    "login_mode": "manual_browser_profile"
  }
}
```

### Response
```json
{
  "session_id": "uuid"
}
```

---

# 10.3 Job 接口

## POST `/api/jobs/feed-collect`

### Request
```json
{
  "account_id": "uuid",
  "feed_type": "xhs_home_feed",
  "target_count": 50,
  "refresh_rounds": 2,
  "per_round_scroll_target": 50,
  "priority": 100
}
```

### Response
```json
{
  "job_id": "uuid",
  "status": "pending"
}
```

---

## POST `/api/jobs/creator-monitor`

### Request
```json
{
  "creator_monitor_id": "uuid",
  "priority": 100
}
```

---

## GET `/api/jobs/{job_id}`

### Response
```json
{
  "id": "uuid",
  "job_type": "feed_collect",
  "status": "running",
  "payload": {},
  "checkpoint": {},
  "result_summary": {},
  "retry_count": 0,
  "last_error_code": null,
  "last_error_message": null
}
```

---

## POST `/api/jobs/{job_id}/pause`

---

## POST `/api/jobs/{job_id}/resume`

---

# 10.4 Agent Claim Job

## POST `/api/agents/{agent_id}/jobs/claim`

### Request
```json
{
  "max_jobs": 1,
  "supported_job_types": [
    "feed_collect",
    "detail_fetch",
    "comment_fetch",
    "creator_monitor"
  ]
}
```

### Response
```json
{
  "jobs": [
    {
      "job_id": "uuid",
      "job_type": "feed_collect",
      "account_id": "uuid",
      "payload": {},
      "checkpoint": {},
      "claim_expires_at": "2026-05-18T12:05:00+08:00"
    }
  ]
}
```

---

# 10.5 Agent Start / Progress / Complete

## POST `/api/jobs/{job_id}/start`

### Request
```json
{
  "agent_id": "uuid"
}
```

---

## POST `/api/jobs/{job_id}/progress`

### Request
```json
{
  "agent_id": "uuid",
  "checkpoint": {},
  "partial_metrics": {
    "items_seen": 32,
    "unique_emitted": 25
  }
}
```

---

## POST `/api/jobs/{job_id}/complete`

### Request
```json
{
  "agent_id": "uuid",
  "status": "success",
  "result_summary": {}
}
```

---

## POST `/api/jobs/{job_id}/fail`

### Request
```json
{
  "agent_id": "uuid",
  "error": {
    "code": "manual_verify_required",
    "message": "XHS account requires manual verification",
    "retryable": false,
    "raw_context": {}
  },
  "checkpoint": {}
}
```

---

# 10.6 Feed Candidate Ingestion

## POST `/api/ingestion/feed-candidates`

### Request
```json
{
  "job_id": "uuid",
  "account_id": "uuid",
  "candidates": [
    {
      "platform": "xhs",
      "platform_content_id": "abc",
      "canonical_url": "https://...",
      "content_type": "image_text",
      "title_or_summary": "xxx",
      "cover_url": "https://...",
      "author_platform_id": "u1",
      "author_name": "作者",
      "visible_like_count": 666,
      "source_surface": "xhs_home_feed",
      "feed_type": "xhs_home_feed",
      "feed_position": 12,
      "discovered_at": "2026-05-18T12:00:00+08:00",
      "raw_payload": {}
    }
  ]
}
```

### Response
```json
{
  "results": [
    {
      "platform_content_id": "abc",
      "content_id": "uuid",
      "is_new_content": true,
      "detail_job_enqueued": true,
      "discovery_event_id": "uuid"
    }
  ]
}
```

---

# 10.7 Detail Result Ingestion

## POST `/api/ingestion/content-detail`

### Request
```json
{
  "job_id": "uuid",
  "content_id": "uuid",
  "snapshot": {
    "title": "标题",
    "body_text": "正文",
    "author_platform_id": "u1",
    "author_name": "作者",
    "cover_url": "https://...",
    "image_urls": ["https://..."],
    "video_url": null,
    "like_count": 1000,
    "comment_count": 88,
    "collect_count": 50,
    "share_count": 12,
    "publish_time": "2026-05-18T10:00:00+08:00",
    "raw_payload": {}
  }
}
```

### Response
```json
{
  "snapshot_id": "uuid",
  "candidate_decision_enqueued": true,
  "comment_job_enqueued": true
}
```

---

# 10.8 Comment Result Ingestion

## POST `/api/ingestion/comments`

### Request
```json
{
  "job_id": "uuid",
  "content_id": "uuid",
  "comments": [
    {
      "platform_comment_id": "c1",
      "parent_platform_comment_id": null,
      "author_platform_id": "u2",
      "author_name": "评论者",
      "body_text": "求推荐",
      "like_count": 3,
      "created_time": "2026-05-18T11:00:00+08:00",
      "raw_payload": {}
    }
  ]
}
```

### Response
```json
{
  "inserted": 1,
  "updated": 0,
  "lead_keyword_hits": ["求推荐"]
}
```

---

# 10.9 查询情报内容

## GET `/api/intelligence/contents`

### Query 支持
- `platform`
- `candidate_bucket`
- `keyword`
- `discovered_after`
- `discovered_before`
- `account_id`
- `source_surface`
- `page`
- `page_size`

### Response
```json
{
  "items": [
    {
      "content_id": "uuid",
      "platform": "xhs",
      "content_type": "image_text",
      "title": "标题",
      "author_name": "作者",
      "cover_url": "https://...",
      "like_count": 1000,
      "comment_count": 88,
      "candidate_bucket": "lead_candidate",
      "latest_discovered_at": "2026-05-18T12:00:00+08:00"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 100
}
```

---

# 10.10 对标监控接口

## POST `/api/creator-monitors`

### Request
```json
{
  "platform": "xhs",
  "creator_platform_id": "creator_123",
  "creator_display_name": "对标账号A",
  "monitor_group_key": "A类账号对标",
  "mapped_business_account_type": "A",
  "check_interval_seconds": 900
}
```

### Response
```json
{
  "creator_monitor_id": "uuid"
}
```

---

## GET `/api/creator-monitors`

---

## GET `/api/creator-monitor-events`

支持 query：
- `creator_monitor_id`
- `event_type`
- `created_after`

---

# 11. Local Agent 执行协议

## 11.1 Agent 启动
Agent 启动后：

1. 注册或读取本地已有 `agent_id`；
2. 发心跳；
3. 周期性 claim job；
4. 按 job_type 调度到本地 executor。

---

## 11.2 Agent 内部模块建议

```text
local_agent/
├── agent_runtime.py
├── config.py
├── job_poller.py
├── executors/
│   ├── feed_collect_executor.py
│   ├── detail_fetch_executor.py
│   ├── comment_fetch_executor.py
│   └── creator_monitor_executor.py
├── browser/
│   ├── profile_registry.py
│   ├── browser_session_provider.py
│   └── cdp_runtime.py
├── clients/
│   ├── center_server_client.py
│   └── ingestion_client.py
└── health/
    └── heartbeat.py
```

---

## 11.3 Agent 任务执行通用伪代码

```python
async def run_claimed_job(job: ClaimedJob):
    await api.start_job(job.id)

    try:
        result = await executor_registry[job.job_type].execute(job)

        await api.complete_job(
            job.id,
            status=result.status,
            result_summary=result.summary,
        )
    except EngineError as e:
        await api.fail_job(
            job.id,
            error=e.to_api_error(),
            checkpoint=e.checkpoint,
        )
```

---

# 12. Connector Result 契约

## 12.1 Feed Connector 输出

```python
@dataclass
class FeedCandidate:
    platform: Platform
    platform_content_id: str
    canonical_url: str | None
    content_type: ContentType
    title_or_summary: str | None
    cover_url: str | None
    author_platform_id: str | None
    author_name: str | None
    visible_like_count: int | None
    source_surface: SourceSurface
    feed_type: FeedType
    feed_position: int | None
    discovered_at: datetime
    raw_payload: dict
```

---

## 12.2 Detail Connector 输出

```python
@dataclass
class DetailSnapshotInput:
    title: str | None
    body_text: str | None
    author_platform_id: str | None
    author_name: str | None
    cover_url: str | None
    image_urls: list[str]
    video_url: str | None
    like_count: int | None
    comment_count: int | None
    collect_count: int | None
    share_count: int | None
    publish_time: datetime | None
    raw_payload: dict
```

---

## 12.3 Comment Connector 输出

```python
@dataclass
class CommentSnapshotInput:
    platform_comment_id: str
    parent_platform_comment_id: str | None
    author_platform_id: str | None
    author_name: str | None
    body_text: str
    like_count: int | None
    created_time: datetime | None
    raw_payload: dict
```

---

# 13. Repository Contract

## 13.1 ContentRepository

必须提供：

```python
class ContentRepository(Protocol):
    async def get_by_platform_identity(
        self,
        platform: Platform,
        platform_content_id: str,
    ) -> ContentIdentity | None:
        ...

    async def upsert_identity_from_candidate(
        self,
        candidate: FeedCandidate,
    ) -> ContentIdentityUpsertResult:
        ...

    async def insert_discovery_event(
        self,
        ...
    ) -> DiscoveryEvent:
        ...

    async def create_snapshot(
        self,
        ...
    ) -> ContentSnapshot:
        ...

    async def update_latest_snapshot(
        self,
        content_id: UUID,
        snapshot_id: UUID,
    ) -> None:
        ...
```

---

## 13.2 JobRepository

必须提供：

```python
class JobRepository(Protocol):
    async def create_job(...) -> Job: ...
    async def claim_jobs_for_agent(...) -> list[Job]: ...
    async def mark_started(...) -> None: ...
    async def update_checkpoint(...) -> None: ...
    async def mark_success(...) -> None: ...
    async def mark_partial_success(...) -> None: ...
    async def mark_failed(...) -> None: ...
    async def requeue_expired_claims(...) -> int: ...
```

---

## 13.3 LeaseRepository

必须提供：

```python
class LeaseRepository(Protocol):
    async def try_acquire(...) -> LeaseAcquireResult: ...
    async def release(...) -> None: ...
    async def expire_stale_leases(...) -> int: ...
```

---

# 14. 事务边界

## 14.1 Feed Candidate 入库事务
每个 candidate 的入库流程应单独事务化：

```text
BEGIN
- upsert content_identity
- insert discovery_event
- optionally create detail_fetch job
COMMIT
```

单条 candidate 失败，不影响其他 candidate。

---

## 14.2 Detail Result 入库事务
```text
BEGIN
- insert content_snapshot
- update content_identity.latest_snapshot_id
- insert/update candidate decision task or direct evaluate
- optionally create comment_fetch job
COMMIT
```

---

## 14.3 Lease 获取事务
lease 获取必须原子化，避免并发重复补采。

---

# 15. 任务优先级建议

| JobType | 默认 priority |
|---|---:|
| DETAIL_FETCH | 80 |
| COMMENT_FETCH | 90 |
| FEED_COLLECT | 100 |
| CREATOR_MONITOR | 110 |
| SEARCH_COLLECT | 120 |
| MEDIA_DOWNLOAD | 200 |

数值越小，优先级越高。

理由：
- Feed 发现后，详情补采应尽快；
- 评论补采稍后；
- 对标监控与 Feed 并行；
- 下载最低优先级。

---

# 16. 第一阶段默认策略

## 16.1 Feed
```text
target_count = 50
refresh_rounds = 2
```

## 16.2 Detail
```text
request-first
browser-fallback if available
```

## 16.3 Comments
```text
max_comments = 20
include_sub_comments = false
```

## 16.4 Snapshot 刷新策略
第一阶段可简化：

| 资源 | Freshness TTL |
|---|---:|
| 内容详情正文 | 24 小时 |
| 互动数快照 | 6 小时 |
| 评论预览 | 12 小时 |

---

# 17. 测试要求

## 17.1 单元测试
必须覆盖：
- 枚举；
- 状态机；
- Job claim/requeue；
- FetchLease；
- Content dedup；
- Candidate filter；
- Repository 基础行为。

## 17.2 集成测试
必须覆盖：
- 建任务 → claim → start → progress → complete；
- Feed candidate ingestion；
- 重复 candidate 去重；
- detail result ingestion；
- comment result ingestion；
- creator monitor event 写入。

## 17.3 Connector 测试
第一阶段允许用 fixture JSON 做 parser tests：
- XHS feed raw sample → FeedCandidate
- DY video feed raw sample → FeedCandidate
- DY image feed raw sample → FeedCandidate
- Detail raw → SnapshotInput
- Comment raw → CommentInput

注意：
**不要把外部平台实时访问测试作为 CI 强依赖。**

---

# 18. Codex 第一轮开工任务拆解

## Task 1：项目初始化
- FastAPI 项目骨架；
- SQLAlchemy / Alembic；
- 配置系统；
- 基础日志；
- health check。

## Task 2：领域模型与枚举
- 所有 Enum；
- Pydantic DTO；
- Domain dataclass / ORM model 基线。

## Task 3：数据库迁移
- 16 张表；
- 索引；
- 唯一约束；
- 基础 migration。

## Task 4：Repository 层
- JobRepository；
- ContentRepository；
- LeaseRepository；
- AccountRepository；
- CreatorMonitorRepository。

## Task 5：Job API 与状态机
- create job；
- claim；
- start；
- progress；
- complete；
- fail；
- pause；
- resume。

## Task 6：Feed Candidate Ingestion
- 去重；
- discovery event；
- detail job 自动生成。

## Task 7：Detail / Comment Ingestion
- snapshot；
- comment snapshot；
- candidate decision；
- comment fetch job 生成。

## Task 8：Agent API
- register；
- heartbeat；
- claim job。

## Task 9：Creator Monitor API
- create；
- list；
- run monitor job；
- event 查询。

---

# 19. 第一轮不要让 Codex 做的事

1. 不要一开始就实现真实 Playwright 采集；
2. 不要先碰 XHS/DY 实时请求；
3. 不要先做前端；
4. 不要先做 AI；
5. 不要先做图片/视频下载；
6. 不要先做完整权限；
7. 不要先做复杂分布式队列；
8. 不要再去复制 MediaCrawler 代码。

### 第一轮目标应是：
**先把“引擎骨架 + 数据层 + 任务协议 + API Contract”建稳。**

之后再在这个骨架上接真实 Connector。

---

# 20. 第二轮 Codex 执行顺序建议

当第一轮基础完成后，再做：

1. Local Agent Skeleton；
2. Browser SessionProvider；
3. XHS HomeFeed Connector；
4. XHS Detail / Comment；
5. DY Video Feed；
6. DY Image Feed；
7. DY Detail / Comment；
8. Creator Monitor Connector。

---

# 21. 与前四份文档如何配合使用

## 给 Codex 的推荐输入顺序
1. `intel-center-engine-plan-v1.md`
2. `mc-capability-benchmark.md`
3. `mc-source-audit.md`
4. `intel-engine-architecture-v0.1.md`
5. `intel-engine-schema-and-api-contract-v0.1.md`

## 建议提示词
可直接对 Codex 下指令：

> 严格依据这五份文档，先完成 Intelligence Engine 第一轮基础工程：  
> 1）FastAPI + SQLAlchemy + Alembic 项目骨架；  
> 2）文档定义的 Enum / ORM / DTO；  
> 3）完整数据库迁移；  
> 4）Job / Agent / Account / CreatorMonitor / Ingestion API；  
> 5）Job claim、resume、lease、dedup 逻辑；  
> 6）先用 fixture 和假的 Connector 完成端到端测试；  
> 不要提前实现真实平台采集，不要自由改架构，不要复制 MediaCrawler 的全局配置模式。  
> 完成后给出：目录树、关键代码、迁移文件、测试报告、尚未完成清单。

---

# 22. 最终验收

当 Codex 第一轮完成后，应该能做到：

1. 创建账号；
2. 注册 Agent；
3. 创建 Feed Job；
4. Agent claim Job；
5. Agent 上报假 Feed Candidate；
6. Server 去重并建内容主记录；
7. 自动创建 Detail Job；
8. Detail Result 入库并生成 Snapshot；
9. Comment Result 入库；
10. Candidate Decision 产出；
11. 对标账号 Monitor 可创建并生成 Job；
12. 任务全链路状态可查询；
13. 测试通过。

这一步完成，就代表：

# Intelligence Engine 的“系统骨架”已经真正建立，可以进入真实采集 Connector 开发。
