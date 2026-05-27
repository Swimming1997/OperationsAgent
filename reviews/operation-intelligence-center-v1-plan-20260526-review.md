# Plan Review: 运营情报中心 V1 开发计划

**Plan File**: 待开发计划/运营情报中心V1开发计划_20260526.md
**Reviewer**: Codex

---

## Round 1 — 2026-05-26

### Overall Assessment
计划方向总体合理，尤其是继续沿用 Central Server 与 Local Agent 分边界、先做规则版 AI 占位、先沉淀运营资产这些判断。但作为可执行开发计划，目前对已有 `ReferenceLibraryItem`、`CandidateDecision`、前端页面和权限体系的承接不够具体，P0 范围也偏大，存在模型重复、规则冲突、迁移路径和验收口径不清的问题。
**Rating**: 6/10

### Issues
#### Issue 1 (Critical): 对标作品库模型存在重复建设风险
**Location**: 4.1 可复用现有模型第 127 行；4.2 `BenchmarkItem` 第 131-151 行；阶段 0 任务第 479 行；阶段 1 第 494-518 行
计划一方面说 `ReferenceLibraryItem` 可评估复用或迁移，另一方面马上新增 `BenchmarkItem`、`BenchmarkItemEvent` 并进入 P0 落库。现有代码已经有 `ReferenceLibraryItem` 和 `ReferenceLibraryEvent`，且 API、前端、测试都围绕它工作；直接新增一套对标条目会造成双库并存、入库去重和历史数据迁移不清。
**Suggestion**: 在阶段 0 输出强制决策表：复用、扩展或迁移三选一。若复用，明确把 `selection_source`、`lead/non_lead/uncategorized`、`matched_keywords_json` 等字段如何加入 `reference_library_items`；若迁移，补充 backfill migration、旧 API 兼容策略、前端切换步骤和回滚方案。

#### Issue 2 (Critical): 手动选中与 AI 选中的幂等和优先级规则不足
**Location**: 4.2 `BenchmarkItem.selection_source` 第 140 行；阶段 4 验收第 642 行；阶段 5 任务第 653-657 行
计划要求“手动选中优先级高于 AI 判断”，又要求新内容自动进入 AI 选中，但没有定义同一 content 在 manual 和 ai、获客和非获客、不同评级之间的唯一性和覆盖规则。现有 `reference_library_items` 是按 `content_id + library_type + active` 去重，无法表达同一条内容的选中来源冲突和重评覆盖。
**Suggestion**: 增加明确的状态机和唯一约束，例如同一 `content_id` 只能有一个 active benchmark item，`selection_sources_json` 记录多来源，manual 字段不可被自动评估覆盖。补充 `manual -> ai`、`ai -> manual`、规则重评、移动分类、删除后重入库的行为表和单元测试。

#### Issue 3 (High): 默认评级规则与现有候选分类器冲突
**Location**: 阶段 2 默认规则第 536-548 行；阶段 5 验收第 661-666 行
计划定义了抖音和小红书分平台阈值，例如小红书获客库点赞 `>=10` 为中、`>=100` 为好，非获客库 `>=50`、`>=200`、`>=500`。但现有分类器是统一 `FILTER_V1_VISIBLE_LIKE_THRESHOLD = 50`，输出 `lead_candidate/content_candidate/pending_enrichment/discard`，且评论命中只是 supplemental signal。这会导致计划里的评级和现有 `CandidateDecision` 语义不一致。
**Suggestion**: 把阶段 2 改成“引入可配置 RuleProfile”，按平台、业务类型、库类型分别定义阈值和评级映射，并明确 `CandidateBucket` 到 benchmark `library_type/rating` 的转换。验收增加现有阈值迁移测试、规则配置读取测试和重评结果快照测试。

#### Issue 4 (High): P0 API 清单没有落到现有 FastAPI 路由和前端 client
**Location**: 阶段 0 任务第 481-483 行；阶段 3 第 565-596 行；阶段 4 第 621-636 行
计划只写“设计 P0 API 清单”和页面任务，没有列出具体 endpoint、request/response schema、权限、分页和错误码。现有前端使用 `frontend/src/api/intelligence.ts` 调 `/api/intelligence/contents/product`、`/api/reference-library/items`，现有 routes 中的业务操作仍分散在 product routes；缺少合同会让前后端并行开发困难。
**Suggestion**: 在计划中补一节“P0 API Contract”，至少列出筛选列表、详情、手动入库、批量入库、评级、移动分类、标签、备注、AI 重评、事件列表的 endpoint、方法、schema、角色权限、错误码和兼容现有接口的迁移顺序。

#### Issue 5 (High): 情报中心筛选方案缺少查询性能设计
**Location**: 阶段 3 筛选增强第 565-577 行；阶段 4 任务第 621-626 行；验收总口径第 974-977 行
计划新增平台、关键词、点赞、评论、发布时间、是否已入库、来源 surface、标签和多种排序，但没有说明索引、分页上限和 JSON 字段查询策略。现有 `WorkflowRepository.list_intelligence_contents` 已大量使用 JSON cast + contains，数据量上来后很容易变慢，尤其是批量运营和对标库筛选会叠加 join。
**Suggestion**: 增加数据库查询设计：常用过滤字段建立普通索引或派生列，关键词命中落到结构化表或 JSONB GIN 索引，列表默认分页上限和排序白名单写入 API 合同。验收增加 1 万或 10 万内容量级的查询耗时基准。

#### Issue 6 (High): 批量操作缺少事务、部分失败和审计定义
**Location**: 阶段 3 操作第 587-596 行；阶段 4 任务第 626-636 行；4.2 `BenchmarkItemEvent` 第 152-163 行
计划要求批量加入、批量标签、移动分类、评级和删除，但只说记录事件，没有定义批量操作是全成功回滚还是允许部分成功，也没有定义重复入库、内容缺失、权限不足时的响应结构。
**Suggestion**: 补充 Bulk API 行为规范：请求 idempotency key、最大批量数、逐条 result、错误码、是否 partial commit、事件 payload 格式和操作者字段。验收增加重复提交、部分失败、并发批量入库的测试。

#### Issue 7 (High): 权限和角色矩阵不足
**Location**: 1 当前判断第 13 行；阶段 3 第 587-596 行；阶段 4 第 626-636 行；阶段 11 第 831-872 行
计划提到 central server 负责权限，但没有定义管理员、主管、运营、销售分别能做哪些动作。现有代码已有 `admin/supervisor/operator/sales` 和 `require_any_role`，新增删除、移动分类、分发任务、客资跟进等动作如果没有矩阵，会出现普通运营误删资产、销售改规则、主管无法审计等边界问题。
**Suggestion**: 增加“权限矩阵与审计”章节，按功能列出 read/create/update/delete/export/bulk/assign/re-evaluate/archive 的允许角色，定义敏感操作必须写事件，并明确前端只隐藏按钮不是权限控制，后端必须强制校验。

#### Issue 8 (High): 客资线索范围与数据来源不清
**Location**: 4.2 `Lead` 第 258-275 行；5.1 `LeadDetectionService` 第 303-309 行；阶段 11 客资提醒第 851-872 行；暂不优先事项第 939-941 行
计划把评论、摘要、私信都作为识别来源，但暂不优先自动评论、回复、私信处理，当前 job types 也没有私信采集。若 V1 同时承诺 `source_comment_id` 和私信，会引入本地执行、隐私、合规和数据结构的不确定性。
**Suggestion**: 将 V1 明确限定为评论和已入库内容文本的规则识别，私信只保留枚举占位，不进入验收。补充 `Lead` 与 `CommentSnapshot` 的外键、去重规则、负责人分配、误报关闭和敏感信息处理要求。

#### Issue 9 (Medium): service 层计划没有结合现有 repository 和 route 结构
**Location**: 2.3 执行层服务先于路由堆逻辑第 61-73 行；5.1 Central Server 服务第 280-365 行；推荐工作顺序第 886-893 行
方向正确，但计划没有指定文件路径、依赖方向和迁移顺序。现有代码已经有 `storage/repositories/*`、`services/task_materialization.py`、`filtering/candidate_classifier.py`，很多业务逻辑仍在 repository 和 route 中；如果只新增 service 名称，旧逻辑可能继续分散。
**Suggestion**: 增加 service 分层落地方案：例如 `services/benchmark_selection.py` 调 repository，API route 只做 schema 和权限，classifier 只做纯规则判断。每个阶段列出要迁移的现有函数和新增测试位置，避免“新 service + 旧 route 逻辑”并存。

#### Issue 10 (Medium): 运营规则库与已有关键词规则体系边界不清
**Location**: 4.2 `OperationRule` 第 184-198 行；5.1 `OperationRuleService` 第 320-326 行；阶段 7 第 697-724 行
计划新增 `OperationRule`，但现有系统已有 `KeywordRuleSet`、`KeywordRule` 和业务类型绑定。新增规则库如果不定义与关键词规则的关系，会形成“运营规则”和“关键词规则”两套启停、适用平台和引用机制。
**Suggestion**: 将规则分为 machine_rule 和 human_guideline 两类，明确关键词匹配继续使用现有 `KeywordRuleSet/KeywordRule`，文案、封面、风险、人设规则才进入 `OperationRule`。规则需增加 version、effective_status、引用快照，确保仿写项目引用后不会被后续编辑悄悄改变历史结果。

#### Issue 11 (Medium): 底图库缺少存储、安全和生命周期设计
**Location**: 4.2 `BackgroundAsset` 第 165-182 行；5.1 `AssetExtractionService` 第 311-318 行；阶段 8 第 727-758 行
计划定义了 `asset_url`、`local_artifact_ref` 和敏感状态，但没有说明图片文件放在哪里、如何访问、是否下载原图、缩略图如何生成、敏感信息打码前是否可见、删除和保留策略是什么。现有 central server 只有 DB、data/logs 和 `MEDIA_DOWNLOAD` job type 枚举，没有完整资产存储服务。
**Suggestion**: 在 P1 前增加 Asset Storage 设计：本地文件或对象存储路径规范、DB artifact 表、访问鉴权、缩略图、敏感状态流转、删除策略和 `MEDIA_DOWNLOAD` job 对接方式。验收包含上传、引用、归档、敏感状态拦截展示。

#### Issue 12 (Medium): 分发任务和发布记录边界过宽
**Location**: 4.2 `DistributionTask` 第 237-256 行；5.1 `DistributionService` 第 358-365 行；阶段 11 第 825-878 行；暂不优先事项第 937 行
计划说不做自动发布，但 `DistributionTask` 又包含发布状态、链接、互动数据和线索数，阶段 11 还要求记录发布结果。没有定义这些数据是人工录入、导入、还是由采集任务回填，也没有说明与 operated account 的账号状态和权限如何绑定。
**Suggestion**: 将阶段 11 拆成手动分发和发布回填两个子阶段。V1 只做任务派发、负责人、截止时间、人工填链接和状态；互动指标和线索数回填另列 API 和采集来源。账号必须绑定 `PlatformAccount.account_role = operated_account` 或等价字段。

#### Issue 13 (Medium): Local Agent 执行层内容放在中央开发计划里，责任边界不够清晰
**Location**: 5.2 Local Agent 执行层抽象第 367-423 行；阶段 6 第 670-692 行；AGENTS 约束对应 central server 只做中央职责
计划中的 `ProfileManager`、`AccountLock`、`OperatorExecutor` 属于 local_agent 运行时职责，而本次要求验证 `central_server` 可行性。中央代码规则明确“不管理员工电脑 Chrome，不直接操作 Local Agent profile”。如果把这些作为 central_server 阶段任务，容易造成跨边界实现。
**Suggestion**: 把 5.2 改成“Local Agent 配套计划或接口依赖”，central_server 只定义 Job payload contract、agent heartbeat capability、错误码和运行中心展示。Profile/profile lock 的实现应移到 local_agent 计划，并以接口验收而不是 central_server 代码验收。

#### Issue 14 (Medium): MVP 和 V1 闭环范围不一致
**Location**: 3 目标产品闭环第 89-113 行；10 近期最小可交付版本第 953-968 行；11 验收总口径第 970-982 行
目标闭环包含底图、规则、仿写、分发、发布记录和客资提醒，但“近期最小可交付版本”只到对标作品库。验收总口径又把底图、规则、仿写、仿画入口纳入当前阶段，范围边界不清，容易让 P0 无法按期交付。
**Suggestion**: 明确命名为 MVP、V1、V1.1 或 P0/P1/P2，并为每个版本单独写非目标和验收。P0 只验收情报中心、手动入库、规则 AI 选中、对标库；底图、规则、仿写只允许数据模型占位，不要求前端入口，或另设 P1 验收。

#### Issue 15 (Low): 错误码和稳定性验收缺少量化指标
**Location**: 阶段 6 任务第 676-686 行；阶段 6 验收第 688-693 行；11 验收总口径第 980-982 行
计划要求 benchmark、stress test、标准化错误码和连续运行成功率统计，但没有定义成功率口径、样本量、运行时长、平台失败分类和可接受阈值。现有 `ErrorCode` 已有较完整枚举，计划应避免重复定义但补齐指标。
**Suggestion**: 增加稳定性 SLO：例如推荐流、搜索、详情、评论分别在 N 个账号、N 次任务、N 小时内的成功率、重试率、登录失效识别耗时和 stale job 清理时限。列出复用现有 `ErrorCode` 的映射和新增错误码流程。

#### Issue 16 (Suggestion): 前端 UX 任务缺少与现有页面的落地关系
**Location**: 阶段 3 右侧详情区和操作第 579-596 行；阶段 4 页面结构第 613-619 行；阶段 4 任务第 621-636 行
计划描述了列表、右侧详情和三层筛选，但没有说明是改造现有 `IntelligencePage` 的 tab，还是新增独立 `BenchmarkItemsPage`。现有前端的“对标素材库”tab 目前基本是只读列表，详情仍要求回到公共池查看，和计划里的对标作品库管理差距较大。
**Suggestion**: 增加页面结构草图和组件/API 分工：情报中心列表、详情抽屉、对标作品库独立页、批量操作栏、筛选状态持久化、空状态和权限禁用态。验收应包含前端测试和最小可用操作路径，而不只是字段列表。

### Positive Aspects
- 明确坚持 Central Server 与 Local Agent 分边界，符合现有 `central_server/AGENTS.md` 的职责约束。
- 先用规则实现 AI 选中、仿写和客资识别，降低了早期大模型集成风险。
- 领域模型先行、service 层承接业务判断的方向是正确的，也符合当前代码需要从 route/repository 中抽离业务逻辑的趋势。
- 对标作品库、事件记录、规则库、底图库、仿写和分发的产品链路完整，能覆盖运营资产沉淀的主要场景。
- 阶段 6 把 XHS 引擎稳定性单列出来是必要的，否则上层产品会缺少可靠数据来源。

### Summary
Top 3 key issues:
1. 先解决 `ReferenceLibraryItem` 与 `BenchmarkItem` 的复用、扩展或迁移决策，否则 P0 会重复建模。
2. 补齐规则选中、手动选中、评级、重评和批量操作的状态机、幂等和 API 合同。
3. 收窄 P0 范围并补充权限、性能索引和量化验收，保证计划能按现有 FastAPI/React/SQLAlchemy 栈落地。
**Consensus Status**: NEEDS_REVISION
---

## Round 2 — 2026-05-26

### Overall Assessment
修订版已经实质性吸收 Round 1 的核心意见：对标库明确复用 `ReferenceLibraryItem`，新增了状态机、RuleProfile、P0 API 草案、权限矩阵、批量规范、性能约束和版本边界。当前剩余问题主要集中在少数必须落成明确合同的点：生产鉴权、API 兼容路径、唯一约束迁移、RuleProfile 持久化，以及 P0 自动评估触发的幂等实现。
**Rating**: 8/10

### Previous Round Tracking
| Round 1 Issue | Severity | Status | Evidence in Revised Plan | Remaining Action |
|---|---|---|---|---|
| Issue 1: 对标作品库模型重复建设风险 | Critical | Resolved | 4.1、4.2.1、阶段 0、阶段 1 明确复用并扩展 `ReferenceLibraryItem`，禁止 `BenchmarkItem` 平行表。 | 无；实现时按迁移方案执行。 |
| Issue 2: 手动选中与 AI 选中幂等和优先级不足 | Critical | Mostly Resolved | 4.3 定义 manual 锁、AI 不覆盖、重评跳过、每 content 单 active 条目。 | 仍需在阶段 0 选定 DB 唯一约束还是服务层约束，不能长期二选一。 |
| Issue 3: 默认评级规则与现有分类器冲突 | High | Resolved | 阶段 2 引入 `RuleProfile`，区分情报池可见性阈值与对标库评级阈值。 | 实现时补配置读取和旧数据重评测试。 |
| Issue 4: P0 API 清单未落到现有路由 | High | Mostly Resolved | 7.5.1 增加 API 合同草案、路径、角色和错误码。 | 详情路由与现有 `/product-detail` 不一致，schema 仍需补齐。 |
| Issue 5: 查询性能设计不足 | High | Mostly Resolved | 7.5.5 增加分页、排序白名单、结构化字段、1 万条 P95 指标和索引方向。 | 需要指定目标数据库、数据生成方式和 EXPLAIN 验收。 |
| Issue 6: 批量操作事务和审计不足 | High | Resolved | 7.5.3 定义批量上限、Idempotency-Key、partial success、事件写入和并发幂等。 | 无；实现时补 atomic=true 测试。 |
| Issue 7: 权限和角色矩阵不足 | High | Mostly Resolved | 7.5.2 增加 admin/supervisor/operator/sales 矩阵和后端强制要求。 | 需要处理生产环境禁止 `X-Role` 注入的问题，并细化 P2 “部分”权限。 |
| Issue 8: 客资线索范围与数据来源不清 | High | Mostly Resolved | 4.2 Lead 限定评论和摘要，私信不进 P0/P1；说明去重和误报关闭。 | 5.1 `LeadDetectionService` 仍写“私信文本”，需同步修正。 |
| Issue 9: service 层未结合现有结构 | Medium | Resolved | 5.2 给出 service 路径、依赖和迁移现有逻辑清单。 | 无；实现时避免 route/repository 继续堆业务规则。 |
| Issue 10: OperationRule 与 KeywordRule 边界不清 | Medium | Resolved | 4.4 区分机器可执行规则与运营经验条文，并要求引用快照。 | 无。 |
| Issue 11: 底图库存储和安全设计不足 | Medium | Mostly Resolved | 7.5.6 定义 P1 前置设计、存储路径、鉴权 URL、缩略图、敏感状态。 | 阶段 8 开工前仍需单独产出完整资产设计。 |
| Issue 12: 分发任务和发布记录边界过宽 | Medium | Mostly Resolved | 5.1 和阶段 11 拆为 11a 手动分发、11b 指标回填。 | 阶段 11 任务和验收仍混写发布记录与线索提醒，应按子阶段拆验收。 |
| Issue 13: Local Agent 职责边界不清 | Medium | Mostly Resolved | 5.3 明确这些属于 local_agent 计划，central_server 只做 Job payload、错误码和展示。 | 可保留为接口依赖，但建议减少 central_server 计划中的本地实现细节。 |
| Issue 14: MVP 与 V1 闭环范围不一致 | Medium | Resolved | 第 10 节明确 MVP/P0、V1/P1、V1.1/P2，并声明验收以 10.1-10.3 为准。 | 无。 |
| Issue 15: 稳定性验收缺少量化指标 | Low | Resolved | 阶段 6 增加 24h/50 次、>=90%、登录失效 5 分钟、stale job 30 分钟等 SLO。 | 无；实现时明确统计脚本。 |
| Issue 16: 前端 UX 缺少落地关系 | Suggestion | Resolved | 7.5.4 明确 `IntelligencePage` 改造、独立 `BenchmarkLibraryPage`、详情和 Vitest 验收。 | 无。 |

### Issues
#### Issue 1 (High): 生产鉴权策略仍未纳入计划
**Location**: 7.5.2 权限矩阵第 927-940 行；验收总口径第 1076 行；现有栈 `central_server/intelligence_engine/security/auth.py` 支持 `X-Role` / `X-User-Roles` 注入
修订版要求“后端强制”权限，这是正确的，但没有说明生产环境如何禁用当前代码里的请求头角色注入。现有 `get_optional_principal` 会在没有 Bearer token 时接受 `X-Role` / `X-User-Roles`，如果生产部署不加开关，任何能发请求的人都可能伪造 admin/supervisor 权限。
**Suggestion**: 在 7.5.2 增加生产鉴权约束：`X-Role`/`X-User-Roles` 仅允许 dev/test 环境，生产必须 Bearer token；增加配置项如 `allow_header_auth=false`，并把权限矩阵验收扩展为“无 token + 伪造 X-Role 在生产配置下返回 401/403”的 API 测试。

#### Issue 2 (High): API 合同草案仍存在详情路由兼容风险
**Location**: 7.5.1 P0 API 合同第 914 行；阶段 0 任务第 503 行；现有前端 API 使用 `/api/intelligence/contents/{content_id}/product-detail`
7.5.1 把情报详情写成 `GET /api/intelligence/contents/{content_id}`，但当前前端和后端已经有 `/api/intelligence/contents/{content_id}/product-detail`。如果不说明是新增 alias、替换旧路由还是保留兼容期，会导致前端 client、测试和已有调用断裂。
**Suggestion**: 在 API 合同中明确“保留 `/product-detail`，新增短路径 alias”或“迁移到短路径并保留旧路径一版”。同时为详情、入库、批量、重评和事件列表补最小 request/response schema 字段，不只列 endpoint。

#### Issue 3 (Medium): 每 content 单 active 对标条目的约束方式还没有定稿
**Location**: 4.3 第 265 行；阶段 0 任务第 501 行；阶段 1 任务第 525 行
计划仍把“调整为每 content 单条 active”与“服务层保证库类型互斥”作为二选一留到阶段 0。这个选择会直接影响 Alembic migration、现有 `uq_reference_library_active_content_type` 约束、历史多 library_type 数据如何合并，以及并发批量入库的正确性。
**Suggestion**: 在计划中预先推荐 DB 级部分唯一约束为默认方案：`content_id WHERE status='active'` 唯一；阶段 0 只允许推翻并记录理由。补充历史冲突处理规则：多个 active 条目如何选择主条目、如何归档其余条目、事件如何补写。

#### Issue 4 (Medium): `RuleProfile` 的持久化和版本快照仍不够具体
**Location**: 4.3 第 275 行；4.4 第 279 行；阶段 2 默认规则第 553-568 行；7.5.2 第 936 行
计划引入 `RuleProfile`，但仍写成“新增配置表或 JSON 配置”，没有明确存储模型、版本字段、启停范围、谁能编辑、重评时如何选择历史版本。由于 AI 选中和评级都依赖它，RuleProfile 如果只是代码常量或松散 JSON，后续规则变更无法审计，也无法解释旧结果。
**Suggestion**: 增加 `RuleProfile` 最小模型：`id/name/platform/library_type/version/enabled/config_json/created_by/created_at`，评估结果必须写入 `rule_profile_id`、`rule_profile_version` 和 `input_snapshot_json`。7.5.1 同步增加 RuleProfile 列表、更新和启停 API，或明确 P0 只允许配置文件、不提供 UI。

#### Issue 5 (Medium): AI 自动选中触发点缺少幂等和事务边界
**Location**: 阶段 5 任务第 667-671 行；4.3 规则重评第 272 行；7.5.3 批量操作规范第 942-947 行
计划要求详情/评论入库后自动触发规则评估并写入对标库，但没有定义这是 ingestion 同事务内同步执行、提交后异步 job、还是后台扫描任务。评论多次入库、详情重复抓取、手动重评和自动评估并发时，如果没有触发幂等和锁策略，可能重复写事件或覆盖非预期字段。
**Suggestion**: 在阶段 5 增加自动评估执行模型：推荐在 ingestion commit 后投递内部评估任务或调用 service 的 idempotent 方法；以 `content_id + rule_profile_version + trigger_source` 做去重；所有写入通过 `BenchmarkSelectionService.ai_select_by_rules`，并复用 4.3 manual 锁检查和 DB 唯一约束。

#### Issue 6 (Medium): LeadDetectionService 描述与私信排除范围不一致
**Location**: 4.2 `Lead` 第 247-260 行；5.1 `LeadDetectionService` 第 309-314 行；9 暂不优先事项第 1024 行
4.2 已明确私信不进入 P0/P1 验收，但 5.1 仍写“从评论、摘要、私信文本中识别求推类关键词”。这会让实现者误以为要预留或接入私信文本处理，扩大数据来源和隐私边界。
**Suggestion**: 把 5.1 改为“从评论、标题、摘要文本中识别求推类关键词”；私信仅在 P2+ 的 `source_type` 枚举中预留，并标注 disabled / no ingestion。

#### Issue 7 (Medium): 性能验收缺少目标数据库和可复现数据集
**Location**: 7.5.5 第 956-960 行；README 默认 SQLite；docker-compose 提供 Postgres
7.5.5 给出 1 万条 P95 < 500ms，这是有价值的，但没有说明以 SQLite 还是 Postgres 为准，也没有定义数据分布、索引已应用状态、是否包含 comments/discovery/decisions/reference joins。不同数据库和数据分布下结果差异很大，验收可能不可复现。
**Suggestion**: 指定 P0 性能基准环境，例如 Postgres 16 为主、SQLite 只做开发烟测；提供 seed 脚本生成内容、快照、发现事件、候选决策、参考库条目和评论；验收保存 EXPLAIN 输出和 P95 统计脚本路径。

#### Issue 8 (Low): 7.5 工程约束章节位置影响可读性和执行顺序
**Location**: 7.5 P0 工程约束第 907 行，位于阶段 11 之后；阶段 0 多处引用 7.5
7.5 是 P0 的核心工程合同，却放在阶段 11 之后，阅读时会先经过 P1/P2 阶段再看到 P0 约束。虽然不影响技术可行性，但容易让执行者漏读 API、权限、批量和性能要求。
**Suggestion**: 将 7.5 移到阶段 0 之前，或作为 `## 7.0 P0 工程约束` 放在分阶段开发计划开头；后续阶段只引用它。

#### Issue 9 (Low): 阶段 11 子阶段拆分后，任务和验收仍混在一起
**Location**: 阶段 11 第 846-902 行；5.1 DistributionService 第 373 行；10.3 第 1058-1060 行
计划新增 11a/11b 拆分，但阶段 11 的任务和验收仍写“发布记录、点赞、评论、收藏、线索数、命中关键词后生成客资提醒”。这和“11a 先做手动分发、11b 后做指标回填”之间仍有范围混淆。
**Suggestion**: 把阶段 11 任务和验收拆成 11a、11b 两套：11a 只验任务派发、状态、人工链接；11b 再验发布记录指标、线索数和客资提醒。避免 P2 实施时再次把回填和提醒拉进首个分发版本。

### Positive Aspects
- Round 1 的核心架构风险基本被消除，尤其是对标库复用 `ReferenceLibraryItem` 的决策清晰了。
- P0 范围明显收敛，版本边界比上一版可执行得多。
- 批量操作、权限矩阵、性能目标和前端信息架构都从抽象愿望变成了可实施约束。
- Local Agent 边界已经改成接口依赖，符合 central_server 当前职责。

### Summary
Top 3 key issues:
1. 生产鉴权必须禁止请求头伪造角色，否则权限矩阵无法真正成立。
2. API 合同需要处理现有 `/product-detail` 兼容和最小 schema，避免前后端实现分叉。
3. 每 content 单 active 对标条目、RuleProfile 存储和自动评估触发必须在 P0 开发前定稿。
**Consensus Status**: MOSTLY_GOOD