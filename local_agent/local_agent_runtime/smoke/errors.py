from __future__ import annotations

BROWSER_START_FAILED = "browser_start_failed"
CDP_CONNECT_FAILED = "cdp_connect_failed"
PROFILE_LOCKED = "profile_locked"
LOGIN_REQUIRED = "login_required"
PAGE_LOAD_TIMEOUT = "page_load_timeout"
SELECTOR_NOT_FOUND = "selector_not_found"
DOM_EXTRACT_FAILED = "dom_extract_failed"
RATE_LIMITED_OR_BLOCKED = "rate_limited_or_blocked"
NETWORK_ERROR = "network_error"
UNKNOWN_ERROR = "unknown_error"

ALL_ERROR_CODES = {
    BROWSER_START_FAILED,
    CDP_CONNECT_FAILED,
    PROFILE_LOCKED,
    LOGIN_REQUIRED,
    PAGE_LOAD_TIMEOUT,
    SELECTOR_NOT_FOUND,
    DOM_EXTRACT_FAILED,
    RATE_LIMITED_OR_BLOCKED,
    NETWORK_ERROR,
    UNKNOWN_ERROR,
}
