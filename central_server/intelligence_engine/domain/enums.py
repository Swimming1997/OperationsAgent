from enum import Enum


class Platform(str, Enum):
    XHS = "xhs"
    DOUYIN = "douyin"


class UserRoleName(str, Enum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    OPERATOR = "operator"
    SALES = "sales"


class TaskTemplateType(str, Enum):
    RECOMMENDATION_FEED_TASK = "recommendation_feed_task"
    CREATOR_MONITOR_TASK = "creator_monitor_task"
    KEYWORD_SEARCH_TASK = "keyword_search_task"


class TaskScheduleType(str, Enum):
    MANUAL = "manual"
    INTERVAL_SECONDS = "interval_seconds"
    DAILY_TIME_WINDOW = "daily_time_window"


class TaskRunTriggerType(str, Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class TaskRunStatus(str, Enum):
    MATERIALIZED = "materialized"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class NetworkEgressStrategy(str, Enum):
    DIRECT_LOCAL = "direct_local"
    FIXED_PROXY_PER_ACCOUNT = "fixed_proxy_per_account"
    POOL_PROXY_FOR_ELIGIBLE_TASK = "pool_proxy_for_eligible_task"


class ContentWorkflowStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    ASSIGNED = "assigned"
    SELECTED = "selected"
    DISCARDED = "discarded"
    ARCHIVED = "archived"


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
    MANUAL_IMPORT = "manual_import"


class ContentType(str, Enum):
    IMAGE_TEXT = "image_text"
    VIDEO = "video"
    UNKNOWN = "unknown"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    NEED_LOGIN = "need_login"
    NEED_MANUAL_VERIFY = "need_manual_verify"
    DEGRADED = "degraded"
    PAUSED = "paused"
    DISABLED = "disabled"


class AuthStatus(str, Enum):
    NOT_LOGGED_IN = "not_logged_in"
    LOGIN_PENDING = "login_pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    ERROR = "error"


class LoginSessionStatus(str, Enum):
    CREATED = "created"
    WAITING_AGENT = "waiting_agent"
    LAUNCHING_BROWSER = "launching_browser"
    WAITING_USER_LOGIN = "waiting_user_login"
    CHECKING_AUTH = "checking_auth"
    LOGGED_IN = "logged_in"
    FAILED = "failed"
    EXPIRED = "expired"


class SessionStatus(str, Enum):
    READY = "ready"
    EXPIRED = "expired"
    MANUAL_VERIFY_REQUIRED = "manual_verify_required"
    UNAVAILABLE = "unavailable"


class AgentStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    RETIRED = "retired"


class JobType(str, Enum):
    FEED_COLLECT = "feed_collect"
    DETAIL_FETCH = "detail_fetch"
    COMMENT_FETCH = "comment_fetch"
    CREATOR_MONITOR = "creator_monitor"
    SEARCH_COLLECT = "search_collect"
    XHS_SEARCH_SUGGEST = "xhs_search_suggest"
    MEDIA_DOWNLOAD = "media_download"


class ContentDataStatus(str, Enum):
    CARD_ONLY = "card_only"
    DETAIL_READY = "detail_ready"
    COMMENTS_READY = "comments_ready"
    DETAIL_FAILED = "detail_failed"
    COMMENTS_FAILED = "comments_failed"


class AccountRole(str, Enum):
    INTELLIGENCE_COLLECTOR = "intelligence_collector"
    OPERATED_ACCOUNT = "operated_account"


class AccountHealthStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    COOLING_DOWN = "cooling_down"
    BLOCKED = "blocked"
    DISABLED = "disabled"


class EnqueueDetailPolicy(str, Enum):
    ALL = "all"
    CANDIDATE_ONLY = "candidate_only"
    MANUAL_ONLY = "manual_only"
    THRESHOLD_ONLY = "threshold_only"


class EnqueueCommentPolicy(str, Enum):
    ALL = "all"
    HIGH_COMMENT_ONLY = "high_comment_only"
    MANUAL_ONLY = "manual_only"
    SELECTED_ONLY = "selected_only"


class XhsSearchSort(str, Enum):
    COMPREHENSIVE = "comprehensive"
    LATEST = "latest"
    MOST_LIKED = "most_liked"
    MOST_COMMENTED = "most_commented"
    MOST_COLLECTED = "most_collected"


class XhsNoteType(str, Enum):
    ALL = "all"
    VIDEO = "video"
    IMAGE_TEXT = "image_text"


class XhsPublishTime(str, Enum):
    ALL = "all"
    ONE_DAY = "one_day"
    ONE_WEEK = "one_week"
    HALF_YEAR = "half_year"


class XhsSearchScope(str, Enum):
    ALL = "all"
    VIEWED = "viewed"
    UNVIEWED = "unviewed"
    FOLLOWED = "followed"


class XhsLocationFilter(str, Enum):
    ALL = "all"
    SAME_CITY = "same_city"
    NEARBY = "nearby"


class ReferenceLibraryType(str, Enum):
    BENCHMARK_WORK = "benchmark_work"
    LEAD_CASE = "lead_case"
    VISUAL_MATERIAL = "visual_material"


class ReferenceLibraryItemStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ReferenceLibraryRating(str, Enum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"


class ReferenceLibraryUsageStatus(str, Enum):
    UNUSED = "unused"
    USED = "used"
    ARCHIVED = "archived"


class JobStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    PARTIAL_SUCCESS = "partial_success"
    SUCCESS = "success"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class LeaseResourceType(str, Enum):
    DETAIL_FETCH = "detail_fetch"
    COMMENT_FETCH = "comment_fetch"
    CREATOR_MONITOR = "creator_monitor"


class CandidateBucket(str, Enum):
    LEAD_CANDIDATE = "lead_candidate"
    CONTENT_CANDIDATE = "content_candidate"
    PENDING_ENRICHMENT = "pending_enrichment"
    DISCARD = "discard"


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
