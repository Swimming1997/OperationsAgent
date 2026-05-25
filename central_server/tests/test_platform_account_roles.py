import pytest

from intelligence_engine.domain.enums import Platform
from intelligence_engine.services.task_materialization import TaskMaterializationService
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.storage.repositories.product_repository import ProductRepository


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
    template = ProductRepository(db_session).create_task_template(
        name="推荐流",
        template_type="recommendation_feed_task",
        platform=Platform.XHS.value,
        account_id=account.id,
        business_account_type_id=None,
        config={"executor_account_id": account.id, "feed_type": "xhs_home_feed", "target_count": 5, "refresh_rounds": 1, "per_round_scroll_target": 5},
        enabled=True,
    )
    with pytest.raises(ValueError, match="cannot run"):
        TaskMaterializationService(db_session).materialize_template(template)
