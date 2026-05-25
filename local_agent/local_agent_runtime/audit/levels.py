from __future__ import annotations

from enum import Enum


class AuditSeverity(str, Enum):
    P0_FATAL = "P0_FATAL"
    P1_BLOCKER = "P1_BLOCKER"
    P2_MAJOR = "P2_MAJOR"
    P3_MINOR = "P3_MINOR"
    P4_INFO = "P4_INFO"


ISSUE_CODES = {
    "session_not_ready",
    "login_required",
    "manual_verify_required",
    "missing_xsec_context",
    "api_signature_failed",
    "api_http_failed",
    "dom_structure_changed",
    "field_coverage_low",
    "field_mismatch",
    "normalization_empty",
    "comment_surface_unavailable",
    "creator_surface_unavailable",
    "media_url_missing",
    "performance_slow",
    "fallback_used",
}


def highest_severity(values: list[AuditSeverity]) -> AuditSeverity:
    order = {value: index for index, value in enumerate(AuditSeverity)}
    if not values:
        return AuditSeverity.P4_INFO
    return min(values, key=lambda item: order[item])
