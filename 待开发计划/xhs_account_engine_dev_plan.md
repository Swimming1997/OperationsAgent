# 小红书账号体系与底层引擎待开发计划任务书

> 建议保存路径：`D:\\AMiracle\\docs\\plans\\xhs-account-engine-dev-plan.md`  
> 当前优先级：先固化账号体系设计，再集中测试和整改小红书底层引擎，把稳定性和性能做到可用基线。

---

## 1. 项目背景

当前项目已经完成中央服务器与本地 Local Agent 的结构拆分：

- `central_server`：中央服务器，负责平台、API、数据库、任务队列、情报池、账号中心、权限、审计、前端。
- `local_agent`：员工电脑上的本地执行器，负责 Chrome Profile、本机浏览器、小红书页面操作、采集、评论/回复动作和 HTTP 上报。

后续平台需要同时支持两类核心业务：

1. **情报搜集**：用专门养好的采集号看推荐流、搜索、对标账号、爆文、评论区，把数据沉淀到中央情报池。
2. **员工运营**：员工在中央平台上管理自己负责的小红书账号，查看评论、回复评论、发布互动动作。

这两类账号必须从一开始就区分清楚，否则后续会在权限、风控、性能、调度、审计上混乱。

---

## 2. 总体原则

### 2.1 账号用途必须隔离

必须明确：

```text
采集账号池 ≠ 员工运营账号池 ≠ 员工本人账号
```

账号不能混用：

- 采集号只用于只读采集，不参与评论、回复、私信等对外互动。
- 员工运营号用于员工负责的账号维护，可以查看评论、回复评论、执行互动动作。
- 员工本人登录平台账号只代表平台权限身份，不等于小红书账号。

### 2.2 中央只管平台和任务，本地执行真实浏览器操作

中央服务器不能直接保存小红书 Cookie，也不能直接模拟账号浏览器操作。

正确边界：

```text
中央服务器：
  人员、账号、权限、任务、缓存、审核、审计、状态展示

Local Agent：
  本机 Chrome、Profile、登录态、页面采集、评论/回复、截图、结果上报
```

两者只能通过 HTTP JSON 协议通信。

### 2.3 性能体验不能依赖点击后临时采集

员工点击中央平台时，不能设计成：

```text
点击页面 -> 临时启动浏览器 -> 打开小红书 -> 抓取 -> 等待返回
```

这样体验一定慢。

正确方式：

```text
后台预采集 / 定时刷新 / 缓存优先展示
员工点击中央平台
先展示中央已有缓存
同时触发 Local Agent 刷新
刷新完成后页面增量更新
```

### 2.4 IP 池不是核心方案

不建议把“IP 池”作为核心设计。

对员工运营账号而言，更稳定的方式是：

- 固定员工电脑；
- 固定 Chrome Profile；
- 相对固定网络环境；
- 低并发；
- 有操作间隔；
- 有人工确认；
- 账号级熔断和健康监控。

频繁更换 IP、设备指纹、登录环境，可能反而提高账号异常风险。

---

## 3. 目标能力

### 3.1 情报采集账号池

用途：

- 推荐流采集；
- 搜索结果采集；
- 对标账号主页采集；
- 笔记详情采集；
- 评论区采集；
- 爆文发现；
- 素材发现；
- 客户线索发现。

特点：

- 只读为主；
- 不发评论；
- 不回复用户；
- 不代表公司对外互动；
- 可以绑定到专门采集机器或专门 Local Agent；
- 数据进入情报池、爆文池、对标账号池、素材池、评论洞察池。

### 3.2 员工运营账号池

用途：

- 员工管理自己负责的小红书账号；
- 查看账号内容；
- 查看评论；
- 回复评论；
- 发布评论；
- 后续可能扩展私信、互动、内容发布。

特点：

- 强绑定员工；
- 强绑定本机 Local Agent；
- 强绑定本地 Chrome Profile；
- 需要权限控制；
- 需要操作审计；
- 默认必须人工确认；
- 不能被系统随意自动操作。

### 3.3 多账号本机管理

初步目标：

```text
每个员工电脑可以管理约 10 个小红书运营账号。
```

但运行策略不能是 10 个账号同时长期开 10 个浏览器。

建议运行策略：

```text
一台员工电脑：
  常驻 Local Agent
  每个账号一个独立 Profile
  按需打开账号 Profile
  任务结束后关闭浏览器或进入空闲
```

并发建议：

- 同一账号：绝对串行；
- 同一 Profile：绝对串行；
- 同一 Local Agent：初期建议同时活跃 1～2 个浏览器，稳定后再评估 3 个；
- 评论/回复动作：初期全部串行；
- 采集任务：可以后台排队，低并发执行。

---

## 4. 数据模型改造任务

### Task A1：统一平台账号表增加账号用途字段

目标：中央服务器能够区分采集号和运营号。

建议字段：

```text
platform_account
  id
  platform
  account_role
  display_name
  platform_account_id
  owner_employee_id
  bound_local_agent_id
  profile_key
  status
  login_status
  health_status
  last_seen_at
  last_login_check_at
  created_at
  updated_at
```

其中 `account_role` 至少支持：

```text
intelligence_collector    # 情报采集号
operated_account          # 员工运营号
```

验收标准：

- 中央 API 可以创建、编辑、查询账号用途；
- 前端账号列表能展示账号用途；
- 后端 Job 创建时能基于账号用途限制任务类型；
- 采集号不能创建评论/回复 Job；
- 运营号可以创建操作型 Job，但必须走权限和审计。

---

### Task A2：建立员工、账号、Local Agent、Profile 绑定关系

目标：平台知道某个小红书账号应该由哪台员工电脑上的哪个 Profile 执行。

绑定关系：

```text
employee -> operated_account -> bound_local_agent -> profile_key
```

建议约束：

- 一个运营账号只能绑定一个主 Local Agent；
- 一个运营账号可以转移绑定，但要记录审计；
- 一个 Profile Key 对应一个小红书账号；
- 采集账号可以绑定到采集专用 Local Agent。

验收标准：

- 中央能查询“员工负责的运营账号”；
- 中央能查询“某 Local Agent 可执行哪些账号”；
- Local Agent claim job 时只能领取自己可执行的账号任务；
- Profile Key 不允许重复绑定到多个账号。

---

### Task A3：账号健康状态与登录状态

目标：避免失效账号继续执行采集或操作。

建议状态：

```text
login_status:
  unknown
  valid
  expired
  need_manual_login
  locked
  banned_or_restricted

health_status:
  healthy
  warning
  cooling_down
  blocked
  disabled
```

验收标准：

- Local Agent 支持 login check job；
- 登录失效时中央展示明确状态；
- 登录失效账号不会继续被分配任务；
- 账号异常后可自动进入 cooling_down 或 disabled；
- 前端能提醒员工处理登录问题。

---

## 5. Job 体系改造任务

### Task B1：区分采集型 Job 与操作型 Job

目标：任务队列层面明确“只读采集”和“对外操作”。

建议分类：

```text
collector_job:
  xhs_home_feed_collect
  xhs_search_collect
  xhs_creator_profile_collect
  xhs_note_detail_collect
  xhs_comment_collect

operator_job:
  xhs_comment_reply
  xhs_comment_publish
  xhs_comment_like
  xhs_login_check
```

验收标准：

- Job 类型能标识采集/操作；
- Job 创建时根据 `account_role` 校验；
- 操作型 Job 必须记录发起人；
- 操作型 Job 必须写审计日志；
- 操作型 Job 必须经过账号级锁。

---

### Task B2：新增评论/回复动作 Job

目标：员工可在中央平台点击回复，由 Local Agent 使用对应运营账号执行。

建议 Job Payload：

```json
{
  "job_type": "xhs_comment_reply",
  "account_id": "xhs_account_123",
  "profile_key": "xhs_account_123",
  "target_note_url": "https://www.xiaohongshu.com/...",
  "target_comment_id": "comment_xxx",
  "reply_text": "你好，可以私信我了解一下",
  "require_screenshot": true,
  "operator_user_id": 10001,
  "source": "operator_workspace"
}
```

验收标准：

- 中央可以创建 reply job；
- Local Agent 可以领取 reply job；
- Local Agent 使用指定 Profile 打开目标笔记；
- Local Agent 定位目标评论并回复；
- 成功后回传状态、时间、截图；
- 失败后回传错误码、错误信息、截图；
- 中央前端能展示任务结果。

---

### Task B3：账号级锁与 Profile 锁

目标：避免同一账号、同一 Profile 并发执行导致状态冲突。

锁粒度：

```text
account_id lock
profile_key lock
local_agent concurrency limit
```

初期规则：

- 同一账号一次只能执行一个任务；
- 同一 Profile 一次只能被一个浏览器进程使用；
- 操作型任务优先级高于普通后台采集；
- 评论/回复任务默认串行；
- 采集任务可以低并发排队。

验收标准：

- 并发下同一账号不会同时执行两个任务；
- 浏览器 Profile 不会被重复打开；
- 锁释放有超时和异常恢复；
- Local Agent 重启后能清理陈旧锁；
- 中央能看到任务排队原因。

---

## 6. Local Agent 执行器改造任务

### Task C1：拆分 CollectorExecutor 与 OperatorExecutor

目标：Local Agent 内部明确区分采集执行器和操作执行器。

结构建议：

```text
local_agent_runtime/
  executors/
    collector_executor.py
    operator_executor.py
  connectors/
    xhs/
      probes/
      actions/
      browser_session.py
  profile_manager.py
  account_lock.py
  browser_pool.py
```

职责：

```text
CollectorExecutor:
  推荐流、搜索、对标账号、详情、评论采集

OperatorExecutor:
  评论、回复、账号维护、登录检测
```

验收标准：

- 采集型 Job 只进入 CollectorExecutor；
- 操作型 Job 只进入 OperatorExecutor；
- 两类执行器使用统一 Profile Manager；
- 两类执行器使用统一 Result Reporter；
- 代码边界清晰，不互相混写。

---

### Task C2：Profile Manager

目标：统一管理每个小红书账号对应的本地 Chrome Profile。

能力：

- 根据 `profile_key` 获取 Profile 路径；
- 检查 Profile 是否存在；
- 启动指定 Profile 浏览器；
- 防止同一 Profile 重复打开；
- 支持关闭空闲浏览器；
- 支持记录 Profile 状态。

默认路径：

```text
local_agent/profiles/accounts/{profile_key}
```

验收标准：

- 每个账号有独立 Profile；
- Profile 路径不写死；
- Profile 目录不会进入源码包；
- 同一 Profile 并发打开会被拒绝；
- 异常退出后下次能恢复。

---

### Task C3：Browser Pool 与预热机制

目标：提高员工点击后的响应速度。

设计：

- Local Agent 常驻；
- 可选择预热 1 个浏览器；
- 对高频账号可以提前保持轻量空闲状态；
- 不长期打开所有账号；
- 根据账号最近使用时间和任务队列动态打开/关闭。

验收标准：

- 平台点击时优先展示中央缓存；
- Local Agent 刷新任务能快速开始；
- 不需要每次都完整冷启动；
- 资源占用可控；
- 浏览器崩溃后能自动恢复。

---

## 7. 中央前端与业务工作台任务

### Task D1：账号中心页面

目标：让管理员能管理采集号和运营号。

页面能力：

- 账号列表；
- 账号用途筛选；
- 绑定员工；
- 绑定 Local Agent；
- 绑定 Profile Key；
- 登录状态；
- 健康状态；
- 最近采集/操作时间；
- 禁用/启用账号。

验收标准：

- 管理员能清楚看到采集号和运营号；
- 员工只能看到自己有权限的运营号；
- 账号异常有明显提示；
- 可以查看账号对应 Local Agent 状态。

---

### Task D2：情报中心缓存优先展示

目标：员工打开页面时立即看到已有内容，而不是等待现场采集。

策略：

```text
页面打开：
  1. 读取中央缓存
  2. 展示最后更新时间
  3. 自动触发刷新 Job
  4. Local Agent 回传后增量更新
```

适用内容：

- 推荐流候选；
- 对标账号作品；
- 笔记详情；
- 评论洞察；
- 热门内容池。

验收标准：

- 页面首屏不依赖实时采集；
- 能看到数据最后刷新时间；
- 刷新状态可见；
- 刷新失败不影响已有缓存展示；
- 数据更新后前端能增量刷新。

---

### Task D3：员工运营工作台

目标：员工在中央平台处理自己账号的评论和回复。

核心页面：

```text
我的账号
待回复评论
AI 建议回复
人工编辑
发送
发送结果
失败重试
操作历史
```

默认流程：

```text
评论入池
AI 生成建议回复
员工确认或修改
创建 xhs_comment_reply job
Local Agent 执行
回传结果
中央展示审计记录
```

验收标准：

- 员工只能操作自己有权限的账号；
- 回复前可以编辑内容；
- 发送动作有明确二次确认；
- 发送后显示处理中/成功/失败；
- 每次操作都有审计记录；
- 失败后可以查看原因和截图。

---

## 8. 审计与权限任务

### Task E1：操作审计日志

目标：所有对外互动动作都可追溯。

必须记录：

- 谁发起；
- 哪个员工；
- 哪个小红书账号；
- 哪篇笔记；
- 哪条评论；
- AI 建议内容；
- 员工最终发送内容；
- 发起时间；
- 执行时间；
- 执行 Local Agent；
- 成功/失败；
- 失败原因；
- 结果截图；
- 原始 Job ID。

验收标准：

- 审计日志不可被普通员工删除；
- 管理员可按账号/员工/时间查询；
- 每个操作型 Job 都必须有审计记录；
- 失败任务也必须有记录。

---

### Task E2：权限控制

目标：员工只能操作自己负责的账号。

规则：

- 管理员可以分配账号；
- 主管可以查看团队账号；
- 员工只能看自己账号；
- 员工只能创建自己账号的操作型 Job；
- 员工不能把采集号用于评论/回复；
- 采集号不能进入运营工作台的发送动作。

验收标准：

- 后端 API 做强校验；
- 前端只展示有权限账号；
- 越权请求返回明确错误；
- 权限变更有审计记录。

---

## 9. 小红书底层引擎测试整改计划

当前下一阶段优先级是：先把小红书底层引擎测试整改好，把性能和稳定性做到极致。

### Task F1：底层引擎能力盘点

目标：明确现有 XHS 引擎已经能做什么，哪些不稳定，哪些缺失。

盘点范围：

```text
local_agent_runtime/connectors/xhs
local_agent_runtime/sessions
local_agent_runtime/chrome_launcher.py
local_agent_runtime/account_login_executor.py
local_agent_runtime/runtime.py
local_agent/scripts/start_account_chrome.py
```

输出文档：

```text
local_agent/docs/runtime/xhs-engine-audit.md
```

需要记录：

- 推荐流采集能力；
- 搜索采集能力；
- 笔记详情采集能力；
- 评论采集能力；
- 作者主页采集能力；
- 登录状态检测能力；
- 浏览器启动耗时；
- 页面打开耗时；
- DOM 等待耗时；
- 数据抽取耗时；
- 失败类型；
- 重试策略；
- 当前性能瓶颈。

验收标准：

- 有完整能力清单；
- 有每个能力的成功率和耗时；
- 有已知失败类型；
- 有下一步整改优先级。

---

### Task F2：建立 XHS 引擎性能基准测试

目标：不要凭感觉优化，要有可重复的 benchmark。

新增脚本：

```text
local_agent/scripts/bench_xhs_engine.py
```

测试指标：

- Chrome 冷启动耗时；
- Chrome 热启动耗时；
- CDP 连接耗时；
- 打开首页耗时；
- 打开搜索页耗时；
- 打开笔记详情耗时；
- 推荐流首批卡片出现耗时；
- 抽取 10 条卡片耗时；
- 抽取评论耗时；
- 单任务完整耗时；
- 失败率；
- 重试次数。

输出格式：

```text
local_agent/logs/bench/xhs_engine_bench_YYYYMMDD_HHMMSS.ndjson
```

验收标准：

- benchmark 可一键运行；
- 不依赖中央 DB；
- 可配置账号 Profile；
- 可配置测试 URL；
- 每个阶段都有耗时打点；
- 输出 ndjson，方便后续分析。

---

### Task F3：建立 XHS 引擎稳定性测试

目标：验证连续运行时的稳定性，而不是只看一次成功。

新增脚本：

```text
local_agent/scripts/stress_xhs_engine.py
```

测试方式：

- 连续执行 N 次推荐流采集；
- 连续执行 N 次详情页打开；
- 连续执行 N 次评论抽取；
- 支持间隔时间；
- 支持失败截图；
- 支持失败 HTML 快照；
- 支持自动汇总错误类型。

验收标准：

- 连续 30 次推荐流采集有成功率统计；
- 连续 30 次详情页采集有成功率统计；
- 每次失败都有错误类型；
- 不会遗留大量 Chrome 僵尸进程；
- 不会污染源码目录。

---

### Task F4：浏览器启动与 Profile 性能优化

目标：减少冷启动和切号成本。

优化方向：

- Profile 路径固定；
- 浏览器启动参数精简；
- 避免每次重新安装/初始化；
- 可选保持一个 warm browser；
- 避免重复打开同一 Profile；
- 对异常 Chrome 做清理；
- 记录实际 browser pid；
- stop 只杀项目自己管理的 pid。

验收标准：

- 冷启动耗时可观测；
- 热启动耗时可观测；
- 重复打开同一 Profile 会被拒绝；
- 停止脚本不会误杀普通 Chrome；
- 异常退出后可以恢复。

---

### Task F5：页面等待策略优化

目标：避免固定 sleep，改成基于页面状态的智能等待。

优化方向：

- 等待关键 DOM；
- 等待网络空闲只作为辅助，不能无限等；
- 对不同页面有不同 wait strategy；
- DOM 不出现时快速失败并截图；
- 可配置超时时间；
- 明确错误码。

验收标准：

- 主要采集流程没有大量固定 sleep；
- 超时错误能区分是页面未加载、登录失效、选择器失效、网络异常；
- 失败时有截图或 HTML 快照；
- benchmark 中 DOM 等待耗时下降。

---

### Task F6：数据抽取性能优化

目标：卡片、详情、评论抽取要快、稳定、结构清楚。

优化方向：

- 减少不必要的 JS evaluate 次数；
- 批量抽取 DOM 数据；
- 统一 normalize；
- 避免重复解析；
- 采集结果只保留必要字段；
- 图片、封面、作者、点赞等字段要有缺失容错。

验收标准：

- 推荐流单批卡片抽取耗时下降；
- 详情页字段稳定；
- 评论抽取字段稳定；
- 缺字段不导致整体失败；
- 输出结构与中央 ingestion 协议一致。

---

### Task F7：错误码与失败恢复

目标：失败要可诊断、可恢复、可统计。

建议错误码：

```text
browser_start_failed
cdp_connect_failed
profile_locked
login_required
page_load_timeout
selector_not_found
dom_extract_failed
rate_limited_or_blocked
network_error
unknown_error
```

验收标准：

- Local Agent 上报标准错误码；
- 中央可以按错误码统计；
- 可区分账号问题、页面问题、网络问题、代码问题；
- 失败后不会卡死任务；
- 失败后释放账号锁和 Profile 锁。

---

## 10. 开发里程碑

### Milestone 1：账号体系定型

目标：先把采集号和运营号分清楚。

任务：

- A1：账号用途字段；
- A2：员工/账号/Local Agent/Profile 绑定；
- A3：账号登录和健康状态；
- E2：基础权限校验。

验收：

- 账号中心能区分采集号和运营号；
- 后端能限制不同账号用途的 Job；
- 员工只能看到自己负责的运营账号。

---

### Milestone 2：XHS 底层引擎基准测试

目标：先知道当前引擎到底慢在哪里、错在哪里。

任务：

- F1：引擎能力盘点；
- F2：性能 benchmark；
- F3：稳定性 stress test；
- F7：错误码初版。

验收：

- 有 benchmark ndjson；
- 有稳定性测试报告；
- 有性能瓶颈清单；
- 有错误类型统计。

---

### Milestone 3：XHS 引擎性能整改

目标：把采集体验优化到员工可接受。

任务：

- F4：浏览器启动和 Profile 优化；
- F5：页面等待策略优化；
- F6：数据抽取性能优化；
- F7：失败恢复完善。

验收：

- 推荐流采集耗时显著下降；
- 详情页采集稳定；
- 评论采集稳定；
- 连续测试成功率达到可用基线；
- 失败可诊断，不会卡死任务。

---

### Milestone 4：缓存优先的情报工作台

目标：平台点击立即显示已有数据，后台刷新。

任务：

- D2：情报中心缓存优先展示；
- 采集型 Job 后台刷新；
- 前端刷新状态展示；
- 数据最后更新时间展示。

验收：

- 页面首屏不等待实时采集；
- 后台刷新完成后能更新；
- 失败时仍展示已有缓存。

---

### Milestone 5：员工评论/回复最小闭环

目标：先跑通一个账号的一条评论回复。

任务：

- B1：操作型 Job；
- B2：评论/回复 Job；
- B3：账号锁；
- C1：OperatorExecutor；
- C2：Profile Manager；
- D3：员工运营工作台基础版；
- E1：操作审计。

验收：

- 员工选择账号和评论；
- 输入或修改回复；
- 创建 reply job；
- Local Agent 执行；
- 中央展示成功/失败；
- 有截图和审计记录。

---

## 11. 当前建议立即执行的第一批任务

由于当前优先级是“先把小红书底层引擎测试整改好，把性能做到极致”，推荐开发顺序如下：

```text
第一步：F1 XHS 引擎能力盘点
第二步：F2 性能 benchmark
第三步：F3 稳定性 stress test
第四步：F7 错误码标准化
第五步：F4/F5/F6 性能整改
```

暂时不要先做复杂的评论回复工作台。  
原因是：如果底层浏览器、Profile、页面等待、数据抽取不稳定，后面的运营动作和多账号管理都会建立在不稳的基础上。

---

## 12. 给 Codex 的执行要求

后续让 Codex 实施时，必须遵守：

- 不改中央/Local Agent 的目录边界；
- Local Agent 不允许直连中央 DB；
- 中央不允许 import Local Agent；
- 不把 Chrome Profile、日志、DB、截图、缓存打进源码包；
- 所有 benchmark/stress 输出必须进入 `local_agent/logs/`；
- 所有运行产物必须被 `.gitignore` 和 `package_project.ps1` 排除；
- 性能优化必须有前后对比数据；
- 不要只靠 sleep；
- 失败必须有错误码、截图或 HTML 快照；
- 所有新增能力必须有最小测试。

---

## 13. 验收口径

本阶段不是以“代码写完”为验收，而是以以下指标验收：

```text
1. 账号用途清楚：采集号和运营号不会混用。
2. 本地执行边界清楚：真实小红书操作只发生在 Local Agent。
3. 性能可观测：每个关键阶段有耗时。
4. 稳定性可统计：连续运行有成功率和错误类型。
5. 失败可诊断：不是只报 unknown error。
6. 用户体验可接受：中央页面优先显示缓存，不阻塞等待现场采集。
7. 后续可扩展：评论/回复、多账号、审计可以自然接上。
```
