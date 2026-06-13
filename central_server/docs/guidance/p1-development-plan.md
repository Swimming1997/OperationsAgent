# P1 开发落地计划

> 定稿日期：2026-06-13  
> 依据：P0 设计与验收结果、当前 central_server / local_agent / shared_contracts 实现。  
> 目标：把系统从“能采集、能筛选、能入库”推进到“可持续运营、可追踪复盘、可进入创作准备”。

---

## 1. P1 总目标

P1 聚焦运营闭环，不重做 P0 地基，也不提前进入高风险动作能力。

核心交付：

- 任务调度与运行闭环稳定可用。
- XHS 账号资产读取进入正式 Job 链路。
- 对标作品可沉淀为创作素材准备记录。
- 运营规则可解释、可复盘、可配置。
- 用真实 Local Agent 运行数据补齐 XHS SLO 验收。

---

## 2. 非目标

以下能力不纳入 P1：

- 销售写跟进、Lead CRM、客户意向流转。
- 自动发布、点赞、收藏、关注、评论、私信。
- Douyin 等多平台深度采集扩展。
- 大模型自动仿写、自动仿画、自动成稿。
- 绕过 Central / Local Agent / shared_contracts 既有边界的快捷实现。

---

## 3. 主线 A：任务调度与运行闭环

### 范围

- 完善任务模板、定时计划、任务运行、Job 领取与回传的端到端体验。
- 强化任务失败定位、重试、暂停、取消、运行详情。
- 让运营使用 `/tasks` 和 `/my-runs`，主管/管理员使用 `/operations` 完成日常排障。

### 主要落点

- 后端：`TaskTemplate`、`TaskSchedule`、`TaskRun`、`Job`、`JobEvent`。
- 服务：`task_materialization`、`jobs/maintenance`、`job_operations_service`。
- 前端：`TasksPage`、`MyRunsPage`、`OperationsPage`、`RunDetailPanel`。
- Local Agent：继续只通过 HTTP JSON claim / progress / complete，不访问中央数据库。

### 验收

- 运营可创建并立即运行采集任务。
- 运营可配置定时任务，并看到下一次运行时间。
- 主管可查看失败原因、错误码、关联账号、关联 Agent。
- 失败任务支持按规则重试或人工重新触发。
- stale running job 可被维护任务处理，并在运行中心可见。

---

## 4. 主线 B：XHS 账号资产读取

### 范围

优先只读能力，纳入中央 Job 与 Local Agent 正式协议。

建议优先级：

1. `xhs.account.posted_notes`：当前账号已发布笔记。
2. `xhs.creator_platform.published_list`：创作者平台已发布作品列表。
3. `xhs.search.users`：用户搜索，用于补齐对标账号与监控对象。

暂缓：

- 点赞、收藏、关注、评论、私信、发布作品。
- 未经审计的 MediaCrawler 运行依赖接入。

### 主要落点

- `shared_contracts/enums.py`：补充正式 JobType 或 capability 标识。
- `local_agent_runtime/connectors/xhs/`：新增只读 probe / normalizer。
- `local_agent_runtime/runtime.py`：接入 Job 执行分发。
- 中央 ingestion API：复用内容、快照、发现事件、Job result summary。
- 前端：账号详情或运行详情中展示读取结果与失败原因。

### 验收

- 每个能力至少有 fixture 单测、normalizer 单测、Local Agent smoke。
- Job result summary 包含读取数量、跳过数量、错误码与采集 surface。
- 读取结果不上传 Cookie、token、原始登录敏感信息。
- 中央侧不 import `local_agent_runtime`。

---

## 5. 主线 C：对标作品到创作素材准备

### 范围

基于 P0 对标作品库，增加轻量“素材准备”能力。P1 不直接做自动仿写，只沉淀人工可用的结构化参考。

建议信息：

- 标题、正文、封面、图片、视频 URL。
- 互动指标、发布时间、作者信息。
- 评论亮点、用户痛点、卖点标签。
- 适用业务类型、运营备注、人工标签。
- 拆解结论：可借鉴点、不可借鉴点、风险提示。

### 主要落点

- 优先扩展 `ReferenceLibraryItem.metadata_json` 或新增窄表，视字段查询需求决定。
- 服务层放在 reference library 或 content service 内，避免新建过重域。
- 前端优先在 `BenchmarkLibraryPage` 详情面板扩展，不急于新开复杂页面。

### 验收

- 运营能从一条对标作品生成或维护素材准备记录。
- 素材记录能保留人工标签和备注。
- 主管可按业务类型、等级、标签筛选复用素材。
- 不改变 P0 对标库 active / archive / revoke 状态机。

---

## 6. 主线 D：运营规则实用化

### 范围

把已经落库的 `OperationRule` 从配置项变成运营可理解的判断依据。

### 主要能力

- 规则启停、适用业务类型、版本说明。
- 情报列表和详情展示规则命中解释。
- 对标入库理由能追溯到规则、关键词、阈值和触发来源。
- 规则重评结果有摘要和事件记录。

### 主要落点

- `OperationRule`、`RuleProfile`、`CandidateDecision`、`ReferenceLibraryEvent`。
- `RulesPage`、`IntelligenceDetailPanel`、`BenchmarkLibraryPage`。

### 验收

- 主管修改规则后，可对指定范围内容发起重评。
- 重评不会覆盖 manual lock 语义。
- 运营能看到“为什么推荐/为什么入库/为什么未命中”。
- sales 仍保持只读，不获得写规则或写对标库权限。

---

## 7. 主线 E：真实 SLO 与演示环境固化

### 范围

P0 已有夹具 SLO 验收；P1 需要补真实 Local Agent 运行数据。

### 主要能力

- 24 小时真实 Job 窗口统计。
- 按 job_type 输出成功率、终态数、错误码分布。
- 登录态异常、人工验证、结构变化、限流等问题可见。
- reset 后从零演示流程保持可复现。

### 验收

- XHS 推荐流、搜索、详情、评论四类 Job 真实运行成功率达到约定 SLO。
- `scripts/xhs_slo_report.py` 可直接复用真实数据输出报告。
- 运行中心能定位 SLO 失败样本。
- 演示环境 reset 后，管理员、主管、运营、销售四类角色流程可跑通。

---

## 8. 建议排期

| 周期 | 目标 | 输出 |
|---|---|---|
| 第 1 周 | P1 合同定稿 | 本文档、API 草案、验收清单、风险清单 |
| 第 2-3 周 | 任务调度与运行闭环 | 定时任务、运行详情、失败处理、回归测试 |
| 第 4-5 周 | XHS 账号资产读取 | 新 Job 能力、Local Agent smoke、中央入库/展示 |
| 第 6 周 | 对标素材准备 | 对标详情扩展、素材记录、筛选复用 |
| 第 7 周 | 规则解释与重评 | 命中解释、规则版本、事件追溯 |
| 第 8 周 | 真实 SLO 与验收 | 24h 实跑报告、演示脚本、全量回归 |

---

## 9. 工程约束

- 中央服务不得 import `local_agent_runtime` 或真实采集 runtime。
- Local Agent 不直接访问中央数据库、storage、service。
- 跨端协议优先放在 `shared_contracts/` 或双方已有 HTTP schema。
- 新能力必须配套后端单测、前端关键路径测试、Local Agent connector 测试。
- 涉及页面变更时，需保证 admin / supervisor / operator / sales 权限表现一致。
- 高风险动作能力必须另立阶段，不夹带进 P1。

---

## 10. P1 总验收清单

- [x] 任务模板可立即运行和定时运行。
- [x] 运行中心能查看失败原因、错误码、账号、Agent、重试状态。
- [x] XHS 账号资产至少一个只读能力完成正式 Job 闭环。
- [x] 对标作品可生成或维护素材准备记录。
- [x] 规则命中解释在情报详情或对标详情中可见。
- [x] sales 仍只读，运营/主管/管理员权限矩阵不回退。
- [x] Central / Local Agent 边界扫描通过。
- [x] 后端 pytest、前端 test/build、Local Agent smoke 通过。
- [x] 使用真实 Local Agent 数据输出 24h XHS SLO 报告。
