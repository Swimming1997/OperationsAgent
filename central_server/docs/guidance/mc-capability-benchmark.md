# MediaCrawler / MediaCrawlerPro 能力对标与我方第一阶段目标
**文件名：** `mc-capability-benchmark.md`  
**版本：** v1.0  
**用途：** 作为“运营情报中心第一阶段采集引擎”的能力基线、竞品对标与研发范围冻结文档。  
**阅读对象：** Codex / 后端工程师 / 系统架构师 / 产品负责人。

---

# 0. 结论先行

## 0.1 核心判断
我们不应把开源版 MediaCrawler 直接 fork 后继续堆功能，而应：

1. **把开源版 MediaCrawler 作为“已验证的多平台采集参考实现”来吃透；**
2. **把 MediaCrawlerPro 的公开能力作为“第一阶段引擎功能对标线”；**
3. **围绕我们的业务目标，自研一套更适合情报中心的 Intelligence Engine。**

## 0.2 为什么不能直接 fork 开源版
因为我们的产品第一阶段核心不是“关键词搜索爬虫”，而是：

- 小红书首页推荐流内容库；
- 抖音视频推荐页；
- 抖音图文推荐页；
- 多员工、多账号、多终端的任务调度；
- 内容全局去重与共享；
- 候选内容详情/评论补采；
- 对标账号更新监控；
- 后续服务情报中心、对标作品库、素材库与 AI 筛选。

而开源版 MediaCrawler 的当前公开主模式仍是：

- `search`
- `detail`
- `creator`

它没有把 **HomeFeed / 推荐流** 作为现有主链路，也没有围绕“组织级情报共享”来设计数据模型和任务模型。

## 0.3 我们第一阶段的对标目标
第一阶段引擎至少要覆盖 MediaCrawlerPro 公开宣称的以下关键能力：

- 多平台：首页推荐信息流 HomeFeed；
- 多账号；
- 断点续跑；
- 签名逻辑解耦；
- Cookie / Session 同步机制；
- 搜索 / 详情 / 创作者主页 / 评论能力；
- 可服务后续前端与任务系统的 API 化设计。

---

# 1. 资料范围与事实基线

## 1.1 本文依据
本文依据四类材料形成：

1. 我方《运营情报中心产品说明与需求文档》；
2. 开源版 MediaCrawler 当前仓库 README、项目架构文档、代码结构文档；
3. 开源版 MediaCrawler 核心源码文件：
   - `main.py`
   - `cmd_arg/arg.py`
   - `config/base_config.py`
   - `base/base_crawler.py`
   - `media_platform/xhs/core.py`
   - `media_platform/xhs/client.py`
   - `media_platform/xhs/login.py`
   - `media_platform/xhs/playwright_sign.py`
   - `media_platform/douyin/core.py`
   - `media_platform/douyin/client.py`
   - `media_platform/douyin/help.py`
   - `media_platform/douyin/login.py`
   - `tools/cdp_browser.py`
   - `tools/browser_launcher.py`
   - `store/xhs/__init__.py`
   - `store/douyin/__init__.py`
   - `database/models.py`
   - `var.py`
   - `api/main.py`
4. MediaCrawlerPro 的公开主页、公开 README 与订阅说明。

## 1.2 重要边界
MediaCrawlerPro 源码并未公开，本文对 Pro 的判断仅基于公开信息，不假装知道其内部源码实现。  
因此，本文的 Pro 对标结论属于：

- 功能对标；
- 架构意图对标；
- 我方研发目标约束；

不属于：

- Pro 源码级实现复刻；
- Pro 内部数据结构还原；
- Pro 私有代码逻辑推断。

---

# 2. 我方业务需求映射

## 2.1 PRD 中与采集引擎直接相关的能力
我方 PRD 已明确需要：

1. **情报中心**
   - 采集抖音、小红书内容；
   - 通过关键词、点赞数、评论数筛选；
   - 手动选中或 AI 选中进入作品库。

2. **AI 选中规则**
   - 获客库需命中“求推 / 求推荐 / 怎么联系”等意向词；
   - 非获客库主要依据互动阈值。

3. **对标账号更新**
   - 录入对标账号；
   - 新作品及时入库；
   - 触发提醒。

4. **账号管理**
   - 多员工；
   - 多平台账号；
   - 账号归属到员工；
   - 内容可共享。

## 2.2 对采集引擎的真实要求
因此，采集引擎不是“抓帖子脚本”，而是要提供：

- 内容发现；
- 详情补采；
- 评论补采；
- 对标账号监控；
- 全局去重；
- 多账号运行；
- 持久化任务；
- 共享数据池。

---

# 3. 能力矩阵总览

## 3.1 平台与任务类型对标

| 能力 | 开源 MediaCrawler | MediaCrawlerPro 公开能力 | 我方第一阶段要求 |
|---|---:|---:|---:|
| 小红书 | 支持 | 支持 | 必须 |
| 抖音 | 支持 | 支持 | 必须 |
| 快手 | 支持 | 支持 | 暂不做 |
| B站 | 支持 | 支持 | 暂不做 |
| 微博 | 支持 | 支持 | 暂不做 |
| 知乎 | 支持 | 支持 | 暂不做 |
| 搜索 Search | 支持 | 支持 | 要有，但非最高优先级 |
| 指定内容 Detail | 支持 | 支持 | 必须 |
| 创作者主页 Creator | 支持 | 支持 | 必须 |
| 首页推荐流 HomeFeed | 未见正式主链路 | 明确支持 | 必须，且是第一优先级 |
| 评论抓取 | 支持 | 支持 | 必须 |
| 二级评论 | 支持 | 支持 | 第一阶段可选，结构要预留 |
| 媒体下载 | 支持 | Pro 有 Downloader | 第一阶段不作为主功能，但接口预留 |

---

## 3.2 会话、账号、任务能力对标

| 能力 | 开源版 | Pro 公开能力 | 我方要求 |
|---|---:|---:|---:|
| 二维码登录 | 支持 | 公开未逐项说明 | 可保留调试用 |
| Cookie 登录 | 支持 | 公开未逐项说明 | 要支持 |
| 浏览器持久化登录态 | 支持 | Pro强调去 Playwright 主干依赖 | 要支持，但抽象成 Session Provider |
| CDP 连接已有浏览器 | 支持 | Pro强调重构 | 可作为阶段性方案 |
| 多账号池 | 未形成产品级账号池 | 明确支持 | 必须 |
| 账号健康状态 | 未见完整状态机 | 未公开细节 | 必须自研 |
| 断点续跑 | 未见任务级正式支持 | 明确支持 | 必须 |
| 任务调度 | 未见服务级调度引擎 | 未公开细节 | 必须自研 |
| 内容去重共享 | 存储层可落库，但非业务级共享池 | 未公开细节 | 必须自研 |
| 补采租约 | 未见 | 未公开 | 必须自研 |
| 签名服务独立化 | 开源版部分仍嵌在项目内 | 明确新增签名服务 | 必须设计可插拔 Signer Boundary |
| CookieBridge / Session Bridge | 开源版无独立机制 | Pro仓库列表公开 CookieBridge | 我方需有 Session Bridge 概念 |

---

## 3.3 数据模型与产品化能力对标

| 能力 | 开源版 | Pro 公开能力 | 我方要求 |
|---|---:|---:|---:|
| CSV / JSON / JSONL | 支持 | 支持多种存储 | 不作为业务主存储 |
| SQLite / MySQL / PostgreSQL / MongoDB | 支持多种 | 支持多种 | 第一阶段建议 PostgreSQL / SQLite 任选一套正式落地 |
| 平台原始表 | 有 | 未公开 | 不足，需要统一内容层 |
| 全局内容身份表 | 无 | 未公开 | 必须 |
| 内容发现事件表 | 无 | 未公开 | 必须 |
| 内容快照表 | 无 | 未公开 | 必须 |
| 评论快照 / 线索规则表 | 无 | 未公开 | 必须 |
| 前端情报中心服务模型 | 无 | 未公开 | 必须 |
| 主管/员工角色接口 | 无 | 未公开 | 第一阶段可以只做字段预留 |

---

# 4. 开源 MediaCrawler 已经做得好的地方

## 4.1 多平台 Connector 思想成立
开源版已经将 XHS、DY 等平台拆在 `media_platform/*` 下，并通过 `CrawlerFactory` 创建对应爬虫对象。  
这说明：

- 平台实现分层是对的；
- 公共抽象层是必要的；
- 我方未来也应采用 `Connector` / `PlatformAdapter` 思路。

## 4.2 Search / Detail / Creator 三类基础任务都已验证
小红书和抖音都具备：

- 搜索；
- 指定内容详情；
- 创作者主页；
- 评论抓取。

这证明我方后续并非从零探索，而是要把“推荐流”和“产品化引擎”补上。

## 4.3 详情与评论链路是可借鉴的
以小红书为例：

- 搜索结果中提取 `note_id / xsec_token / xsec_source`；
- 通过详情接口补齐正文与互动数据；
- 再按内容 ID 拉评论；
- 必要时 HTML 详情页做 fallback。

这个“发现 → 详情 → 评论”的三级链路，适合被我们继承为正式任务模型。

## 4.4 CDP / 浏览器态与 HTTP 请求态联动思路值得参考
开源版使用浏览器上下文完成登录与 Cookies 获取，再通过 HTTP 客户端请求接口。  
这是我们“浏览器负责发现、请求层负责补采”的重要技术参考。

## 4.5 Store 层虽不适合直接复用，但字段映射有价值
开源版将平台原始数据映射为较规整的存储字段：

- 小红书：
  - note_id
  - title
  - desc
  - liked_count
  - comment_count
  - collected_count
  - image_list
- 抖音：
  - aweme_id
  - title / desc
  - create_time
  - liked_count
  - comment_count
  - collected_count
  - cover_url

这些字段可作为我们统一 `ContentSnapshot` 模型的输入参考。

---

# 5. MediaCrawlerPro 公开能力对我们的意义

## 5.1 Pro 公开承认了开源版的结构性问题
Pro 的公开说明明确提到，开源版暴露出一系列问题：

- 多账号；
- 断点续爬；
- Linux 部署；
- Playwright 依赖；
- 部署复杂性。

这与我们审计普通版源码得到的判断一致：  
**开源版适合学习和验证，不宜直接被改造成我们的长期引擎。**

## 5.2 Pro 公开新增的关键能力，正是我们的第一阶段目标
### 重点 1：首页推荐信息流 HomeFeed
这是我方情报中心的核心入口。  
相比关键词搜索，HomeFeed 更贴合“员工养号后刷到什么，就把什么沉淀为情报”的业务模式。

### 重点 2：多账号
我方天然存在：
- 员工 A 负责多个抖音 / 小红书账号；
- 员工 B 负责另外的账号；
- 多账号共同组成内容发现网络。

因此，多账号不是优化项，而是底层实体。

### 重点 3：断点续跑
任何长任务都需要：
- 中断后恢复；
- 某页失败后从 checkpoint 接上；
- 不能因某一条内容异常就整轮任务作废。

### 重点 4：签名服务解耦
我方引擎必须设计：
- Signer Interface；
- 平台特定 Signer Provider；
- 上层业务不感知具体签名实现。

### 重点 5：CookieBridge
我方未必实现与 Pro 同名的 CookieBridge，但必须有：
- Session Bridge；
- 账号登录态同步；
- 本地 Agent 与中心服务之间的 Session 生命周期协议。

---

# 6. 我方引擎要“比 Pro 更贴近业务”的地方

## 6.1 HomeFeed 是主入口，不是附加功能
Pro 的公开列表将 HomeFeed 作为一个功能项。  
我方第一阶段应把它提升为第一主链路：

```text
Feed Discovery
→ Candidate Filter
→ Detail Enrichment
→ Comment Enrichment
→ Intelligence Pool
```

## 6.2 多账号的价值不是“更猛地抓”，而是“更广地发现 + 更少地重复补采”
我方必须做：

- `content_identity`
- `content_discovery_event`
- `content_snapshot`
- `fetch_lease`

这样多个员工、多个账号刷到同一条内容时：
- 只记录多次发现；
- 不重复拉取正文；
- 不重复跑评论补采；
- 不重复做 AI 判断。

## 6.3 采集引擎要天然服务情报中心
开源爬虫更多围绕“抓下来存什么”。  
我方要围绕“运营怎么用”设计字段：

- `business_keyword_hits`
- `lead_keyword_hits`
- `candidate_grade`
- `source_feed_type`
- `discovered_by_account`
- `discovered_by_employee`
- `material_candidate_status`

---

# 7. 逐能力设计决策

## 7.1 HomeFeed
### 我方决策
第一阶段必须做，并且同时支持：

- 小红书推荐页；
- 抖音视频推荐页；
- 抖音图文推荐页。

### 输出标准
统一返回：

```json
{
  "platform": "xhs",
  "feed_type": "home_recommend",
  "account_id": "acc_001",
  "items": [
    {
      "platform_content_id": "...",
      "canonical_url": "...",
      "author_id": "...",
      "author_name": "...",
      "title_or_summary": "...",
      "cover_url": "...",
      "visible_like_count": 123,
      "content_type": "image_text",
      "feed_position": 12,
      "discovered_at": "..."
    }
  ]
}
```

---

## 7.2 Detail
### 我方决策
必须独立为 Detail Connector，不与 Feed 绑定。

### 支持来源
- HomeFeed；
- Search；
- Creator Monitor；
- 手动输入链接。

---

## 7.3 Comments
### 我方决策
评论抓取是“候选后补采”，不是默认全量抓取。

第一阶段：
- 默认前 N 条；
- 支持规则词识别；
- 支持升级为更深评论抓取；
- 二级评论结构预留。

---

## 7.4 Creator Monitor
### 我方决策
这是对标账号更新库的底座，第一阶段必须做。

### 核心流程
```text
Creator identity
→ latest posts
→ compare with stored latest cursor/content ids
→ new content event
→ insert/update pool
→ notification event
```

---

## 7.5 Search
### 我方决策
保留能力，但业务优先级低于 HomeFeed。

原因：
- 首页情报中心主入口是推荐流；
- Search 更适合作为：
  - 手动补充；
  - 关键词专项研究；
  - 对标扩散发现。

---

# 8. 第一阶段能力优先级

## P0：必须立即具备
1. Account / Session 抽象；
2. Job / Checkpoint / Resume；
3. 小红书 HomeFeed；
4. 抖音视频 HomeFeed；
5. 抖音图文 HomeFeed；
6. Detail Connector；
7. Comment Connector；
8. 全局去重；
9. Creator Monitor。

## P1：第一阶段后半程补齐
1. Search Connector；
2. 更深评论策略；
3. 账号健康看板；
4. 采集日志面板；
5. 媒体下载接口。

## P2：后续阶段
1. ContentRemixAgent；
2. 下载器 UI；
3. 多平台扩展到快手/B站/知乎；
4. 更复杂 AI 标签体系。

---

# 9. 功能差距清单

## 9.1 开源版相对我方的差距
| 差距 | 影响 |
|---|---|
| 无正式 HomeFeed 主线 | 不能直接支撑推荐页情报中心 |
| 无多员工/多账号业务模型 | 不适合组织级运营 |
| 全局去重不足 | 多账号重复采集成本高 |
| 任务恢复能力弱 | 长任务失败代价大 |
| 配置大量依赖全局可变状态 | 不适合服务化并发 |
| 数据库是平台原始表思路 | 不适合作为共享情报池 |
| 错误处理不够产品化 | 难以接后台任务中心 |

## 9.2 Pro 公开能力相对我方的差距
| 差距 | 判断 |
|---|---|
| Pro 已有 HomeFeed，但未知其是否围绕“推荐流筛选运营情报”建模 | 我方仍需自研业务模型 |
| Pro 已有多账号，但未知其是否支持员工/账号/内容共享组织关系 | 我方要按运营系统设计 |
| Pro 有 CookieBridge，但未知其是否适配“本地 Agent + 中央服务”的协作协议 | 我方要建立自己的 Session Bridge |
| Pro 有 Downloader / Agent 功能 | 非我方第一阶段核心 |

---

# 10. 研发策略建议

## 10.1 不直接 fork
推荐策略：

```text
阅读 MediaCrawler 源码
→ 提取可借鉴模式
→ 编写我方引擎架构
→ 从零建立 Intelligence Engine
→ 部分算法/适配思路参考开源版
```

## 10.2 把“签名逻辑”视为可替换依赖
无论当前是：
- 浏览器态辅助；
- JS 签名模块；
- 独立 Sign Service；

上层 Connector 都不应直接耦合实现。

建议接口：

```python
class SignerProvider(Protocol):
    async def sign(self, request: SignRequest, session: SessionContext) -> SignedRequest:
        ...
```

## 10.3 把“Session”视为平台采集的核心资产
建议接口：

```python
class SessionProvider(Protocol):
    async def get_session(self, account_id: str) -> SessionContext:
        ...

    async def refresh_session(self, account_id: str) -> SessionContext:
        ...

    async def mark_invalid(self, account_id: str, reason: str) -> None:
        ...
```

---

# 11. 第一阶段验收矩阵

| 项目 | 验收标准 |
|---|---|
| 小红书 HomeFeed | 可采样 50 条，支持刷新重复采样 |
| 抖音视频 HomeFeed | 可采样 50 条 |
| 抖音图文 HomeFeed | 可采样 50 条 |
| Detail | 可将候选内容补齐正文与互动 |
| Comment | 可抓取前 N 条评论并命中“求推”词 |
| Creator Monitor | 可识别对标账号新作品 |
| Multi-account | 可指定账号执行任务 |
| Resume | 任务中断后可恢复 |
| Dedup | 同内容多账号发现不重复补采 |
| Service API | 前端或任务中心可调度引擎 |
| Data Model | 能落入统一内容主表、发现事件表、快照表 |

---

# 12. 最终建议

## 12.1 对普通版 MediaCrawler 的定位
- **学习对象**
- **实验基线**
- **适配思路来源**
- **问题案例来源**

## 12.2 对 MediaCrawlerPro 的定位
- **功能能力对标线**
- **第一阶段目标压力线**
- **后续若取得源码，可做进一步源码级复盘**

## 12.3 对我方引擎的定位
不是另一个通用爬虫，而是：

# 运营情报中心的内容发现与补采引擎

它要围绕：
- 首页推荐流；
- 对标账号更新；
- 多账号组织协作；
- 去重共享；
- 规则筛选；
- 后续 AI 运营系统；

来进行架构设计。

---

# 13. 给 Codex 的执行原则

1. 不直接 fork MediaCrawler。
2. 不把开源版的全局配置模型照搬。
3. 不把 Session、Job、Connector、Store 混在一个对象里。
4. 不使用 `sys.exit()` 式错误处理。
5. 不让单条内容失败终止整轮任务。
6. 不把签名逻辑写死在 Connector 内。
7. 不用平台原始表直接当产品主模型。
8. HomeFeed 是第一入口，而不是 Search 的附属。
9. 多账号不是“多并发”，而是“可调度、可共享、可恢复”。
10. 所有后续编码都要以本文和 `intel-engine-architecture-v0.1.md` 为架构基准。
