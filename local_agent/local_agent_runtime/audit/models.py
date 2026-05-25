from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from local_agent_runtime.audit.levels import AuditSeverity, highest_severity


@dataclass(frozen=True)
class EngineAuditIssue:
    severity: AuditSeverity
    capability_key: str
    surface: str
    code: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    suggested_action: str | None = None


@dataclass(frozen=True)
class FieldCoverage:
    fields: dict[str, float] = field(default_factory=dict)

    @property
    def average(self) -> float:
        if not self.fields:
            return 0.0
        return sum(self.fields.values()) / len(self.fields)


@dataclass(frozen=True)
class FieldCompareResult:
    field: str
    matched: bool
    expected: Any = None
    actual: Any = None
    reason: str | None = None


@dataclass(frozen=True)
class PerfStage:
    name: str
    duration_ms: float


@dataclass(frozen=True)
class EngineAuditRecord:
    capability_key: str
    surface: str
    status: str
    severity: AuditSeverity = AuditSeverity.P4_INFO
    items_seen: int = 0
    normalized_items: int = 0
    field_coverage: dict[str, float] = field(default_factory=dict)
    perf: dict[str, float] = field(default_factory=dict)
    issues: list[EngineAuditIssue] = field(default_factory=list)
    source_path: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    account_summary: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "capability_key": self.capability_key,
            "surface": self.surface,
            "status": self.status,
            "severity": self.severity.value,
            "items_seen": self.items_seen,
            "normalized_items": self.normalized_items,
            "field_coverage": self.field_coverage,
            "perf": self.perf,
            "issues": [
                {
                    "severity": issue.severity.value,
                    "capability_key": issue.capability_key,
                    "surface": issue.surface,
                    "code": issue.code,
                    "message": issue.message,
                    "evidence": issue.evidence,
                    "suggested_action": issue.suggested_action,
                }
                for issue in self.issues
            ],
            "source_path": self.source_path,
            "payload": self.payload,
        }
        if self.account_summary is not None:
            result["account_summary"] = self.account_summary
        return result


@dataclass(frozen=True)
class EngineAuditRunSummary:
    run_id: str
    records: list[EngineAuditRecord]
    total_ms: float
    artifacts: dict[str, str] = field(default_factory=dict)

    @property
    def severity(self) -> AuditSeverity:
        severities = [record.severity for record in self.records] + [issue.severity for record in self.records for issue in record.issues]
        return highest_severity(severities)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "run_id": self.run_id,
            "severity": self.severity.value,
            "total_ms": self.total_ms,
            "surface_count": len(self.records),
            "records": [record.to_dict() for record in self.records],
        }
        if self.artifacts:
            payload["artifacts"] = self.artifacts
        for record in self.records:
            if record.surface == "self_info" and record.account_summary:
                payload["self_info"] = record.account_summary
                break
        return payload
