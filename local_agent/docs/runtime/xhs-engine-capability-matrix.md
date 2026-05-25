# XHS Engine Capability Matrix

本文件面向 Local Agent 运行时智能体。正式小红书采集执行只位于 `local_agent_runtime/connectors/xhs/`。`references/MediaCrawler` 仅用于参考接口路径、字段和错误判断，不作为运行依赖。

## 第一层：只读采集引擎，本阶段验收

| capability_key | 说明 | 当前状态 |
|---|---|---|
| xhs.login.qrcode_or_manual | 二维码 / 手机验证码 / 人工登录态维护 | 部分已有 |
| xhs.account.self_info | 获取当前登录账号信息 | 已有 query_self/pong 审计入口 |
| xhs.feed.home_recommend | 推荐流笔记 | 已有 homefeed_probe |
| xhs.search.notes | 搜索笔记 | 已有 search_probe |
| xhs.note.detail | 笔记详情 | 已有 detail_probe |
| xhs.note.comments | 一级评论 | 已有 comment_probe |
| xhs.note.sub_comments | 二级评论 | 参考 MediaCrawler 有，当前未正式做 |
| xhs.creator.profile | 作者主页信息 | 部分已有 |
| xhs.creator.posted_notes | 作者已发布笔记 | 部分已有 creator.py |
| xhs.note.media_urls | 图片 / 视频 URL | 部分已有 detail_normalizer，未验收无水印 |

## 第二层：账号资产读取，后续做

| capability_key | 说明 | 当前状态 |
|---|---|---|
| xhs.account.posted_notes | 当前账号已发布笔记 | 未正式做 |
| xhs.account.liked_notes | 当前账号点赞/喜欢笔记 | 未做 |
| xhs.account.collected_notes | 当前账号收藏笔记 | 未做 |
| xhs.creator_platform.published_list | 创作者平台已发布作品列表 | 未做 |
| xhs.search.users | 搜索用户 | 未做 |

## 第三层：动作能力，后续单独做

| capability_key | 说明 | 当前状态 |
|---|---|---|
| xhs.action.comment_publish | 发布评论 | 未做 |
| xhs.action.comment_reply | 回复评论 | 未做 |
| xhs.action.like_note | 点赞笔记 | 未做 |
| xhs.action.collect_note | 收藏笔记 | 未做 |
| xhs.action.follow_user | 关注用户 | 未做 |
| xhs.message.unread | 未读消息 | 未做 |
| xhs.message.mentions | @提醒 / 回复提醒 | 未做 |
| xhs.message.likes_collects | 点赞收藏通知 | 未做 |
| xhs.creator_platform.upload_image | 上传图文作品 | 未做 |
| xhs.creator_platform.upload_video | 上传视频作品 | 未做 |

## 归属

- `local_agent_runtime/connectors/xhs/`：正式浏览器采集、signed API client、probe、normalizer。
- `central_server/intelligence_engine/domain/xhs_context.py`：中央只保留协议上下文合并和 URL 补全工具。
- `central_server/scripts/dev_legacy/xhs_runtime_duplicate/`：历史中央 XHS runtime 副本，不属于正式路径。

## 当前真实验收状态（v2）

| capability_key | 当前状态 | 最高 severity | 说明 |
|---|---|---|---|
| xhs.login.qrcode_or_manual | pass | P4_INFO | Chrome 登录 + CDP 9222 |
| xhs.account.self_info | **pass** | P4_INFO | nickname/user_id/home_url 已从 basic_info 映射 |
| xhs.feed.home_recommend | pass | P4_INFO | 推荐流卡片含 xsec，供 smoke fallback |
| xhs.search.notes | pass | P4_INFO | 搜索 DOM 可用；xsec 常需 homefeed 补全 |
| xhs.note.detail | **pass（smoke）** | P4_INFO | API fetch_source=api |
| xhs.note.comments | **pass（smoke）** | P4_INFO | API 10 条，跳过 DOM fallback |
| xhs.engine.smoke | **pass** | P4_INFO | 闭环 self_info→search→homefeed→detail→comment |
| xhs.creator.profile / posted_notes | pass | P4_INFO | 作者页 20 卡片（上轮 creator 审计） |

**禁止**使用 MediaCrawler 过期示例 URL 验收 detail/comment；应使用 `--surface smoke` 或 search/homefeed 刚抓到的 URL。
