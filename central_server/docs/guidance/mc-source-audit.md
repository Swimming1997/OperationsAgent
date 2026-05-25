# MediaCrawler 开源版源码审计报告
**文件名：** `mc-source-audit.md`  
**版本：** v1.0  
**审计对象：** `NanmiCoder/MediaCrawler` 当前主分支核心源码  
**用途：** 判断哪些设计可借鉴、哪些问题必须规避，并为我方情报采集引擎提供反面约束与正面参考。

---

# 0. 审计结论摘要

## 0.1 总评
MediaCrawler 开源版是一个 **功能广、平台多、上手快** 的研究型多平台采集项目。  
它已经证明了以下路线在工程上可行：

- 平台分模块；
- 浏览器登录态 + HTTP 请求补采；
- 搜索 / 详情 / 创作者主页 / 评论采集；
- 多种存储方式；
- CDP 连接真实浏览器；
- 部分平台签名逻辑的动态/独立处理。

但它当前的代码组织仍偏向：

> **“单次任务脚本 + 全局配置驱动”**

而不是：

> **“多账号、多任务、可恢复、可调度、可服务化的采集引擎”**

因此：

- **不能直接作为我方 Intelligence Engine 的工程底座；**
- **适合被逐模块研究、提取经验；**
- **其核心问题必须被我方架构反向约束。**

---

# 1. 审计边界

## 1.1 已审计源码
本次逐项阅读了以下核心文件：

### 程序入口与配置
- `main.py`
- `cmd_arg/arg.py`
- `config/base_config.py`
- `var.py`

### 基础抽象
- `base/base_crawler.py`

### 小红书主链路
- `media_platform/xhs/core.py`
- `media_platform/xhs/client.py`
- `media_platform/xhs/login.py`
- `media_platform/xhs/playwright_sign.py`

### 抖音主链路
- `media_platform/douyin/core.py`
- `media_platform/douyin/client.py`
- `media_platform/douyin/help.py`
- `media_platform/douyin/login.py`

### 浏览器 / CDP
- `tools/cdp_browser.py`
- `tools/browser_launcher.py`

### 存储与数据模型
- `store/xhs/__init__.py`
- `store/douyin/__init__.py`
- `database/models.py`

### API
- `api/main.py`

### 项目文档
- `README.md`
- `docs/项目架构文档.md`
- `docs/项目代码结构.md`
- `docs/CDP模式使用指南.md`

## 1.2 未完全审计的范围
本报告未逐行展开所有平台、所有 Store Implementation、所有 WebUI Router、所有测试文件。  
但已经覆盖了：

- 程序骨架；
- XHS/DY 两个与我方强相关平台；
- 浏览器与签名关键链路；
- 存储与模型；
- API 暴露模式；

足以对我方第一阶段引擎设计作出架构判断。

---

# 2. 开源版整体架构复盘

## 2.1 启动路径
核心路径：

```text
main.py
→ cmd_arg.parse_cmd()
→ 全局 config 被命令行覆盖
→ CrawlerFactory.create_crawler(platform)
→ crawler.start()
→ 根据 config.CRAWLER_TYPE 分流：
   search / detail / creator
```

这个设计的优点是：
- CLI 简洁；
- 快速接不同平台；
- 学习门槛低。

缺点是：
- 全局配置被不断修改；
- 不适合多任务并发；
- 不适合服务端长期驻留；
- 无法自然表达“账号 A 正在跑任务 1，账号 B 正在跑任务 2”。

---

## 2.2 平台爬虫结构
XHS / DY 结构高度类似：

```text
Crawler
├── start()
├── search()
├── get_specified_*
├── get_creators_and_*
├── get_*_detail()
├── batch_get_comments()
├── launch_browser()
├── launch_browser_with_cdp()
└── get_media()
```

优势：
- 业务链路直观；
- 开发者容易上手。

问题：
- Crawler 同时承担：
  - 生命周期编排；
  - 浏览器创建；
  - 登录；
  - 请求任务调度；
  - 数据补采；
  - 存储调用；
  - 媒体下载触发；
- 单类职责过多；
- 很难抽象成服务级任务引擎；
- 新增 HomeFeed 后会继续膨胀。

---

# 3. 主要优点审计

## 3.1 平台模块化已成型
`media_platform/xhs` 与 `media_platform/douyin` 分离清晰，适合后续作为 Connector 设计参考。

### 我方应继承
- 平台分包；
- 平台特定解析逻辑局部化；
- 共用抽象接口。

### 我方不应照搬
- 将平台模块同时承担 Browser / Login / Client / Job / Store 全职责。

---

## 3.2 Search / Detail / Creator 三类链路已经跑通
以 XHS 为例：

- Search 获取列表；
- 获取 `note_id / xsec_token / xsec_source`；
- Detail 补齐笔记详情；
- Comments 拉评论；
- Store 落地。

以 DY 为例：

- Search 获取 `aweme_info`；
- Detail 拉作品详情；
- Comments 拉评论；
- Creator 拉主页作品。

### 我方应继承
- “发现 → 详情 → 评论”分阶段的思想；
- Detail 与 Comment 的独立任务化。

---

## 3.3 小红书详情有 API → HTML fallback
`get_note_detail_async_task()` 会先走 API 详情，再在失败时走 HTML 详情 fallback。  
这是很好的工程思路：

- 主路快；
- 旁路兜底；
- 不中断全部流程。

### 我方应继承
在 HomeFeed 场景下，详情补采也应支持：
- 主请求方案；
- 页面 fallback；
- 错误分级记录。

---

## 3.4 CDP 模式体现了“真实浏览器会话”的方向
项目提供：
- `CDP_CONNECT_EXISTING`
- 连接用户已有 Chrome；
- 浏览器上下文复用；
- Cookie 提取；
- 获取 User-Agent / localStorage。

这与我方“本地 Agent 托管员工账号会话”的方向一致。

### 我方应继承
- 真实会话优先；
- Session 与采集任务分离；
- 浏览器态只在必要时使用。

---

## 3.5 存储字段映射有借鉴价值
XHS / DY Store 已经把平台原始对象转成较规整字段。  
这些字段可直接帮助我方定义：

- `ContentSnapshot`
- `CommentSnapshot`
- `CreatorSnapshot`

---

# 4. 关键问题总览

| 编号 | 问题 | 严重级别 |
|---|---|---:|
| P0-01 | 全局可变 config 驱动，无法自然支持多任务、多账号服务化 | P0 |
| P0-02 | 无 HomeFeed 主链路 | P0 |
| P0-03 | 无任务 checkpoint / resume 正式抽象 | P0 |
| P0-04 | 无组织级内容共享去重模型 | P0 |
| P0-05 | Session 管理混入平台 Crawler，难以统一 | P0 |
| P0-06 | 批量异常可能打断整轮任务 | P0 |
| P1-01 | CDP 连接已有浏览器时默认复用第一个 context，无法表达多 profile 多账号 | P1 |
| P1-02 | CDP 失败静默 fallback 到标准模式，风险姿态变化不透明 | P1 |
| P1-03 | BrowserLauncher 使用 `0.0.0.0` remote debugging address，安全边界不适合产品化 | P1 |
| P1-04 | Douyin 参数与签名链路有多处硬编码 / 脆弱点 | P1 |
| P1-05 | XHS 签名依赖第三方库并做 monkey patch，需封装隔离 | P1 |
| P1-06 | 错误处理大量 generic Exception / sys.exit，不适合集成系统 | P1 |
| P1-07 | Store 每次调用工厂新建实例，职责与性能都不理想 | P1 |
| P2-01 | 数据表平台隔离，缺少统一 Content Identity | P2 |
| P2-02 | source_keyword 等上下文设计偏 search，不适配 feed / creator | P2 |
| P2-03 | 媒体下载耦合在 crawl path，影响主链路稳定性 | P2 |
| P2-04 | API 层更像工具控制面，而非长驻任务引擎 | P2 |

---

# 5. P0 级问题详审

## P0-01：全局可变 config 驱动，不适合多任务服务化

### 代码表现
- `cmd_arg.parse_cmd()` 直接修改全局 `config.PLATFORM / LOGIN_TYPE / CRAWLER_TYPE / ...`
- 登录类构造函数中还会再写 `config.LOGIN_TYPE = login_type`
- 搜索逻辑中还会修改 `config.CRAWLER_MAX_NOTES_COUNT`

### 架构问题
这意味着当前系统天然假设：

```text
同一时间只有一个“全局运行态”
```

而我方系统需要：

```text
任务 A：账号 xhs_001 跑 HomeFeed
任务 B：账号 dy_003 跑 CreatorMonitor
任务 C：账号 xhs_002 跑 DetailFetch
```

同时存在。

### 结论
**我方绝不能沿用全局可变 config 架构。**

### 我方要求
必须改成：
- `JobSpec`
- `AccountContext`
- `ConnectorConfig`
- `SessionContext`

都作为显式参数传递。

---

## P0-02：没有 HomeFeed 主链路

### 代码表现
`CrawlerTypeEnum` 只有：
- `search`
- `detail`
- `creator`

`config.CRAWLER_TYPE` 也只描述这三类。

### 影响
无法直接支撑我方第一阶段最重要的：
- 小红书推荐页；
- 抖音视频推荐页；
- 抖音图文推荐页；
- 50 条下滑 → 刷新 → 重复。

### 结论
**HomeFeed 必须由我方单独设计，不应硬塞进现有 search 逻辑。**

---

## P0-03：缺少任务 checkpoint / resume

### 代码表现
当前流程更接近：

```text
for keyword in keywords:
    while page:
        拉取 → 保存 → sleep
```

但没有看到完整的：
- checkpoint 持久化；
- failed item queue；
- task resume token；
- partial_success；
- job lease；
- retry budget。

### 影响
一旦任务被中断：
- 搜索页数断点不清晰；
- 评论抓取断点不清晰；
- CreatorMonitor 若被打断难以续上；
- HomeFeed 更无法稳定分轮持久化。

### 结论
**任务系统必须作为我方引擎第一等公民。**

---

## P0-04：缺少组织级内容共享去重模型

### 当前存储模式
开源版存储更像：

```text
平台原始内容表
平台评论表
平台创作者表
```

例如：
- `xhs_note`
- `douyin_aweme`

它们服务的是“采集结果落库”，而不是“组织级情报共享”。

### 我方需要
```text
content_identity
content_discovery_event
content_snapshot
comment_snapshot
fetch_job
fetch_lease
```

### 差异
- 开源版：内容是“爬虫产物”；
- 我方：内容是“共享情报资产”。

---

## P0-05：Session 管理混在平台 Crawler 内

### 代码表现
每个平台 `start()` 同时负责：
- 启动浏览器；
- 创建 page；
- 创建 client；
- 检查 login；
- 异常时登录；
- 更新 cookies；
- 然后进入业务采集。

### 影响
多账号架构会非常难做，因为：
- Session 生命周期散落在每个平台；
- 难以统一管理账号健康状态；
- 难以切换账号；
- 难以 centralize CookieBridge / SessionBridge。

### 我方要求
Session 独立成模块：

```text
SessionManager
├── SessionProvider
├── AccountHealthManager
├── CookieBridgeAdapter
├── BrowserSessionProvider
└── RequestSessionProvider
```

---

## P0-06：批量异常可能打断整轮任务

### 代码表现
在 XHS `search()` 里：
```python
note_details = await asyncio.gather(*task_list)
```

而 `get_note_detail_async_task()` 在 API 与 HTML fallback 都失败时，会抛出泛化 Exception：
```python
raise Exception(...)
```

它没有在该函数本身被完整捕获。  
这意味着单个内容失败有机会导致整批 `gather()` 传播异常，进而打断当前轮次。

### 外部现象
公开 issue 中已经出现：
- 抓取若干条后任务退出；
- 异步 Future 异常未被回收；
- `TargetClosedError` 等链式问题。

### 我方要求
必须使用：
- Item-level failure isolation；
- `return_exceptions=True` 或自建 task wrapper；
- 每个 item 写 `FetchResult(status, error_code, error_detail)`；
- 一条失败绝不打断整轮任务。

---

# 6. P1 级问题详审

## P1-01：CDP 使用第一个 Context，不支持多 Profile 多账号的明确绑定

### 代码表现
`CDPBrowserManager._create_browser_context()`：
- 如果存在 contexts，直接使用 `contexts[0]`。

### 问题
这对于研究脚本勉强可用，但对于我方场景不行。

我方必须表达：
```text
account_id A → session/profile A → browser context A
account_id B → session/profile B → browser context B
```

否则九个账号管理会混乱。

### 我方要求
- 不依赖“第一个 context”；
- 必须有显式 `account_session_id`;
- Browser session 需可定位、可检测、可释放。

---

## P1-02：CDP 失败时静默 fallback 到标准 Playwright 模式

### 代码表现
`launch_browser_with_cdp()` 失败后：
- 记录日志；
- 直接 fallback 到标准 Playwright。

### 问题
这会悄悄改变：
- 会话来源；
- Cookie 来源；
- 环境指纹；
- 任务风险姿态；
- 采集成功率预期。

对产品系统来说，这种“无声降级”不可接受。

### 我方要求
需要显式：
```text
SESSION_CONNECT_FAILED
SESSION_FALLBACK_REQUIRES_POLICY
```

由任务策略决定是否 fallback，而不是默认自动切。

---

## P1-03：BrowserLauncher 的远程调试地址不适合产品化

### 代码表现
`--remote-debugging-address=0.0.0.0`

### 问题
从系统安全角度，远程调试端口应谨慎控制访问范围。  
我方是要在员工电脑本地跑 Collector Agent，不应默认把调试入口暴露得过宽。

### 我方要求
- 默认仅本机可访问；
- 若要跨进程通信，走 Agent 内部受控协议；
- 调试端口管理与任务权限分离。

---

## P1-04：Douyin 参数链路存在脆弱硬编码

### 观察点
在 `DouYinClient.__process_req_params()` 中：
- 浏览器参数写死大量值；
- `browser_platform = MacIntel`
- `browser_version = 125.0.0.0`
- 屏幕宽高写死；
- 其他参数也为固定模板。

在 `get_user_aweme_posts()` 中：
- `verifyFp`
- `fp`
是固定字符串。

### 问题
这些参数如果与真实浏览器上下文不一致，或者平台策略变动，将降低稳定性。

### 我方要求
- 参数构造应作为可维护的 Provider；
- 能从 SessionContext / BrowserContext 中读取的，不应硬编码；
- 平台参数模板要独立于 Connector 主业务。

---

## P1-05：XHS 签名依赖第三方库，并通过 monkey patch 修复

### 代码表现
`playwright_sign.py`：
- 使用 `xhshow`；
- 启动时 monkey-patch 其内部 `CryptoProcessor.build_payload_array`；
- 修复 GET 签名行为。

### 评价
工程上这是能跑的办法，但产品化要非常谨慎：
- monkey patch 提示该依赖与当前平台行为存在适配缝隙；
- 依赖升级可能引入新兼容问题；
- 签名逻辑不应散落在业务 Client 中。

### 我方要求
- 抽象 `SignerProvider`；
- 第三方签名库包装在单独模块；
- 对签名结果做可观测监控；
- 平台变更时只替换 signer，不改业务 Connector。

---

## P1-06：错误处理不适合集成系统

### 观察
代码中可见：
- `sys.exit()`
- `raise Exception(...)`
- CAPTCHA 直接 generic Exception
- Request 中统一抛 `DataFetchError`

### 问题
系统无法稳定区分：
- 登录失效；
- 账号验证；
- 页面结构变化；
- 资源不存在；
- 请求暂时失败；
- 签名失效；
- 参数构造异常。

### 我方要求
明确错误码体系：

```text
AUTH_REQUIRED
MANUAL_VERIFY_REQUIRED
SESSION_EXPIRED
SIGNATURE_INVALID
CONTENT_NOT_FOUND
RATE_LIMITED
STRUCTURE_CHANGED
REMOTE_BLOCKED
RETRYABLE_NETWORK_ERROR
NON_RETRYABLE_PLATFORM_ERROR
```

---

## P1-07：Store 层每次调用工厂重新 new，职责也不干净

### 代码表现
每次 `update_xhs_note()` 最后：
```python
await XhsStoreFactory.create_store().store_content(...)
```

### 问题
- 重复实例化；
- 存储选择依赖全局 config；
- Store 不像 Repository，更像过程函数；
- 难以做事务、批写、幂等、去重租约。

### 我方要求
- `Repository` 或 `StoreGateway` 常驻；
- 事务边界明确；
- Job 与 Store 关系清晰；
- 支持批量写入与幂等 upsert。

---

# 7. P2 级问题详审

## P2-01：数据库模型是平台原始表，不是统一内容资产模型
`database/models.py` 中：
- XHS 是 `XhsNote`
- DY 是 `DouyinAweme`

这对于多平台爬虫保存原数据没问题。  
但对我方“共享情报中心”不够。

### 我方需要
统一抽象：
- `ContentIdentity`
- `ContentSnapshot`
- `DiscoveryEvent`
- `CreatorIdentity`
- `CreatorContentRelation`

---

## P2-02：上下文变量设计偏 Search，不适配 HomeFeed
`var.py` 里：
- `request_keyword_var`
- `source_keyword_var`

这说明项目许多链路默认搜索为中心。  
但 HomeFeed 并没有关键词起点。

### 我方要求
上下文应改为：
- `source_surface`
- `discovery_job_id`
- `account_id`
- `session_id`

---

## P2-03：媒体下载耦合在采集主链路
在 Core 中，详情抓完后直接：
- `get_notice_media`
- `get_aweme_media`

### 问题
下载图片/视频是重活，会拖慢采集主流程。

### 我方要求
- 主采集只采结构化信息；
- 媒体下载独立任务；
- 只有素材库需要时再下载。

---

## P2-04：API 层不是正式任务引擎
`api/main.py` 显示了：
- FastAPI；
- 配置接口；
- 健康检查；
- 前端静态资源挂载。

但未体现：
- 正式任务状态机；
- Job checkpoint；
- Resume；
- Account registry；
- Content dedup；
- Fetch lease。

### 结论
开源版 WebUI 可用于工具化操作，但不能直接视为我方后台服务骨架。

---

# 8. 对 XHS 与 DY 的源码层结论

## 8.1 小红书链路结论
### 值得借鉴
- 搜索 → detail → comment 的分层；
- fallback 策略；
- `xsec_token / xsec_source` 的传递机制；
- 评论批处理；
- 媒体资源解析字段。

### 必须重构
- 签名模块隔离；
- Session 从 Crawler 中抽出；
- 单条异常隔离；
- Store 解耦；
- Feed 作为新主线。

---

## 8.2 抖音链路结论
### 值得借鉴
- 搜索 / 详情 / 创作者 / 评论全链路；
- URL 解析能力；
- 评论分页结构；
- 作品类型识别；
- 图片与视频字段提取。

### 必须重构
- 参数模板与真实 Session 解耦；
- 签名策略抽象；
- 固定 `verifyFp/fp` 类字段移除或 Provider 化；
- 错误模型改造；
- 账号状态识别独立化；
- HomeFeed 单独设计。

---

# 9. 我方应复用什么，不复用什么

## 9.1 可复用的是“思想”
| 模块 | 是否建议直接复用 | 是否建议借鉴 |
|---|---:|---:|
| CrawlerFactory | 不直接复用 | 借鉴 |
| Platform 分包 | 不直接复用 | 强烈借鉴 |
| XHS 详情/评论链路 | 局部参考 | 强烈借鉴 |
| DY 详情/评论链路 | 局部参考 | 强烈借鉴 |
| Browser/CDP 思路 | 不照搬 | 强烈借鉴 |
| Store 字段映射 | 不照搬 | 借鉴 |
| 数据库模型 | 不直接复用 | 仅作字段参考 |
| API/WebUI | 不直接复用 | 少量借鉴 |

## 9.2 不应复用的结构
1. 全局可变配置；
2. `sys.exit()` 异常策略；
3. 一体化 Crawler 巨类；
4. Store 与全局 config 耦合；
5. 任务失败缺少 checkpoint；
6. 第一 context 自动绑定账号；
7. 采集与媒体下载强耦合。

---

# 10. 对我方引擎的强制架构约束

后续 Codex 建项目时必须遵守：

## 10.1 四大核心层
```text
Session Layer
Job Layer
Connector Layer
Storage Layer
```

## 10.2 五个核心接口
```python
SessionProvider
SignerProvider
FeedConnector
DetailConnector
CommentConnector
CreatorConnector
```

## 10.3 所有任务必须任务化
不允许继续写成：
```python
main()
→ crawler.start()
→ 整体跑完
```

必须是：
```python
JobSpec
→ JobRunner
→ Step / Checkpoint
→ Result / Resume
```

## 10.4 所有异常必须结构化
禁止：
```python
raise Exception(...)
sys.exit()
```

必须：
```python
raise PlatformFetchError(
    code="SIGNATURE_INVALID",
    retryable=False,
    ...
)
```

---

# 11. 建议的源码学习顺序

Codex 或工程师继续深入时，应按以下顺序阅读：

1. `main.py`
2. `cmd_arg/arg.py`
3. `config/base_config.py`
4. `base/base_crawler.py`
5. `media_platform/xhs/core.py`
6. `media_platform/xhs/client.py`
7. `media_platform/xhs/login.py`
8. `media_platform/xhs/playwright_sign.py`
9. `media_platform/douyin/core.py`
10. `media_platform/douyin/client.py`
11. `media_platform/douyin/help.py`
12. `media_platform/douyin/login.py`
13. `tools/cdp_browser.py`
14. `tools/browser_launcher.py`
15. `store/xhs/__init__.py`
16. `store/douyin/__init__.py`
17. `database/models.py`
18. `var.py`
19. `api/main.py`

---

# 12. 最终审计结论

## 12.1 对 MediaCrawler 开源版
它是一个优秀的研究型参考项目，但不是我们的生产级引擎底座。

### 它解决得好的
- 平台适配；
- 登录与请求联动；
- 详情和评论链路；
- 多存储导出；
- 多平台快速起步。

### 它没有解决或不适合我们的
- HomeFeed 主场景；
- 多账号组织化；
- 任务恢复；
- 共享内容池；
- 服务级并发；
- 完整错误状态机；
- 前后端产品化运行时。

## 12.2 对我方
我们要做的不是“MediaCrawler 改版”，而是：

# 运营情报中心专用的 Intelligence Engine

它需要：
- 继承开源版的采集经验；
- 对标 Pro 的公开能力；
- 围绕我方 HomeFeed + 多账号共享 + 任务化架构重新设计。

---

# 13. 给 Codex 的直接指令

1. 任何新代码不得依赖全局 config 作为任务真相源。
2. 任何 Connector 都不得自行决定任务生命周期。
3. 任何 Session 都不得隐式绑定“第一个 browser context”。
4. 任何失败都必须返回结构化结果。
5. 任何内容主记录都必须先走全局去重。
6. Detail / Comment / MediaDownload 必须拆成独立任务。
7. HomeFeed 不是 Search 的变体，而是独立一等能力。
8. SignerProvider 必须是可替换模块。
9. 账号实体必须先于采集任务存在。
10. 后续引擎架构以 `intel-engine-architecture-v0.1.md` 为准。
