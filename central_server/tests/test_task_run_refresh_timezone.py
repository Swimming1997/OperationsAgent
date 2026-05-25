from datetime import datetime, timezone

from intelligence_engine.db.models import Job, utcnow
from intelligence_engine.domain.enums import JobStatus, JobType
from intelligence_engine.services.task_materialization import _latest_finished_at


def test_latest_finished_at_handles_naive_and_aware_datetimes():
    jobs = [
        Job(
            job_type=JobType.COMMENT_FETCH.value,
            status=JobStatus.SUCCESS.value,
            payload_json={},
            finished_at=datetime(2026, 5, 19, 14, 29, 7),
        ),
        Job(
            job_type=JobType.DETAIL_FETCH.value,
            status=JobStatus.SUCCESS.value,
            payload_json={},
            finished_at=datetime(2026, 5, 19, 15, 0, 0, tzinfo=timezone.utc),
        ),
    ]
    result = _latest_finished_at(jobs)
    assert result.tzinfo is not None
    assert result >= datetime(2026, 5, 19, 15, 0, 0, tzinfo=timezone.utc)


def test_latest_finished_at_defaults_to_utcnow_when_missing():
    jobs = [Job(job_type=JobType.FEED_COLLECT.value, status=JobStatus.SUCCESS.value, payload_json={})]
    result = _latest_finished_at(jobs)
    assert result.tzinfo is not None
    assert result <= utcnow()
