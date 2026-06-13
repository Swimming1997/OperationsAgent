from intelligence_engine.domain.enums import JobStatus, JobType
from intelligence_engine.storage.repositories.job_repository import JobRepository
from scripts.xhs_slo_report import build_report


def test_xhs_slo_report_builds_job_type_summary(db_session):
    repo = JobRepository(db_session)
    job = repo.create_job(job_type=JobType.DETAIL_FETCH, payload={"content_id": "c1"})
    job.status = JobStatus.SUCCESS.value
    db_session.commit()

    report = build_report(window_hours=24, session=db_session)
    detail = next(item for item in report["job_types"] if item["job_type"] == JobType.DETAIL_FETCH.value)
    assert detail["terminal_total"] >= 1
    assert detail["success_total"] >= 1
    assert detail["real_terminal_total"] >= 1


def test_xhs_slo_report_separates_fixture_jobs(db_session):
    repo = JobRepository(db_session)
    fixture = repo.create_job(job_type=JobType.FEED_COLLECT, payload={"fixture": True})
    fixture.status = JobStatus.SUCCESS.value
    real = repo.create_job(job_type=JobType.FEED_COLLECT, payload={"fixture": False})
    real.status = JobStatus.FAILED.value
    real.last_error_code = "manual_verify_required"
    db_session.commit()

    report = build_report(window_hours=24, session=db_session)
    feed = next(item for item in report["job_types"] if item["job_type"] == JobType.FEED_COLLECT.value)

    assert feed["fixture_terminal_total"] == 1
    assert feed["real_terminal_total"] == 1
    assert feed["error_code_counts"]["manual_verify_required"] == 1
