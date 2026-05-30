from __future__ import annotations

from intelligence_engine.domain.enums import Platform
from intelligence_engine.services.task_materialization import TaskMaterializationService
from intelligence_engine.storage.repositories.product_repository import ProductRepository


def ensure_business_type(repo: ProductRepository, account, *, business_type_id: str | None = None) -> str:
    if business_type_id:
        return business_type_id
    if account.business_account_type_id:
        return account.business_account_type_id
    business_type = repo.create_business_account_type(name="测试业务类型", description=None, enabled=True)
    account.business_account_type_id = business_type.id
    return business_type.id


def create_feed_template(db, account, *, business_type_id: str | None = None, name: str = "推荐流巡检", **config):
    repo = ProductRepository(db)
    bt_id = ensure_business_type(repo, account, business_type_id=business_type_id)
    payload = {
        "feed_type": "xhs_home_feed",
        "target_count": 10,
        "refresh_rounds": 1,
        "per_round_scroll_target": 10,
        **config,
    }
    payload.pop("executor_account_id", None)
    return repo.create_task_template(
        name=name,
        template_type="recommendation_feed_task",
        platform=Platform.XHS.value,
        business_account_type_id=bt_id,
        created_by_user_id=None,
        config=payload,
        enabled=True,
    )


def materialize_for_account(db, template, account_id: str) -> list[str]:
    return TaskMaterializationService(db).materialize_template(template, executor_account_id=account_id)


def run_template(client, template_id: str, account_id: str):
    return client.post(f"/api/task-templates/{template_id}/run", json={"executor_account_id": account_id})
