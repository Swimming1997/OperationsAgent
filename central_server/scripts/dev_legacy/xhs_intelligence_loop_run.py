# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence_engine.db.init_db import init_db
from intelligence_engine.db.models import AccountSession, Employee, LocalAgent, PlatformAccount
from intelligence_engine.db.session import SessionLocal
from intelligence_engine.domain.enums import AccountStatus, FeedType, JobType, Platform, SessionStatus
from intelligence_engine.local_agent.xhs_intelligence_loop_runner import XhsIntelligenceLoopRunner
from intelligence_engine.storage.repositories.job_repository import JobRepository


TEST_EMPLOYEE_ID = "00000000-0000-0000-0000-00000000xhs1"
TEST_AGENT_FINGERPRINT = "xhs-intelligence-loop-local-agent-9222"
TEST_ACCOUNT_EXTERNAL_ID = "xhs-intelligence-loop-account-9222"


def parse_args():
    parser = argparse.ArgumentParser(description="Run XHS Intelligence Filter V1 loop.")
    parser.add_argument("--center-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--target-count", type=int, default=50)
    parser.add_argument("--max-comments", type=int, default=20)
    parser.add_argument("--output", default="")
    return parser.parse_args()


def ensure_bootstrap_entities(cdp_url: str, *, target_count: int) -> tuple[str, str, str, str]:
    init_db()
    with SessionLocal() as db:
        employee = db.get(Employee, TEST_EMPLOYEE_ID)
        if not employee:
            employee = Employee(id=TEST_EMPLOYEE_ID, display_name="XHS Intelligence Loop Employee", email="xhs-intel@example.local")
            db.add(employee)
            db.flush()

        agent = db.scalar(select(LocalAgent).where(LocalAgent.machine_fingerprint == TEST_AGENT_FINGERPRINT))
        if not agent:
            agent = LocalAgent(
                employee_id=employee.id,
                device_name="XHS Intelligence Loop Agent",
                machine_fingerprint=TEST_AGENT_FINGERPRINT,
                status="online",
                agent_version="0.1.0",
                capabilities_json={"platforms": ["xhs"], "supports_cdp": True, "runner": "xhs_intelligence_loop_v1"},
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
                display_name="XHS Intelligence Loop Account",
                external_account_id=TEST_ACCOUNT_EXTERNAL_ID,
                business_account_type="probe",
                status=AccountStatus.ACTIVE.value,
                default_agent_id=agent.id,
                metadata_json={"purpose": "xhs_intelligence_loop_v1"},
            )
            db.add(account)
            db.flush()
        else:
            account.default_agent_id = agent.id
            account.status = AccountStatus.ACTIVE.value

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
                "target_count": target_count,
                "probe": True,
                "intelligence_loop_v1": True,
            },
            priority=60,
        )
        db.commit()
        return employee.id, agent.id, account.id, job.id


async def main() -> None:
    args = parse_args()
    _employee_id, _agent_id, account_id, job_id = ensure_bootstrap_entities(args.cdp_url, target_count=args.target_count)
    with SessionLocal() as db:
        result = await XhsIntelligenceLoopRunner(db=db, center_base_url=args.center_url).run(
            feed_job_id=job_id,
            account_id=account_id,
            session_meta={"cdp_url": args.cdp_url},
            target_count=args.target_count,
            max_comments=args.max_comments,
        )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
