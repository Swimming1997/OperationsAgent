from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class XhsCapabilityStatus(str, Enum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    PLANNED = "planned"
    OUT_OF_SCOPE_V1 = "out_of_scope_v1"


class XhsCapabilityLayer(str, Enum):
    READ_ONLY_ENGINE = "read_only_engine"
    ACCOUNT_ASSET_READ = "account_asset_read"
    OPERATOR_ACTION = "operator_action"


@dataclass(frozen=True)
class XhsCapabilitySpec:
    key: str
    layer: XhsCapabilityLayer
    status: XhsCapabilityStatus
    description: str
    current_impl: list[str] = field(default_factory=list)
    mediacrawler_reference: list[str] = field(default_factory=list)
    required_context: list[str] = field(default_factory=list)
    output_contract: list[str] = field(default_factory=list)
    audit_supported: bool = False
    notes: str | None = None


_CAPABILITIES: tuple[XhsCapabilitySpec, ...] = (
    XhsCapabilitySpec(
        key="xhs.login.qrcode_or_manual",
        layer=XhsCapabilityLayer.READ_ONLY_ENGINE,
        status=XhsCapabilityStatus.PARTIAL,
        description="二维码、手机验证码或人工登录态维护。",
        current_impl=["sessions/xhs_browser_session.py", "account_login_executor.py", "chrome_launcher.py"],
        required_context=["local Chrome profile", "CDP endpoint"],
        output_contract=["SessionStatus"],
        audit_supported=True,
    ),
    XhsCapabilitySpec(
        key="xhs.account.self_info",
        layer=XhsCapabilityLayer.READ_ONLY_ENGINE,
        status=XhsCapabilityStatus.PARTIAL,
        description="读取当前登录账号基础信息并判断登录态。",
        current_impl=["connectors/xhs/api_client.py::query_self", "connectors/xhs/api_client.py::pong"],
        mediacrawler_reference=["media_platform/xhs/client.py::get_self_info"],
        required_context=["cookie_str", "signed GET"],
        output_contract=["logged_in", "nickname", "user_id", "home_url"],
        audit_supported=True,
    ),
    XhsCapabilitySpec(
        key="xhs.feed.home_recommend",
        layer=XhsCapabilityLayer.READ_ONLY_ENGINE,
        status=XhsCapabilityStatus.IMPLEMENTED,
        description="采集网页推荐流可见笔记卡片。",
        current_impl=["connectors/xhs/homefeed_probe.py"],
        required_context=["ready browser session"],
        output_contract=["FeedCandidateInput"],
        audit_supported=True,
    ),
    XhsCapabilitySpec(
        key="xhs.search.notes",
        layer=XhsCapabilityLayer.READ_ONLY_ENGINE,
        status=XhsCapabilityStatus.IMPLEMENTED,
        description="按关键词采集搜索结果笔记卡片。",
        current_impl=["connectors/xhs/search_probe.py"],
        mediacrawler_reference=["/api/sns/web/v1/search/notes"],
        required_context=["keyword", "ready browser session"],
        output_contract=["FeedCandidateInput"],
        audit_supported=True,
    ),
    XhsCapabilitySpec(
        key="xhs.note.detail",
        layer=XhsCapabilityLayer.READ_ONLY_ENGINE,
        status=XhsCapabilityStatus.IMPLEMENTED,
        description="获取笔记详情快照。",
        current_impl=["connectors/xhs/detail_probe.py", "connectors/xhs/detail_normalizer.py"],
        mediacrawler_reference=["/api/sns/web/v1/feed"],
        required_context=["note_id", "xsec_token", "xsec_source"],
        output_contract=["DetailSnapshotInput"],
        audit_supported=True,
    ),
    XhsCapabilitySpec(
        key="xhs.note.comments",
        layer=XhsCapabilityLayer.READ_ONLY_ENGINE,
        status=XhsCapabilityStatus.IMPLEMENTED,
        description="获取一级评论。",
        current_impl=["connectors/xhs/comment_probe.py", "connectors/xhs/comment_normalizer.py"],
        mediacrawler_reference=["/api/sns/web/v2/comment/page"],
        required_context=["note_id", "xsec_token"],
        output_contract=["CommentSnapshotInput"],
        audit_supported=True,
    ),
    XhsCapabilitySpec(
        key="xhs.note.sub_comments",
        layer=XhsCapabilityLayer.READ_ONLY_ENGINE,
        status=XhsCapabilityStatus.PLANNED,
        description="获取二级评论。",
        mediacrawler_reference=["/api/sns/web/v2/comment/sub/page"],
        required_context=["note_id", "root_comment_id", "xsec_token"],
        output_contract=["CommentSnapshotInput"],
        audit_supported=False,
    ),
    XhsCapabilitySpec(
        key="xhs.creator.profile",
        layer=XhsCapabilityLayer.READ_ONLY_ENGINE,
        status=XhsCapabilityStatus.PARTIAL,
        description="读取作者主页可见资料。",
        current_impl=["connectors/xhs/creator.py"],
        required_context=["creator_profile_url or creator_platform_id"],
        output_contract=["creator_display_name"],
        audit_supported=True,
    ),
    XhsCapabilitySpec(
        key="xhs.creator.posted_notes",
        layer=XhsCapabilityLayer.READ_ONLY_ENGINE,
        status=XhsCapabilityStatus.PARTIAL,
        description="读取作者已发布笔记列表。",
        current_impl=["connectors/xhs/creator.py"],
        mediacrawler_reference=["/api/sns/web/v1/user_posted"],
        required_context=["creator_platform_id"],
        output_contract=["FeedCandidateInput"],
        audit_supported=True,
    ),
    XhsCapabilitySpec(
        key="xhs.note.media_urls",
        layer=XhsCapabilityLayer.READ_ONLY_ENGINE,
        status=XhsCapabilityStatus.PARTIAL,
        description="从详情中提取图片、视频 URL。",
        current_impl=["connectors/xhs/detail_normalizer.py"],
        required_context=["detail payload or DOM fallback"],
        output_contract=["image_urls", "video_url"],
        audit_supported=True,
        notes="无水印 URL 尚未完成验收。",
    ),
    XhsCapabilitySpec(
        key="xhs.account.posted_notes",
        layer=XhsCapabilityLayer.ACCOUNT_ASSET_READ,
        status=XhsCapabilityStatus.IMPLEMENTED,
        description="当前账号已发布笔记。",
        current_impl=["connectors/xhs/creator.py::fetch_current_account_posted_notes", "runtime.py::_run_account_posted_notes"],
        mediacrawler_reference=["/api/sns/web/v1/user/selfinfo", "/api/sns/web/v1/user_posted"],
        required_context=["ready browser session", "self_info.user_id"],
        output_contract=["FeedCandidateInput"],
        audit_supported=True,
    ),
    XhsCapabilitySpec(
        key="xhs.account.liked_notes",
        layer=XhsCapabilityLayer.ACCOUNT_ASSET_READ,
        status=XhsCapabilityStatus.PLANNED,
        description="当前账号点赞或喜欢笔记。",
    ),
    XhsCapabilitySpec(
        key="xhs.account.collected_notes",
        layer=XhsCapabilityLayer.ACCOUNT_ASSET_READ,
        status=XhsCapabilityStatus.PLANNED,
        description="当前账号收藏笔记。",
    ),
    XhsCapabilitySpec(
        key="xhs.creator_platform.published_list",
        layer=XhsCapabilityLayer.ACCOUNT_ASSET_READ,
        status=XhsCapabilityStatus.PLANNED,
        description="创作者平台已发布作品列表。",
    ),
    XhsCapabilitySpec(
        key="xhs.search.users",
        layer=XhsCapabilityLayer.ACCOUNT_ASSET_READ,
        status=XhsCapabilityStatus.PLANNED,
        description="搜索用户。",
    ),
    XhsCapabilitySpec(
        key="xhs.action.comment_publish",
        layer=XhsCapabilityLayer.OPERATOR_ACTION,
        status=XhsCapabilityStatus.OUT_OF_SCOPE_V1,
        description="发布评论。",
    ),
    XhsCapabilitySpec(
        key="xhs.action.comment_reply",
        layer=XhsCapabilityLayer.OPERATOR_ACTION,
        status=XhsCapabilityStatus.OUT_OF_SCOPE_V1,
        description="回复评论。",
    ),
    XhsCapabilitySpec(
        key="xhs.action.like_note",
        layer=XhsCapabilityLayer.OPERATOR_ACTION,
        status=XhsCapabilityStatus.OUT_OF_SCOPE_V1,
        description="点赞笔记。",
    ),
    XhsCapabilitySpec(
        key="xhs.action.collect_note",
        layer=XhsCapabilityLayer.OPERATOR_ACTION,
        status=XhsCapabilityStatus.OUT_OF_SCOPE_V1,
        description="收藏笔记。",
    ),
    XhsCapabilitySpec(
        key="xhs.action.follow_user",
        layer=XhsCapabilityLayer.OPERATOR_ACTION,
        status=XhsCapabilityStatus.OUT_OF_SCOPE_V1,
        description="关注用户。",
    ),
    XhsCapabilitySpec(
        key="xhs.message.unread",
        layer=XhsCapabilityLayer.OPERATOR_ACTION,
        status=XhsCapabilityStatus.OUT_OF_SCOPE_V1,
        description="未读消息。",
    ),
    XhsCapabilitySpec(
        key="xhs.message.mentions",
        layer=XhsCapabilityLayer.OPERATOR_ACTION,
        status=XhsCapabilityStatus.OUT_OF_SCOPE_V1,
        description="@提醒或回复提醒。",
    ),
    XhsCapabilitySpec(
        key="xhs.message.likes_collects",
        layer=XhsCapabilityLayer.OPERATOR_ACTION,
        status=XhsCapabilityStatus.OUT_OF_SCOPE_V1,
        description="点赞收藏通知。",
    ),
    XhsCapabilitySpec(
        key="xhs.creator_platform.upload_image",
        layer=XhsCapabilityLayer.OPERATOR_ACTION,
        status=XhsCapabilityStatus.OUT_OF_SCOPE_V1,
        description="上传图文作品。",
    ),
    XhsCapabilitySpec(
        key="xhs.creator_platform.upload_video",
        layer=XhsCapabilityLayer.OPERATOR_ACTION,
        status=XhsCapabilityStatus.OUT_OF_SCOPE_V1,
        description="上传视频作品。",
    ),
)

_BY_KEY = {item.key: item for item in _CAPABILITIES}


def list_xhs_capabilities(layer: str | None = None) -> list[XhsCapabilitySpec]:
    if not layer:
        return list(_CAPABILITIES)
    layer_value = XhsCapabilityLayer(layer)
    return [item for item in _CAPABILITIES if item.layer == layer_value]


def get_xhs_capability(key: str) -> XhsCapabilitySpec:
    try:
        return _BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"unknown XHS capability: {key}") from exc
