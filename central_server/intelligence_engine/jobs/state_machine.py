from intelligence_engine.domain.enums import JobStatus


ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING: {JobStatus.CLAIMED, JobStatus.PAUSED, JobStatus.CANCELLED},
    JobStatus.CLAIMED: {JobStatus.RUNNING, JobStatus.PENDING, JobStatus.FAILED, JobStatus.PAUSED},
    JobStatus.RUNNING: {
        JobStatus.SUCCESS,
        JobStatus.PARTIAL_SUCCESS,
        JobStatus.FAILED,
        JobStatus.PAUSED,
        JobStatus.CANCELLED,
    },
    JobStatus.PAUSED: {JobStatus.PENDING, JobStatus.CANCELLED},
    JobStatus.FAILED: {JobStatus.PENDING},
    JobStatus.PARTIAL_SUCCESS: {JobStatus.PENDING},
    JobStatus.SUCCESS: set(),
    JobStatus.CANCELLED: set(),
}


def assert_transition(current: str, target: JobStatus) -> None:
    current_status = JobStatus(current)
    if target not in ALLOWED_TRANSITIONS[current_status]:
        raise ValueError(f"invalid job status transition: {current_status.value} -> {target.value}")
