from __future__ import annotations

from typing import Any

from local_agent_runtime.audit.levels import AuditSeverity


def engine_audit_summary(
    *,
    capability_key: str,
    surface: str,
    report: dict[str, Any] | None = None,
    severity: AuditSeverity = AuditSeverity.P4_INFO,
    issue_codes: list[str] | None = None,
) -> dict[str, Any]:
    report = report or {}
    perf = report.get("perf") if isinstance(report.get("perf"), dict) else {}
    field_report = report.get("field_coverage") if isinstance(report.get("field_coverage"), dict) else {}
    return {
        "severity": severity.value,
        "capability_key": capability_key,
        "surface": surface,
        "source_path": report.get("source_path") or report.get("implementation_basis") or report.get("source"),
        "field_coverage": field_report,
        "perf": {
            key: value
            for key, value in perf.items()
            if key in {"total_ms", "items_per_second", "api_ms", "page_goto_ms", "scroll_ms", "normalize_ms"}
        },
        "issue_codes": issue_codes or [],
    }
