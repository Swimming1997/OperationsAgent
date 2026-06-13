"""Douyin web URL patterns and intercept-target API paths.

Reference (study only, not a runtime dependency):
``references/MediaCrawler/media_platform/douyin/client.py`` and ``field.py``.
We do NOT call these endpoints with our own signature; we let the logged-in
page issue them and intercept the responses, matching on these path fragments.
"""

from __future__ import annotations

from urllib.parse import quote

DOUYIN_HOST = "https://www.douyin.com"

# Web page URLs a human would visit.
HOME_URL = f"{DOUYIN_HOST}/"
# The "精选" discover feed is a waterfall of recommended videos that paginates
# on scroll via the module/feed XHR — this is our recommend-feed surface.
RECOMMEND_URL = f"{DOUYIN_HOST}/jingxuan"


# Canonical filter value → Douyin web search URL params. Sort/publish_time are
# stable, well-known params the page reflects into its (signed) search request,
# so we apply them via URL and let the page sign — the most robust path.
SORT_TYPE_PARAM = {"comprehensive": "0", "most_liked": "1", "latest": "2"}
PUBLISH_TIME_PARAM = {"all": "0", "one_day": "1", "one_week": "7", "half_year": "180"}
DURATION_PARAM = {"all": "", "under_1m": "0-1", "1m_to_5m": "1-5", "over_5m": "5-10000"}


def build_search_url(
    keyword: str,
    *,
    sort: str = "comprehensive",
    publish_time: str = "all",
    duration: str = "all",
) -> str:
    params = ["type=general"]
    sort_type = SORT_TYPE_PARAM.get(sort, "0")
    if sort_type != "0":
        params.append(f"sort_type={sort_type}")
    pub = PUBLISH_TIME_PARAM.get(publish_time, "0")
    if pub != "0":
        params.append(f"publish_time={pub}")
    dur = DURATION_PARAM.get(duration, "")
    if dur:
        params.append(f"filter_duration={dur}")
    return f"{DOUYIN_HOST}/search/{quote(keyword)}?{'&'.join(params)}"


def supported_url_filters() -> dict[str, list[str]]:
    """Canonical filter values Douyin can apply via search URL params."""
    return {
        "sort": list(SORT_TYPE_PARAM.keys()),
        "publish_time": list(PUBLISH_TIME_PARAM.keys()),
        "duration": [v for v in DURATION_PARAM.keys()],
    }


def build_video_url(aweme_id: str) -> str:
    return f"{DOUYIN_HOST}/video/{aweme_id}"


def build_user_url(sec_uid: str) -> str:
    return f"{DOUYIN_HOST}/user/{sec_uid}"


# Response-interception path fragments (substring match on response URL).
# Search responses are an app-framed JSON stream at .../search/stream/ (older
# builds used .../search/single/); match the common prefix to cover both.
SEARCH_RESPONSE_PATH = "/aweme/v1/web/general/search/"
# Long-tail keyword (search box autocomplete) endpoint. Plain JSON (not a stream).
# Served from www-hj.douyin.com; match on the path fragment only.
SUG_RESPONSE_PATH = "/aweme/v1/web/search/sug/"
DETAIL_RESPONSE_PATH = "/aweme/v1/web/aweme/detail/"
COMMENT_RESPONSE_PATH = "/aweme/v1/web/comment/list/"
SUB_COMMENT_RESPONSE_PATH = "/aweme/v1/web/comment/list/reply/"
USER_POSTS_RESPONSE_PATH = "/aweme/v1/web/aweme/post/"
# The recommend feed XHR. The 精选 waterfall paginates via module/feed (count=20
# per page) returning plain JSON with an ``aweme_list``. Match without the API
# version so both v1/v2 builds are covered (observed live: v2 module/feed).
FEED_RESPONSE_PATHS = (
    "/web/tab/feed/",
    "/web/module/feed/",
)

# Search box input selectors (first match wins), used to type a seed keyword
# and trigger the autocomplete (sug) request.
SEARCHBAR_INPUT_SELECTORS = (
    "input[data-e2e='searchbar-input']",
    "input[placeholder*='搜索']",
    "input[type='text']",
    "input",
)

# Login-state signals (no signing required to read these).
LOCAL_STORAGE_LOGIN_KEY = "HasUserLogin"
LOGIN_STATUS_COOKIE = "LOGIN_STATUS"
LOGIN_PANEL_SELECTOR = "#login-panel-new"
CAPTCHA_IMAGE_SELECTOR = "#captcha-verify-image"
CAPTCHA_PAGE_MARKERS = ("验证码中间页", "captcha")
