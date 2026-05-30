import pytest

from intelligence_engine.domain.enums import Platform
from intelligence_engine.services.task_materialization import TaskMaterializationService
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.storage.repositories.product_repository import ProductRepository
from tests.task_template_helpers import create_feed_template, materialize_for_account


def _collector_account(db_session):
    agent = AccountRepository(db_session).register_agent(
        employee_id=None,
        device_name="role-pc",
        machine_fingerprint="role-fp",
        agent_version="0.2.0",
        capabilities={"tasks": ["feed_collect"]},
    )
    return AccountRepository(db_session).create_account(
        employee_id=None,
        platform=Platform.XHS.value,
        display_name="collector",
        external_account_id=None,
        business_account_type=None,
        default_agent_id=agent.id,
        metadata={},
    )


def test_operated_account_cannot_materialize_feed_collect(db_session):
    account = _collector_account(db_session)
    account.account_role = "operated_account"
    db_session.flush()
    template = create_feed_template(db_session, account, name="推荐流", target_count=5)
    with pytest.raises(ValueError, match="cannot run"):
        materialize_for_account(db_session, template, account.id)
