# 运营情报中心第一阶段采集引擎建设计划书

## 0. 文档目的

本计划书面向“运营情报中心”第一阶段研发，目标不是先做完整业务前台，而是优先建设一套可持续演进的 **多平台内容采集引擎**，为后续情报中心、对标作品库、素材库、AI筛选、账号监控提供可靠数据底座。

第一阶段的核心问题只有一个：

> 我们能否稳定、可扩展、可复用地拿到抖音与小红书上所需的数据项，尤其是首页推荐流、详情、评论、创作者更新，并把这些能力沉淀为可长期维护的引擎？

---

## 1. 第一阶段的目标边界

### 1.1 本阶段必须完成

1. 建立一个独立的 **采集引擎服务**，而不是把脚本散落在业务代码里。
2. 支持至少以下采集能力：
   - 小红书首页推荐流 HomeFeed
   - 抖音视频推荐页 HomeFeed
   - 抖音图文推荐页 HomeFeed
   - 内容详情采集
   - 评论预览采集
   - 创作者主页最新作品采集
3. 支持至少以下工程能力：
   - 多账号会话管理
   - 任务调度与断点续跑
   - 全局内容去重
   - 详情补采缓存
   - 失败重试与错误分级
   - 采集任务日志与可观测性
4. 能服务情报中心 MVP：
   - 推荐流下滑 50 条
   - 刷新后继续采样
   - 按关键词、求推词、点赞阈值做初筛
   - 入库并可供后续前端展示

### 1.2 本阶段暂不做

1. 仿写、仿画、底图库完整业务流
2. 完整 RBAC 权限系统
3. 复杂运营后台 UI
4. 自动发布
5. 大规模分布式部署
6. 复杂 AI 内容理解，仅保留规则筛选与后续 AI 接口预留

---

## 2. 对 MediaCrawler / MediaCrawlerPro 的判断

## 2.1 开源 MediaCrawler 的可借鉴点

公开版 MediaCrawler 当前具备：

- 多平台支持：小红书、抖音、快手、B站、微博、贴吧、知乎
- 三类主模式：关键词搜索、指定帖子详情、创作者主页
- 评论抓取、二级评论
- 登录态缓存
- IP代理池
- 多种存储方式
- 基于 Playwright / CDP 的登录与动态参数获取

其核心技术思路是：

> 借助保留登录态的浏览器上下文执行 JS 表达式，拿到动态签名参数，从而避免离线完整逆向签名算法。

这点对我们的第一阶段非常关键。

---

## 2.2 MediaCrawlerPro 的公开能力清单

根据其公开说明，Pro 版本相比开源版重点新增：

1. 断点续爬
2. 多账号 + IP 代理池
3. 移除 Playwright 主干依赖
4. 新增独立签名服务
5. 完整 Linux 支持
6. 多平台首页推荐信息流 HomeFeed
7. CookieBridge
8. Downloader
9. ContentRemixAgent
10. AI Agent Skill

其中对我们第一阶段最重要的是：

- 首页推荐信息流 HomeFeed
- 断点续爬
- 多账号
- 签名逻辑服务化
- Cookie / Session 同步机制

这几项应当成为我们引擎的 **第一阶段对标能力**。

---

## 2.3 对开源版的审计态度

不能直接把开源 MediaCrawler 当成我们的主系统来改。

原因不是它没有价值，而是：

1. 它更像一个“通用爬取工具”，不是“产品级采集引擎”。
2. 它的业务入口是 search/detail/creator，而我们的核心入口是 HomeFeed + 情报筛选。
3. Pro 的诞生背景已经说明，开源版在多账号、断点续爬、Linux、Playwright 耦合等方面存在需要重构的地方。
4. 公开 issue 中也能看到，Playwright 环境、浏览器连接、抖音参数失效、Windows 连接异常等问题值得重点审计。

因此我们要做的是：

> 吃透其源码，吸收其架构经验，复用可复用的实现思想，但不盲目 fork 后堆功能。

---

# 3. 第一阶段总体架构

```text
┌─────────────────────────────────────────────┐
│              情报中心业务层                  │
│   推荐流任务 / 对标监控 / 筛选 / 入库        │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│              Intelligence Engine API          │
│  /feed_runs /content_fetch /creator_monitor   │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│              任务调度与状态层                │
│  Job Scheduler / Resume / Retry / Lease      │
└──────────────────────┬──────────────────────┘
                       │
┌───────────────┬──────▼───────────┬──────────┐
│ Session层     │  Connector层      │ Storage层 │
│ 多账号会话     │  XHS/DY Feed      │ 去重缓存    │
│ Profile管理    │  Detail/Comment   │ 快照与日志  │
│ Cookie桥接     │  Creator Monitor  │            │
└───────────────┴───────────────────┴──────────┘
```

---

# 4. 核心模块设计

## 4.1 Session Manager：多账号会话管理

### 职责
- 平台账号与本地 Session 绑定
- 每个账号有独立会话状态
- 支持账号健康状态：
  - active
  - need_login
  - need_manual_verify
  - degraded
  - paused
- 向 Connector 层提供当前有效请求上下文

### 第一阶段实现要求
- 支持小红书、抖音账号
- 支持每个账号独立 profile/session
- 支持手动登录后持久化
- 支持调试时指定账号执行任务

---

## 4.2 Feed Connector：首页推荐流引擎

### 必须支持
- 小红书推荐页
- 抖音视频推荐页
- 抖音图文推荐页

### 目标
把每个平台首页推荐流统一抽象为：

```json
{
  "platform": "xhs",
  "feed_type": "home_recommend",
  "account_id": "acc_xhs_001",
  "items": [
    {
      "platform_content_id": "...",
      "url": "...",
      "author_id": "...",
      "author_name": "...",
      "title_or_summary": "...",
      "cover_url": "...",
      "visible_like_count": 123,
      "content_type": "image_text",
      "feed_position": 17,
      "collected_at": "..."
    }
  ]
}
```

### 第一阶段目标动作
- 页面进入
- 下滑加载
- 累计 50 条
- 刷新页面
- 再采若干轮
- 提取内容ID和卡片级字段

---

## 4.3 Detail Connector：详情补采引擎

### 职责
输入内容 ID / URL，补齐：
- 完整标题
- 正文
- 作者
- 互动数
- 发布时间
- 图片 / 视频信息
- 详情页 URL
- 评论拉取所需参数

### 设计要求
- 不与 Feed 耦死
- 任何来源发现的内容都可补采：
  - HomeFeed
  - 搜索
  - 创作者主页
  - 手动录入链接

---

## 4.4 Comment Connector：评论引擎

### 第一阶段范围
- 默认抓前 N 条评论
- 支持按需抓更多
- 支持识别：
  - 求推
  - 求推荐
  - 推一下
  - 怎么联系
  - 求渠道
  - 能发吗
  - 多少钱
- 评论结果支持入线索规则引擎

### 原则
- 评论抓取是“候选后深挖”，不是全量默认打开。
- 优先保证情报筛选，而不是一次性无限抓评论。

---

## 4.5 Creator Monitor：对标账号更新引擎

### 职责
- 录入对标账号
- 获取该账号最新内容
- 与历史内容比对
- 发现新作品
- 触发提醒 / 入对标更新库

### 第一阶段必须具备
- 小红书创作者监控
- 抖音创作者监控
- “账号组 → 我方账号类型”的映射预留

---

## 4.6 Job Engine：任务系统

### 任务类型
- feed_collect
- detail_fetch
- comment_fetch
- creator_monitor

### 必须能力
- 任务状态：
  - pending
  - running
  - success
  - partial_success
  - failed
  - paused
- 支持断点续跑
- 支持任务幂等
- 支持同内容补采租约，避免多账号重复补采

---

## 4.7 Storage & Dedup：共享池与去重层

### 核心数据表

#### content_identity
- platform
- platform_content_id
- canonical_url
- first_seen_at
- last_seen_at

#### content_discovery_events
- content_id
- account_id
- feed_type
- discovered_at
- feed_position

#### content_snapshots
- content_id
- title
- text
- like_count
- comment_count
- collect_count
- snapshot_at

#### content_enrichment
- content_id
- business_keyword_hits
- lead_keyword_hits
- preliminary_decision
- material_candidate_status

#### jobs
- job_id
- job_type
- account_id
- status
- payload
- checkpoint
- retry_count
- created_at
- updated_at

---

# 5. 对 MediaCrawler 开源版的源码审计计划

## 5.1 审计目标

我们不是为了“学会怎么运行 MediaCrawler”，而是要回答：

1. 哪些模块值得直接借鉴？
2. 哪些设计不适合产品化引擎？
3. 哪些模块应完全重写？
4. 哪些问题在 Pro 里大概率已解决，我们是否要直接以 Pro 为对标目标实现？
5. 我们自己的引擎边界应该如何划定？

---

## 5.2 源码阅读顺序

### 第 1 层：程序主流程
- main.py
- cmd_arg/arg.py
- config/base_config.py
- var.py

目标：
- 看清启动模型、配置模型、命令模型
- 判断其是否适合作为服务化引擎基础

### 第 2 层：抽象层
- base/base_crawler.py

目标：
- 看平台抽象是否合理
- 看生命周期是否能支撑 HomeFeed
- 看登录、存储、客户端抽象有没有耦合

### 第 3 层：浏览器与执行基础设施
- tools/browser_launcher.py
- tools/cdp_browser.py
- libs/stealth.min.js

目标：
- 看浏览器管理、CDP连接、会话保存方式
- 看浏览器依赖为何会被 Pro 移出主干
- 看这里是否适合作为我们 Session Manager 的参考

### 第 4 层：平台实现
优先审计：
- media_platform/xhs/
- media_platform/douyin/

每个平台重点看：
- core.py
- client.py
- login.py
- help.py
- field.py
- exception.py

目标：
- 数据请求层如何设计
- 签名参数在哪里耦合
- 错误分类是否足够
- 重试策略是否合理
- Creator / Detail / Search 模式是否高度重复

### 第 5 层：存储、缓存、代理
- store/
- database/
- cache/
- proxy/

目标：
- 是否支持任务级增量、断点恢复
- 是否支持全局去重
- 是否只是“落文件/落库”，而不是“面向产品的数据模型”
- 代理池是不是过早进入主链路

### 第 6 层：API/WebUI
- api/

目标：
- 看其 WebUI 是“工具控制台”还是可演进的系统入口
- 判断我们是否值得借鉴其接口形式

---

## 5.3 审计维度

每个模块都从以下维度打分：

1. 可读性
2. 可维护性
3. 可扩展性
4. 平台耦合度
5. 任务恢复能力
6. 多账号能力
7. 错误模型
8. 观测性
9. 数据模型质量
10. 是否适合纳入我们的引擎设计

最终产出：

### 《MediaCrawler 开源版架构审计报告》
包括：
- 模块图
- 数据流图
- 关键类关系
- 问题清单
- 借鉴清单
- 不复用清单
- 对我们引擎的设计约束

---

# 6. 与 MediaCrawlerPro 的对标矩阵

| 能力 | Pro公开能力 | 我们第一阶段 |
|---|---|---|
| 多平台 | 有 | 只做 XHS + DY |
| 首页推荐流 HomeFeed | 有 | 必须有 |
| 搜索 | 有 | 可放第二优先级 |
| 指定内容详情 | 有 | 必须有 |
| 评论 | 有 | 必须有 |
| 创作者主页 | 有 | 必须有 |
| 多账号 | 有 | 必须有 |
| 断点续跑 | 有 | 必须有 |
| 签名服务解耦 | 有 | 需要评估并优先设计解耦边界 |
| CookieBridge | 有 | 我们要设计 Session Bridge / Account Session 同步机制 |
| AI Agent Skill | 有 | 第一阶段只预留，不实现 |
| 内容拆解Agent | 有 | 不属于第一阶段采集引擎 |
| Downloader | 有 | 暂缓，但保留素材下载接口 |

---

# 7. 第一阶段实施里程碑

## M0：事实验证与能力画像

### 目标
先把 MediaCrawler 开源版跑起来，并建立我们自己的测试基线。

### 任务
1. 拉起开源 MediaCrawler
2. 跑通：
   - xhs search
   - xhs detail
   - xhs creator
   - dy search
   - dy detail
   - dy creator
3. 收集输出字段
4. 梳理配置项
5. 记录失败模式与异常日志
6. 阅读 Pro 的公开能力与组织结构

### 验收
- 产出《MediaCrawler 公开能力矩阵》
- 产出《MediaCrawler 实测字段矩阵》
- 产出《MediaCrawler 问题记录初版》

---

## M1：开源版源码审计完成

### 目标
吃透普通版源码，形成客观评价。

### 任务
- 按第 5 章顺序读完核心源码
- 输出架构图
- 标注核心抽象
- 找出重复、耦合、难扩展部分
- 找出可借鉴实现

### 验收
- 产出《MediaCrawler 开源版架构审计报告》
- 产出《哪些代码思想可复用，哪些不能复用》

---

## M2：我们的 Intelligence Engine 总体骨架

### 目标
建立独立引擎项目骨架。

### 任务
- 初始化工程
- 建立模块边界：
  - sessions
  - jobs
  - connectors
  - stores
  - filters
  - APIs
- 建立统一数据模型
- 建立日志与错误协议
- 建立任务状态机

### 验收
- 能启动 API
- 能创建采集任务
- 能入队、执行空任务、记录状态
- 基础数据库可用

---

## M3：Session Manager + 多账号基础

### 目标
解决账号状态与会话生命周期。

### 任务
- 平台账号表
- 本地账号 profile/session 记录
- 手动登录后的持久化方案
- 账号状态管理
- 任务执行时选择指定账号
- 账号健康状态接口

### 验收
- 能注册 XHS/DY 账号
- 能标记账号当前状态
- 能指定账号发起后续采集任务

---

## M4：HomeFeed MVP

### 目标
实现首页推荐流采集。

### 任务
- 小红书 HomeFeed
- 抖音视频 HomeFeed
- 抖音图文 HomeFeed
- 统一抽象输出
- 支持采样 50 条
- 支持刷新后继续采样
- 支持发现事件写库

### 验收
- 三类 Feed 均能输出结构化内容列表
- 每轮任务能返回 feed_position 和账号信息
- 全局内容主表去重生效

---

## M5：Detail + Comment 补采

### 目标
把 feed 发现的内容补齐成可筛选情报。

### 任务
- 内容详情补采
- 评论前 N 条补采
- 求推词识别
- 点赞阈值筛选
- 详情补采缓存
- 补采任务租约

### 验收
- Feed 中的候选内容可自动进入详情补采队列
- 能输出筛选结果
- 同一内容被多账号发现时，只补采一次有效详情

---

## M6：Creator Monitor

### 目标
实现对标账号更新监控底座。

### 任务
- 创作者主页采集
- 最新作品识别
- 新作品事件
- 更新提醒接口预留
- 与内容主表融合

### 验收
- 配置一个创作者后，可拉取最新内容
- 新作品能被识别并写库
- 不重复入库

---

## M7：情报中心最小闭环

### 目标
把第一阶段引擎接到最小业务页面。

### 任务
- 情报任务发起页
- 情报结果列表
- 关键词/点赞筛选
- 手动入库按钮
- 对标更新库最小页

### 验收
- 运营可从页面发起任务
- 看到采集结果
- 能按规则筛选
- 能把结果送到后续业务表

---

# 8. 开发优先级建议

## P0
- MediaCrawler 源码审计
- Intelligence Engine 基础骨架
- Session Manager
- HomeFeed 三路采集
- Detail / Comment 补采
- 全局去重与任务状态机

## P1
- Creator Monitor
- 对标账号更新库
- 最小情报中心页面
- 采集运行日志面板

## P2
- 更丰富的评论抓取策略
- 关键词配置后台
- 账号健康看板
- AI筛选接口预留

---

# 9. 第一阶段最关键的验收指标

| 指标 | 标准 |
|---|---|
| HomeFeed 支持 | XHS + DY视频 + DY图文 |
| 单轮采样 | 每任务 50 条 |
| 去重 | 平台内容ID级别全局去重 |
| 详情补采 | 候选项可自动补全详情 |
| 评论补采 | 可拉前 N 条评论并做词命中 |
| 多账号 | 至少支持多个账号配置与任务指定 |
| 断点恢复 | 中断后可续跑或安全重试 |
| 对标监控 | 创作者新作品可识别 |
| 最小页面 | 可发任务、看结果、手动入库 |

---

# 10. 关键设计原则

1. 不把 MediaCrawler 直接改造成产品，而是把它当成研究对象和能力参照。
2. 不把浏览器操作、签名逻辑、业务筛选混在一起。
3. 不把“抓一次数据”当目标，要把“长期可维护的采集引擎”当目标。
4. HomeFeed 是我们与普通爬虫项目的关键区别。
5. 多账号、断点续跑、去重共享是第一阶段就要打下的底座，不是后补能力。
6. 先做 XHS + DY，不泛化到更多平台。
7. 先做采集引擎，再做完整情报中心产品层。

---

# 11. 建议的立即启动清单

马上开始做这 5 件事：

1. 创建《MediaCrawler 开源版源码审计任务单》
2. 创建《我们的引擎能力清单 v0.1》
3. 拉通 MediaCrawler 的 XHS/DY 基础运行
4. 拆解其 XHS/DY 的 core/client/login/help
5. 设计 Intelligence Engine 的模块骨架和统一数据模型

---

# 12. 本计划的最终产出

第一阶段结束后，我们应该拥有：

1. 一份完整的 MediaCrawler 开源版审计报告
2. 一份 MediaCrawlerPro 对标能力矩阵
3. 一套自研 Intelligence Engine
4. HomeFeed + Detail + Comment + Creator Monitor 四类核心 Connector
5. 多账号、断点续跑、去重共享能力
6. 一个能支撑情报中心 MVP 的真实数据底座
