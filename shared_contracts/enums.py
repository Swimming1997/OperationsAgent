from enum import Enum


class Platform(str, Enum):
    XHS = "xhs"
    DOUYIN = "douyin"


class FeedType(str, Enum):
    XHS_HOME_FEED = "xhs_home_feed"
    DOUYIN_VIDEO_HOME_FEED = "douyin_video_home_feed"
    DOUYIN_IMAGE_HOME_FEED = "douyin_image_home_feed"


class SourceSurface(str, Enum):
    XHS_HOME_FEED = "xhs_home_feed"
    DOUYIN_VIDEO_HOME_FEED = "douyin_video_home_feed"
    DOUYIN_IMAGE_HOME_FEED = "douyin_image_home_feed"
    SEARCH = "search"
    CREATOR_MONITOR = "creator_monitor"
    ACCOUNT_POSTED_NOTES = "account_posted_notes"
    MANUAL_IMPORT = "manual_import"


class ContentType(str, Enum):
    IMAGE_TEXT = "image_text"
    VIDEO = "video"
    UNKNOWN = "unknown"


class SessionStatus(str, Enum):
    READY = "ready"
    EXPIRED = "expired"
    MANUAL_VERIFY_REQUIRED = "manual_verify_required"
    UNAVAILABLE = "unavailable"


class LoginSessionStatus(str, Enum):
    CREATED = "created"
    WAITING_AGENT = "waiting_agent"
    LAUNCHING_BROWSER = "launching_browser"
    WAITING_USER_LOGIN = "waiting_user_login"
    CHECKING_AUTH = "checking_auth"
    LOGGED_IN = "logged_in"
    FAILED = "failed"
    EXPIRED = "expired"


class JobType(str, Enum):
    FEED_COLLECT = "feed_collect"
    DETAIL_FETCH = "detail_fetch"
    COMMENT_FETCH = "comment_fetch"
    CREATOR_MONITOR = "creator_monitor"
    SEARCH_COLLECT = "search_collect"
    # Canonical, platform-agnostic long-tail keyword job; XHS_SEARCH_SUGGEST kept as legacy alias.
    SEARCH_SUGGEST = "search_suggest"
    XHS_ACCOUNT_POSTED_NOTES = "xhs_account_posted_notes"
    XHS_SEARCH_SUGGEST = "xhs_search_suggest"
    MEDIA_DOWNLOAD = "media_download"


class JobStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    PARTIAL_SUCCESS = "partial_success"
    SUCCESS = "success"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class ErrorCode(str, Enum):
    AUTH_REQUIRED = "auth_required"
    MANUAL_VERIFY_REQUIRED = "manual_verify_required"
    SESSION_EXPIRED = "session_expired"
    SESSION_CONNECT_FAILED = "session_connect_failed"
    SIGNATURE_INVALID = "signature_invalid"
    CONTENT_NOT_FOUND = "content_not_found"
    CREATOR_NOT_FOUND = "creator_not_found"
    COMMENT_SURFACE_UNAVAILABLE = "comment_surface_unavailable"
    MISSING_XSEC_CONTEXT = "missing_xsec_context"
    REMOTE_BLOCKED = "remote_blocked"
    RATE_LIMITED = "rate_limited"
    STRUCTURE_CHANGED = "structure_changed"
    RETRYABLE_NETWORK_ERROR = "retryable_network_error"
    NON_RETRYABLE_PLATFORM_ERROR = "non_retryable_platform_error"
    INTERNAL_ENGINE_ERROR = "internal_engine_error"
