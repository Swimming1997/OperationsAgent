import pytest

from intelligence_engine.domain.enums import JobStatus
from intelligence_engine.jobs.state_machine import assert_transition


def test_job_state_machine_accepts_documented_flow():
    assert_transition(JobStatus.PENDING.value, JobStatus.CLAIMED)
    assert_transition(JobStatus.CLAIMED.value, JobStatus.RUNNING)
    assert_transition(JobStatus.RUNNING.value, JobStatus.SUCCESS)


def test_job_state_machine_rejects_invalid_terminal_transition():
    with pytest.raises(ValueError):
        assert_transition(JobStatus.SUCCESS.value, JobStatus.RUNNING)
