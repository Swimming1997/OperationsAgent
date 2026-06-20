from __future__ import annotations

from dataclasses import dataclass

from shared_contracts.enums import ErrorCode


@dataclass(frozen=True)
class FailurePolicy:
    category: str
    retryable: bool
    account_health: str
    default_backoff_class: str


_POLICIES: dict[str, FailurePolicy] = {
    ErrorCode.AUTH_REQUIRED.value: FailurePolicy("authentication", False, "blocked", "manual"),
    ErrorCode.MANUAL_VERIFY_REQUIRED.value: FailurePolicy("risk_control", True, "manual_verification", "long"),
    ErrorCode.SESSION_EXPIRED.value: FailurePolicy("authentication", True, "degraded", "medium"),
    ErrorCode.SESSION_CONNECT_FAILED.value: FailurePolicy("session", True, "degraded", "short"),
    ErrorCode.SIGNATURE_INVALID.value: FailurePolicy("risk_control", True, "cooling_down", "long"),
    ErrorCode.CONTENT_NOT_FOUND.value: FailurePolicy("content", False, "healthy", "none"),
    ErrorCode.CREATOR_NOT_FOUND.value: FailurePolicy("content", False, "healthy", "none"),
    ErrorCode.COMMENT_SURFACE_UNAVAILABLE.value: FailurePolicy("surface", False, "healthy", "none"),
    ErrorCode.MISSING_XSEC_CONTEXT.value: FailurePolicy("context", False, "healthy", "none"),
    ErrorCode.REMOTE_BLOCKED.value: FailurePolicy("risk_control", True, "cooling_down", "long"),
    ErrorCode.RATE_LIMITED.value: FailurePolicy("risk_control", True, "cooling_down", "medium"),
    ErrorCode.STRUCTURE_CHANGED.value: FailurePolicy("platform_structure", False, "degraded", "none"),
    ErrorCode.RETRYABLE_NETWORK_ERROR.value: FailurePolicy("network", True, "degraded", "short"),
    ErrorCode.NON_RETRYABLE_PLATFORM_ERROR.value: FailurePolicy("platform", False, "degraded", "none"),
    ErrorCode.INTERNAL_ENGINE_ERROR.value: FailurePolicy("internal", True, "degraded", "short"),
    "job_execution_timeout": FailurePolicy("timeout", True, "degraded", "short"),
}

_FALLBACK = FailurePolicy("unknown", False, "degraded", "none")


def classify_failure(error_code: ErrorCode | str) -> FailurePolicy:
    value = getattr(error_code, "value", error_code)
    return _POLICIES.get(str(value), _FALLBACK)

