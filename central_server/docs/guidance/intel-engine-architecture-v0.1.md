# Intelligence Engine 架构设计 v0.1
**文件名：** `intel-engine-architecture-v0.1.md`  
**版本：** v0.1  
**用途：** 作为运营情报中心第一阶段采集引擎的正式架构基线，供 Codex 建立项目与后续编码。  
**前置文档：**
1. `intel-center-engine-plan-v1.md`
2. `mc-capability-benchmark.md`
3. `mc-source-audit.md`

---

# 0. 架构决议

## 0.1 项目不再以“爬虫脚本”方式推进
第一阶段直接建设一个独立的：

# Intelligence Engine

它是运营情报中心的数据引擎，而不是一次性数据抓取脚本。

---

## 0.2 第一阶段目标
引擎第一阶段必须支持：

### 数据发现
- 小红书推荐流 HomeFeed；
- 抖音视频推荐流 HomeFeed；
- 抖音图文推荐流 HomeFeed；
- 关键词搜索 Search；
- 对标账号最新内容 Creator Monitor。

### 数据补采
- 作品详情 Detail；
- 评论预览 Comment；
- 后续媒体下载接口预留。

### 系统能力
- 多账号；
- 多任务；
- 断点续跑；
- 共享去重；
- 补采租约；
- Session 生命周期；
- 可观测错误与任务状态；
- 服务化 API。

---

# 1. 系统上下文

## 1.1 业务系统中的位置

```text
┌─────────────────────────────────────────────┐
│             运营情报中心前端 / 业务后台      │
│ 情报列表 / 对标更新库 / 素材库入口 / 任务页   │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│            Intelligence Engine Server         │
│ Job API / Query API / Dedup / Storage / Rules │
└──────────────────────┬──────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
┌───────▼────────┐             ┌──────▼─────────┐
│ Local Agent A   │             │ Local Agent B   │
│ 员工电脑A        │             │ 员工电脑B         │
│ 托管多个账号会话 │             │ 托管多个账号会话   │
└───────┬────────┘             └──────┬─────────┘
        │                             │
┌───────▼─────────────────────────────▼───────┐
│ 浏览器 / 会话 / 请求补采 / 平台 Connector      │
└──────────────────────────────────────────────┘
```

---

## 1.2 为什么需要本地 Agent
因为系统需要使用员工自己登录、自己养好的平台账号，并让这些账号：

- 维持长期会话；
- 运行首页推荐流采集；
- 做必要的页面态取数；
- 在出现登录失效、人工验证时由员工接管。

所以推荐结构不是：
```text
中心服务器直接抓一切
```

而是：
```text
中心服务器调度
→ 本地 Agent 在对应员工电脑上执行
→ 结果回传共享池
```

---

# 2. 核心设计原则

## 2.1 浏览器负责发现，请求层负责补采
推荐流链路遵循：

```text
Feed Browser Discovery
→ Candidate Normalization
→ Global Dedup
→ Detail Fetch
→ Comment Fetch
→ Filter & Intelligence Pool
```

## 2.2 内容主记录全局共享
多个员工、多个账号刷到同一内容时：
- 只新建一条 `ContentIdentity`；
- 每次发现写一条 `DiscoveryEvent`；
- 详情补采有缓存；
- 评论补采按策略决定是否刷新。

## 2.3 所有任务必须可恢复
每个任务都必须具备：
- `job_id`
- `checkpoint`
- `attempt`
- `status`
- `resume_token`
- `last_error`

## 2.4 Signer 与 Session 解耦
签名逻辑会变化，会有不同实现。  
因此必须从架构上定义：

```python
SignerProvider
SessionProvider
```

让 Connector 只关心“发起平台请求”，不关心具体签名实现细节。

---

# 3. 总体模块架构

```text
intelligence_engine/
├── api/
│   ├── jobs_api.py
│   ├── contents_api.py
│   ├── accounts_api.py
│   └── creators_api.py
│
├── application/
│   ├── job_service.py
│   ├── content_service.py
│   ├── creator_monitor_service.py
│   ├── filter_service.py
│   └── dedup_service.py
│
├── domain/
│   ├── accounts/
│   │   ├── entities.py
│   │   ├── session_models.py
│   │   └── health_models.py
│   ├── content/
│   │   ├── entities.py
│   │   ├── snapshots.py
│   │   └── discovery.py
│   ├── jobs/
│   │   ├── entities.py
│   │   ├── state_machine.py
│   │   └── checkpoints.py
│   └── creators/
│       └── entities.py
│
├── connectors/
│   ├── base/
│   │   ├── feed_connector.py
│   │   ├── detail_connector.py
│   │   ├── comment_connector.py
│   │   ├── creator_connector.py
│   │   ├── search_connector.py
│   │   └── models.py
│   ├── xhs/
│   │   ├── feed_connector.py
│   │   ├── detail_connector.py
│   │   ├── comment_connector.py
│   │   ├── creator_connector.py
│   │   ├── search_connector.py
│   │   ├── normalizer.py
│   │   └── parsers.py
│   └── douyin/
│       ├── video_feed_connector.py
│       ├── image_feed_connector.py
│       ├── detail_connector.py
│       ├── comment_connector.py
│       ├── creator_connector.py
│       ├── search_connector.py
│       ├── normalizer.py
│       └── parsers.py
│
├── sessions/
│   ├── session_manager.py
│   ├── browser_session_provider.py
│   ├── request_session_provider.py
│   ├── session_bridge.py
│   ├── account_health.py
│   └── models.py
│
├── signer/
│   ├── signer_provider.py
│   ├── xhs_signer.py
│   ├── douyin_signer.py
│   └── sign_models.py
│
├── jobs/
│   ├── runner.py
│   ├── executors/
│   │   ├── feed_collect_executor.py
│   │   ├── detail_fetch_executor.py
│   │   ├── comment_fetch_executor.py
│   │   ├── creator_monitor_executor.py
│   │   └── search_executor.py
│   ├── retry_policy.py
│   ├── lease.py
│   └── checkpoint_store.py
│
├── storage/
│   ├── repositories/
│   │   ├── account_repository.py
│   │   ├── content_repository.py
│   │   ├── creator_repository.py
│   │   ├── job_repository.py
│   │   └── snapshot_repository.py
│   ├── models/
│   └── migrations/
│
├── filtering/
│   ├── keyword_rules.py
│   ├── lead_intent_rules.py
│   ├── thresholds.py
│   └── candidate_classifier.py
│
├── observability/
│   ├── logging.py
│   ├── metrics.py
│   ├── tracing.py
│   └── error_codes.py
│
└── local_agent/
    ├── agent_server.py
    ├── task_dispatcher.py
    ├── browser_runtime.py
    ├── profile_registry.py
    └── health_reporter.py
```

---

# 4. 核心领域模型

## 4.1 账号 Account

```python
Account(
    id: str,
    platform: Literal["xhs", "douyin"],
    owner_employee_id: str,
    business_role: Optional[str],
    display_name: str,
    status: AccountStatus,
    default_session_id: Optional[str],
)
```

### AccountStatus
```text
ACTIVE
NEED_LOGIN
NEED_MANUAL_VERIFY
DEGRADED
PAUSED
DISABLED
```

---

## 4.2 Session

```python
Session(
    id: str,
    account_id: str,
    platform: str,
    local_agent_id: str,
    session_type: Literal["browser", "request"],
    profile_ref: Optional[str],
    cookie_ref: Optional[str],
    status: SessionStatus,
    last_validated_at: datetime,
)
```

### SessionStatus
```text
READY
EXPIRED
MANUAL_VERIFY_REQUIRED
UNAVAILABLE
```

---

## 4.3 ContentIdentity

```python
ContentIdentity(
    id: str,
    platform: str,
    platform_content_id: str,
    canonical_url: str,
    content_type: str,
    first_seen_at: datetime,
    last_seen_at: datetime,
)
```

唯一键：
```text
(platform, platform_content_id)
```

---

## 4.4 DiscoveryEvent

```python
DiscoveryEvent(
    id: str,
    content_id: str,
    job_id: str,
    account_id: str,
    platform: str,
    source_surface: str,
    feed_type: Optional[str],
    feed_position: Optional[int],
    discovered_at: datetime,
)
```

### source_surface 建议枚举
```text
XHS_HOME_FEED
DOUYIN_VIDEO_HOME_FEED
DOUYIN_IMAGE_HOME_FEED
SEARCH
CREATOR_MONITOR
MANUAL_IMPORT
```

---

## 4.5 ContentSnapshot

```python
ContentSnapshot(
    id: str,
    content_id: str,
    title: Optional[str],
    text: Optional[str],
    author_id: Optional[str],
    author_name: Optional[str],
    cover_url: Optional[str],
    image_urls: list[str],
    video_url: Optional[str],
    like_count: Optional[int],
    comment_count: Optional[int],
    collect_count: Optional[int],
    share_count: Optional[int],
    publish_time: Optional[datetime],
    fetched_at: datetime,
    fetch_source_account_id: Optional[str],
)
```

---

## 4.6 CommentSnapshot

```python
CommentSnapshot(
    id: str,
    content_id: str,
    comment_id: str,
    parent_comment_id: Optional[str],
    author_id: Optional[str],
    author_name: Optional[str],
    text: str,
    like_count: Optional[int],
    created_at: Optional[datetime],
    fetched_at: datetime,
)
```

---

## 4.7 CreatorMonitor

```python
CreatorMonitor(
    id: str,
    platform: str,
    creator_platform_id: str,
    creator_name: Optional[str],
    group_id: Optional[str],
    enabled: bool,
    last_checked_at: Optional[datetime],
    last_known_content_cursor: Optional[str],
)
```

---

## 4.8 Job

```python
Job(
    id: str,
    job_type: JobType,
    account_id: Optional[str],
    creator_monitor_id: Optional[str],
    payload: dict,
    status: JobStatus,
    checkpoint: dict,
    retry_count: int,
    created_at: datetime,
    updated_at: datetime,
)
```

### JobType
```text
FEED_COLLECT
DETAIL_FETCH
COMMENT_FETCH
CREATOR_MONITOR
SEARCH_COLLECT
MEDIA_DOWNLOAD
```

### JobStatus
```text
PENDING
RUNNING
PARTIAL_SUCCESS
SUCCESS
FAILED
PAUSED
CANCELLED
```

---

# 5. Connector 设计

## 5.1 FeedConnector

```python
class FeedConnector(Protocol):
    async def collect(
        self,
        *,
        account: Account,
        session: SessionContext,
        job: JobContext,
        plan: FeedCollectPlan,
    ) -> FeedCollectResult:
        ...
```

### FeedCollectPlan
```python
FeedCollectPlan(
    target_count: int = 50,
    refresh_rounds: int = 1,
    per_round_scroll_limit: int = 50,
    feed_type: str,
)
```

### FeedCollectResult
```python
FeedCollectResult(
    items: list[DiscoveredContentCandidate],
    checkpoint: dict,
    diagnostics: dict,
)
```

---

## 5.2 DetailConnector

```python
class DetailConnector(Protocol):
    async def fetch_detail(
        self,
        *,
        content: ContentIdentity,
        session: SessionContext,
        job: JobContext,
    ) -> ContentSnapshot:
        ...
```

---

## 5.3 CommentConnector

```python
class CommentConnector(Protocol):
    async def fetch_comments(
        self,
        *,
        content: ContentIdentity,
        session: SessionContext,
        job: JobContext,
        limit: int,
        include_sub_comments: bool = False,
    ) -> CommentFetchResult:
        ...
```

---

## 5.4 CreatorConnector

```python
class CreatorConnector(Protocol):
    async def fetch_latest_contents(
        self,
        *,
        monitor: CreatorMonitor,
        session: SessionContext,
        job: JobContext,
    ) -> CreatorLatestContentsResult:
        ...
```

---

## 5.5 SearchConnector
第一阶段保留能力，但优先级低于 HomeFeed。

```python
class SearchConnector(Protocol):
    async def search(
        self,
        *,
        keyword: str,
        account: Account,
        session: SessionContext,
        job: JobContext,
    ) -> SearchResult:
        ...
```

---

# 6. Session 与 Signer 设计

## 6.1 SessionProvider

```python
class SessionProvider(Protocol):
    async def acquire(self, account_id: str, purpose: str) -> SessionContext:
        ...

    async def validate(self, session: SessionContext) -> SessionValidationResult:
        ...

    async def mark_invalid(self, session: SessionContext, reason: str) -> None:
        ...

    async def release(self, session: SessionContext) -> None:
        ...
```

---

## 6.2 SessionBridge
### 目标
用于同步：
- Browser session；
- Request session；
- Cookies；
- 本地 Agent 与中心服务中的 session metadata。

### 第一阶段建议
不要直接命名为 CookieBridge 复刻别人，而是实现更贴合我方的：

```text
SessionBridge
```

职责：
- 浏览器登录态读取；
- 请求客户端 cookie 更新；
- 账号失效反馈；
- 本地 Agent 侧 session 健康上报。

---

## 6.3 SignerProvider

```python
class SignerProvider(Protocol):
    async def sign(
        self,
        request: SignRequest,
        session: SessionContext,
    ) -> SignedRequest:
        ...
```

### 为什么必须这样设计
因为公开版 MediaCrawler 已经显示：
- XHS 签名实现有第三方算法依赖与 monkey patch；
- DY 签名逻辑也具有平台波动性；
- Pro 公开强调“新增签名服务，解耦签名逻辑”。

我方从第一天就应把签名当作可替换依赖。

---

# 7. HomeFeed 任务流程

## 7.1 业务流程

```text
创建 FEED_COLLECT 任务
→ 调度到指定本地 Agent
→ 获取 account session
→ 打开指定 feed 页面
→ 滚动发现内容
→ 累计到 target_count
→ 标准化 candidate
→ 上送 Server
→ Server 做内容去重
→ 写 DiscoveryEvent
→ 命中基础规则的内容进入 DETAIL_FETCH 队列
```

---

## 7.2 推荐页类型
必须明确拆开：

```text
XHS_HOME_FEED
DOUYIN_VIDEO_HOME_FEED
DOUYIN_IMAGE_HOME_FEED
```

不能把抖音视频与图文页混成一个 Connector。

---

## 7.3 Checkpoint 示例

```json
{
  "round_index": 1,
  "items_seen": 50,
  "unique_items_emitted": 47,
  "scroll_cursor": "opaque-browser-runtime-state",
  "last_discovered_content_ids": ["...", "..."]
}
```

---

# 8. 去重与补采租约

## 8.1 内容去重逻辑

```text
收到 candidate
→ 查 (platform, platform_content_id)
→ 不存在：
   建 ContentIdentity
   写 DiscoveryEvent
   评估是否入 DetailFetch
→ 已存在：
   更新 last_seen_at
   写 DiscoveryEvent
   检查 snapshot 是否过期
   仅在过期时重新补采
```

---

## 8.2 Fetch Lease
为避免多账号同时发现同一内容后重复补采，设计：

```python
FetchLease(
    resource_type: Literal["detail", "comments"],
    resource_id: str,
    owner_job_id: str,
    expires_at: datetime,
)
```

### 规则
- 同一内容详情补采同一时间只能有一个活跃 lease；
- lease 到期前其他任务直接跳过或等待；
- 若 job 失败，lease 可释放或超时回收。

---

# 9. 规则筛选设计

## 9.1 第一阶段只做规则筛选
AI 先预留接口，不作为引擎首要依赖。

### 规则维度
- 业务关键词；
- 获客意向词；
- 点赞阈值；
- 评论命中；
- 平台差异阈值。

---

## 9.2 Candidate Filter

```python
CandidateDecision(
    business_keyword_hits: list[str],
    lead_keyword_hits: list[str],
    like_threshold_hit: bool,
    preliminary_bucket: Literal[
        "lead_candidate",
        "content_candidate",
        "discard",
        "pending_enrichment"
    ],
)
```

---

# 10. 数据表设计建议

## 10.1 表清单
第一阶段建议至少有：

1. `accounts`
2. `account_sessions`
3. `local_agents`
4. `jobs`
5. `job_events`
6. `content_identity`
7. `content_discovery_events`
8. `content_snapshots`
9. `comment_snapshots`
10. `creator_monitors`
11. `creator_monitor_events`
12. `keyword_rules`
13. `candidate_decisions`
14. `fetch_leases`

---

## 10.2 为什么不用平台原始表直接当产品表
平台原始数据后续可以保留 `raw_payload_json`，但不能把：
- `xhs_note`
- `douyin_aweme`

直接作为业务主表。

否则：
- 多平台前端难统一；
- 去重逻辑难抽象；
- 作品库共享困难；
- 后续 AI/筛选跨平台难复用。

---

# 11. API 草案

## 11.1 Job API

### 创建 Feed 任务
`POST /api/jobs/feed-collect`

请求：
```json
{
  "account_id": "acc_xhs_001",
  "feed_type": "XHS_HOME_FEED",
  "target_count": 50,
  "refresh_rounds": 2
}
```

---

### 获取任务状态
`GET /api/jobs/{job_id}`

---

### 暂停任务
`POST /api/jobs/{job_id}/pause`

---

### 恢复任务
`POST /api/jobs/{job_id}/resume`

---

## 11.2 Content API
- `GET /api/contents`
- `GET /api/contents/{content_id}`
- `GET /api/contents/{content_id}/discoveries`
- `GET /api/contents/{content_id}/comments`

---

## 11.3 Creator Monitor API
- `POST /api/creator-monitors`
- `GET /api/creator-monitors`
- `POST /api/creator-monitors/{id}/run`

---

## 11.4 Account API
- `POST /api/accounts`
- `GET /api/accounts`
- `GET /api/accounts/{id}/health`
- `POST /api/accounts/{id}/mark-login-required`

---

# 12. 错误模型

## 12.1 标准错误码

```text
AUTH_REQUIRED
MANUAL_VERIFY_REQUIRED
SESSION_EXPIRED
SESSION_CONNECT_FAILED
SIGNATURE_INVALID
CONTENT_NOT_FOUND
REMOTE_BLOCKED
RATE_LIMITED
STRUCTURE_CHANGED
RETRYABLE_NETWORK_ERROR
NON_RETRYABLE_PLATFORM_ERROR
```

---

## 12.2 错误返回结构

```python
PlatformError(
    code: str,
    message: str,
    retryable: bool,
    account_id: Optional[str],
    platform: str,
    source_job_id: str,
    raw_context: Optional[dict],
)
```

---

# 13. 可观测性

## 13.1 任务指标
- feed items discovered
- unique contents inserted
- discovery duplicate ratio
- detail fetch success rate
- comment fetch success rate
- creator monitor new content count
- job duration
- retry count
- account failure count

## 13.2 账号指标
- last success time
- last validation time
- consecutive failures
- verification required count
- paused count

---

# 14. 第一阶段实现顺序

## Phase A：项目骨架
1. 初始化工程；
2. 定义 Domain Model；
3. 定义 Repository；
4. 定义 Job State Machine；
5. 定义 Error Model。

## Phase B：账号与会话
1. Account / Session 表；
2. Local Agent 注册；
3. SessionProvider；
4. SessionBridge；
5. Account Health。

## Phase C：HomeFeed
1. XHS Feed；
2. DY Video Feed；
3. DY Image Feed；
4. Dedup；
5. DiscoveryEvent。

## Phase D：Detail / Comment
1. XHS Detail / Comment；
2. DY Detail / Comment；
3. FetchLease；
4. Candidate Filter。

## Phase E：Creator Monitor
1. XHS Creator；
2. DY Creator；
3. New Content Event；
4. Alert Event 预留。

## Phase F：Search 与最小前台
1. SearchConnector；
2. 情报列表页；
3. 对标更新页；
4. 手动入素材库动作。

---

# 15. 与 MediaCrawler / Pro 的映射

| 能力 | 开源版经验 | Pro 对标 | 我方方案 |
|---|---|---|---|
| Login / Cookies | 已有 | Pro重构 | SessionManager |
| CDP / 浏览器 | 已有 | Pro去主干依赖 | BrowserSessionProvider |
| 签名 | XHS/DY 各自实现 | Sign Service | SignerProvider |
| Search | 已有 | 有 | SearchConnector |
| Detail | 已有 | 有 | DetailConnector |
| Comments | 已有 | 有 | CommentConnector |
| Creator | 已有 | 有 | CreatorConnector |
| HomeFeed | 无正式主线 | 有 | FeedConnector 优先实现 |
| 多账号 | 不足 | 有 | Account + Session + Scheduler |
| Resume | 不足 | 有 | Job + Checkpoint |
| Downloader | 有一些媒体下载 | Pro独立 Downloader | Deferred MediaDownload Job |
| AI Agent | 无 | 有 | 后续业务层，不是第一阶段引擎核心 |

---

# 16. 给 Codex 的硬约束

## 必须遵守
1. 不使用全局 mutable config 作为任务真相源。
2. 不使用 `sys.exit()` 处理业务错误。
3. 不将 Feed / Detail / Comment / Creator 混成一个巨型 Crawler。
4. 不将 Session 生命周期散落在平台 Connector 内。
5. 不把平台原始表当业务主表。
6. 不在采集主链路同步下载大量媒体。
7. 不让单 item 失败打断整个 batch。
8. 不让一个账号默认绑定到“浏览器第一个 context”。
9. 不把 Signer 的实现写死进 Connector。
10. 不把抖音视频推荐页与图文推荐页混为同一采集器。

## 必须交付
1. 完整实体模型；
2. Job 状态机；
3. SessionManager；
4. Connector 协议；
5. Repository 接口；
6. 去重与 Lease；
7. XHS/DY 三路 HomeFeed；
8. Detail/Comment；
9. CreatorMonitor；
10. 最小 API。

---

# 17. 第一阶段验收标准

| 目标 | 验收 |
|---|---|
| XHS HomeFeed | 指定账号采到 50 条 |
| DY 视频 HomeFeed | 指定账号采到 50 条 |
| DY 图文 HomeFeed | 指定账号采到 50 条 |
| 刷新轮次 | 支持刷新并重复采样 |
| Detail | 候选内容可补齐正文与互动 |
| Comment | 前 N 条评论可补齐 |
| Lead Keyword | 可识别求推类关键词 |
| Creator Monitor | 新作品可入库 |
| Dedup | 多账号发现同内容不重复补采 |
| Resume | 任务中断后可恢复 |
| Session | 账号失效能明确报状态 |
| API | 能发起任务和查看任务结果 |

---

# 18. 本架构的核心价值

最终我们要建设的不是“多平台爬虫”，而是：

# 一个由多员工、多账号共同驱动的运营情报网络

它具备：
- 推荐流实时发现；
- 对标账号监控；
- 内容共享与去重；
- 规则筛选；
- 可持续补采；
- 后续 AI 分析与内容生产的数据底座。

---

# 19. 后续文档建议
本架构文档之后，建议继续补：

1. `intel-engine-schema-v0.1.md`
2. `intel-engine-api-contract-v0.1.md`
3. `intel-engine-job-state-machine-v0.1.md`
4. `intel-engine-session-protocol-v0.1.md`
5. `intel-engine-feed-extraction-plan-v0.1.md`

其中前两个可以在 Codex 开始建项目之前继续细化。
