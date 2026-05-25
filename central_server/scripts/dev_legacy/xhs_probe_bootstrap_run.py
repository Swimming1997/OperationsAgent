# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence_engine.db.init_db import init_db
from intelligence_engine.db.models import AccountSession, Employee, LocalAgent, PlatformAccount
from intelligence_engine.db.session import SessionLocal
from intelligence_engine.domain.enums import AccountStatus, FeedType, JobType, Platform, SessionStatus
from intelligence_engine.local_agent.xhs_probe_runner import XhsProbeRunner
from intelligence_engine.storage.repositories.job_repository import JobRepository


TEST_EMPLOYEE_ID = "00000000-0000-0000-0000-00000000xhs1"
TEST_AGENT_FINGERPRINT = "xhs-probe-local-agent-9222"
TEST_ACCOUNT_EXTERNAL_ID = "xhs-probe-account-9222"


def parse_args():
    parser = argparse.ArgumentParser(description="Bootstrap local test entities and run real XHS HomeFeed probe.")
    parser.add_argument("--center-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--target-count", type=int, default=50)
    parser.add_argument("--no-post", action="store_true")
    return parser.parse_args()


def ensure_bootstrap_entities(cdp_url: str) -> tuple[str, str, str, str]:
    init_db()
    with SessionLocal() as db:
        employee = db.get(Employee, TEST_EMPLOYEE_ID)
        if not employee:
            employee = Employee(id=TEST_EMPLOYEE_ID, display_name="XHS Probe Test Employee", email="xhs-probe@example.local")
            db.add(employee)
            db.flush()

        agent = db.scalar(select(LocalAgent).where(LocalAgent.machine_fingerprint == TEST_AGENT_FINGERPRINT))
        if not agent:
            agent = LocalAgent(
                employee_id=employee.id,
                device_name="XHS Probe Local Agent",
                machine_fingerprint=TEST_AGENT_FINGERPRINT,
                status="online",
                agent_version="0.1.0",
                capabilities_json={"platforms": ["xhs"], "supports_cdp": True, "probe": "xhs_homefeed"},
            )
            db.add(agent)
            db.flush()

        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.platform == Platform.XHS.value,
                PlatformAccount.external_account_id == TEST_ACCOUNT_EXTERNAL_ID,
            )
        )
        if not account:
            account = PlatformAccount(
                employee_id=employee.id,
                platform=Platform.XHS.value,
                display_name="XHS Probe Account",
                external_account_id=TEST_ACCOUNT_EXTERNAL_ID,
                business_account_type="probe",
                status=AccountStatus.ACTIVE.value,
                default_agent_id=agent.id,
                metadata_json={"purpose": "xhs_homefeed_probe"},
            )
            db.add(account)
            db.flush()

        account_session = db.scalar(
            select(AccountSession).where(
                AccountSession.account_id == account.id,
                AccountSession.local_agent_id == agent.id,
                AccountSession.session_type == "browser",
            )
        )
        if not account_session:
            account_session = AccountSession(
                account_id=account.id,
                local_agent_id=agent.id,
                platform=Platform.XHS.value,
                session_type="browser",
                status=SessionStatus.READY.value,
                session_meta_json={"cdp_url": cdp_url},
            )
            db.add(account_session)
            db.flush()
        else:
            account_session.status = SessionStatus.READY.value
            account_session.session_meta_json = {"cdp_url": cdp_url}

        job = JobRepository(db).create_job(
            job_type=JobType.FEED_COLLECT,
            account_id=account.id,
            local_agent_id=agent.id,
            payload={
                "platform": Platform.XHS.value,
                "account_id": account.id,
                "feed_type": FeedType.XHS_HOME_FEED.value,
                "target_count": 50,
                "refresh_rounds": 1,
                "per_round_scroll_target": 50,
                "probe": True,
            },
            priority=100,
        )
        db.commit()
        return employee.id, agent.id, account.id, job.id


def summarize(result: dict, *, account_id: str, job_id: str) -> dict:
    report = result.get("report") or {}
    ingestion = result.get("ingestion") or {}
    ingestion_results = ingestion.get("results") or []
    field_success = report.get("field_success") or {}
    return {
        "account_id": account_id,
        "job_id": job_id,
        "session_status": result.get("session_status"),
        "session_message": result.get("session_message"),
        "actual_sample_count": report.get("actual_count", 0),
        "deduped_probe_count": report.get("unique_candidate_count", 0),
        "ingestion_success_count": len(ingestion_results),
        "detail_job_enqueue_count": sum(1 for item in ingestion_results if item.get("detail_job_enqueued")),
        "field_parse_rates": {
            field: {
                "count": value.get("count", 0),
                "rate": round(float(value.get("rate", 0.0)), 4),
            }
            for field, value in field_success.items()
        },
    }


async def main() -> None:
    args = parse_args()
    _employee_id, _agent_id, account_id, job_id = ensure_bootstrap_entities(args.cdp_url)
    result = await XhsProbeRunner(center_base_url=args.center_url).run(
        job_id=job_id,
        account_id=account_id,
        session_meta={"cdp_url": args.cdp_url},
        target_count=args.target_count,
        post_ingestion=not args.no_post,
    )
    print(json.dumps(summarize(result, account_id=account_id, job_id=job_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
