# XHS 采集链路与 MediaCrawler 源码对照收敛报告

## 0. 结论

这次评论探针失败的根因，不是“小红书网页端评论不可取”，而是我方 XHS 链路此前**没有内化 MediaCrawler 已验证的小红书上下文协议**：

- 小红书详情/评论链路并不是只靠 `note_id`；
- 至少在 MediaCrawler 的成熟实现中，指定笔记链路会显式保留：
  - `note_id`
  - `xsec_token`
  - `xsec_source`
- Detail Fetch 使用 `note_id + xsec_source + xsec_token`；
- Comment Fetch 使用 `note_id + xsec_token`。

而我方原始实现中：
- 全项目 Python 源码没有任何 `xsec_token / xsec_source` 传递；
- HomeFeed 虽然可能拿到带 query 的 URL，但没有把这些参数建模为平台上下文；
- Detail Job / Comment Job 没有携带小红书上下文；
- 手动评论探针只传 bare URL 时，会把缺 token 的失败误判为 `comment_surface_unavailable`。

本次已将这一协议**内化为我方项目的 `platform_context` 机制**，而不是简单在某个脚本里补一段参数。

---

## 1. 对照 MediaCrawler 得出的关键事实

### 1.1 URL 解析
MediaCrawler 的 XHS `help.py` 中有明确的 `parse_note_info_from_note_url()`，从完整 URL 提取：
- note_id
- xsec_token
- xsec_source

### 1.2 Detail Fetch
MediaCrawler 的 XHS `client.py` 中：
- `get_note_by_id(note_id, xsec_source, xsec_token)`
- 请求 `/api/sns/web/v1/feed`

### 1.3 Comment Fetch
MediaCrawler 的 XHS `client.py` 中：
- `get_note_comments(note_id, xsec_token, cursor="")`
- 请求 `/api/sns/web/v2/comment/page`

### 1.4 调用链
MediaCrawler 的 XHS `core.py` 中：
- 指定笔记抓取时明确注释：必须有 `note_id / xsec_source / xsec_token`
- 评论抓取时批量传入 `note_ids + xsec_tokens`

---

## 2. 我方原始实现的偏差

| 维度 | MediaCrawler 成熟做法 | 我方原始实现 |
|---|---|---|
| URL 解析 | 显式解析 xsec 参数 | 仅提 note_id |
| Feed 候选 | 保留来源参数 | 未显式建模 |
| Detail Job | 需要 xsec 上下文 | 只带 content_id / platform_content_id |
| Comment Job | 需要 xsec 上下文 | 只带 content_id / canonical_url |
| 手动 URL Probe | 完整 URL 更可靠 | bare URL 也直接尝试 |
| 错误判断 | 参数不足应单独识别 | 误判为 surface unavailable |

---

## 3. 本次已完成的代码收敛

### 3.1 新增 `XHS platform_context`
新增模块：

- `intelligence_engine/connectors/xhs/context.py`

提供：
- `XhsNoteContext`
- `parse_xhs_note_context()`
- `context_from_url_and_raw()`
- `merge_xhs_context()`
- `build_xhs_note_url()`
- `prefer_richer_xhs_url()`

### 3.2 FeedCandidate 显式携带平台上下文
`FeedCandidateInput` 新增：
- `platform_context: dict`

XHS HomeFeed normalizer 会从 URL 中解析并保存：
- `note_id`
- `xsec_token`
- `xsec_source`
- `has_xsec_context`

### 3.3 ContentIdentity 记录平台上下文
`ContentRepository`：
- 在 `metadata_json.platform_context` 中保存 XHS 上下文；
- 若已有内容 URL 缺 token，但新发现的 URL 有 token，会优先更新为更完整 URL。

### 3.4 Detail Job / Comment Job 传递平台上下文
- Detail Job payload 新增：
  - `canonical_url`
  - `platform_context`
- Detail Ingestion 生成 Comment Job 时，也传递：
  - `canonical_url`
  - `platform_context`

### 3.5 Detail / Comment Probe 使用平台上下文重建 URL
- `XhsDetailProbe`
- `XhsCommentProbe`

都会基于上下文重建更完整 URL，避免中途丢失 query。

### 3.6 手动评论探针不再接收“半残 URL”
`xhs_manual_comment_probe_run.py`：
- 完整 URL 可创建 Probe；
- 缺少 `xsec_token/xsec_source` 的 URL 会报：
  - `missing_xsec_context`
- 不再把缺上下文误判成：
  - `comment_surface_unavailable`

### 3.7 新错误码
新增：
- `missing_xsec_context`

用于明确表达：
> 这是参数上下文不足，不是网页端不可浏览。

### 3.8 顺手修复一处真实 bug
`XhsCommentProbe.fetch_comments_result()` 原实现中：
- 当 `comments >= limit` 时返回了 `list[comments]`
- 但函数声明与调用方都期望 `XhsCommentFetchResult`

这会在某些真实评论拿到较多时造成运行期结构错误。  
本次已修正为始终返回 `XhsCommentFetchResult`。

---

## 4. 新增测试

新增：
- `tests/test_xhs_context_alignment.py`

覆盖：
1. 完整 URL 解析 note_id / xsec_token / xsec_source；
2. 基于 context 重建 XHS URL；
3. FeedCandidate 保留 context；
4. Feed Candidate → Detail Job 传递 context；
5. Detail Ingestion → Comment Job 传递 context；
6. Comment Probe 缺 context 时显式返回 `missing_xsec_context`。

---

## 5. 目前仍然没有做的事

本次改造的目标是：
> 先把参数协议与跨任务传递机制修正到与成熟链路一致。

还没有做：
1. 将 MediaCrawler 的 XHS API Client 完整移植进我方项目；
2. 将 Detail / Comment 改成严格的“API-first + browser fallback”正式生产链路；
3. 签名服务 Provider 的完整实现；
4. 小红书评论 API 的真实 signed request 验证。

这些属于下一阶段，不应该在“参数协议未校准”前仓促推进。

---

## 6. 下一步建议

下一步不再让 Codex继续猜。

应当先用本次改造后的代码做一次真实验证：

### 验证 1：手动完整 URL 评论探针
传入浏览器地址栏中的**完整 URL**，包括：
- `xsec_token`
- `xsec_source`

观察：
- 是否拿到真实评论；
- comment_snapshot_count；
- 字段解析率；
- keyword_hits。

### 验证 2：重新跑一轮 HomeFeed → Detail → Comment
确认：
- Feed 中采到的 URL 是否带 xsec 上下文；
- Detail Job 是否带 context；
- Comment Job 是否带 context；
- 评论链路是否真正从推荐流上下文自然打通。

---

## 7. 设计判断

这次改造不是“贴补丁”，而是把 MediaCrawler 已验证的小红书链路经验，内化为我方引擎里的：

# 平台上下文协议（platform_context）

后续抖音也应该遵循同一个设计思想：

- 平台上下文不要散落在脚本里；
- 从内容发现阶段就保留；
- 在后续 detail/comment/creator job 中持续传递；
- 缺少上下文要显式报错，不要误判业务表面状态。
