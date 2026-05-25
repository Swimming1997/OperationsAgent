from __future__ import annotations

from intelligence_engine.domain.enums import TaskRunTriggerType


class JobPriority:
    """Lower numeric value = higher claim priority."""

    MANUAL_TASK_RUN = 10
    SCHEDULED_TASK_RUN = 30
    INGESTION_ENRICHMENT = 80
    DEFAULT = 100
    DEBUG_PROBE = 150
    LEGACY_BACKLOG = 200


def priority_for_task_run_trigger(trigger_type: TaskRunTriggerType | str) -> int:
    value = getattr(trigger_type, "value", trigger_type)
    if value == TaskRunTriggerType.MANUAL.value:
        return JobPriority.MANUAL_TASK_RUN
    if value == TaskRunTriggerType.SCHEDULED.value:
        return JobPriority.SCHEDULED_TASK_RUN
    return JobPriority.DEFAULT


def is_legacy_test_job_payload(payload: dict | None) -> bool:
    if not payload:
        return True
    markers = (
        "probe",
        "runner",
        "smoke",
        "debug",
        "intelligence_loop",
        "manual_comment_probe",
    )
    lowered = {str(key).lower() for key in payload.keys()}
    if lowered & {"probe", "runner", "smoke", "debug"}:
        return True
    for value in payload.values():
        if isinstance(value, str) and any(marker in value.lower() for marker in markers):
            return True
    return False
