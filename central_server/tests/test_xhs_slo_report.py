from intelligence_engine.domain.enums import JobStatus, JobType
from intelligence_engine.storage.repositories.job_repository import JobRepository
from scripts.xhs_slo_report import build_report


def test_xhs_slo_report_builds_job_type_summary(db_session):
    repo = JobRepository(db_session)
    job = repo.create_job(job_type=JobType.DETAIL_FETCH, payload={"content_id": "c1"})
    job.status = JobStatus.SUCCESS.value
    db_session.commit()

    report = build_report(window_hours=24)
    detail = next(item for item in report["job_types"] if item["job_type"] == JobType.DETAIL_FETCH.value)
    assert detail["terminal_total"] >= 1
    assert detail["success_total"] >= 1
