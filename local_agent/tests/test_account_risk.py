import asyncio

import pytest

from local_agent_runtime.engine.account_risk import (
    AccountRiskBudgetExceeded,
    AccountRiskController,
    AccountRiskPolicy,
)
from local_agent_runtime.enums import ErrorCode


class FakeTime:
    def __init__(self, value: float = 1_750_000_000.0):
        self.value = value
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


def test_daily_budget_persists_across_controller_restart(tmp_path):
    state_path = tmp_path / "risk.db"
    policy = AccountRiskPolicy(min_interval_seconds=0, daily_job_budget=2)
    first = AccountRiskController(state_path, default_policy=policy)

    asyncio.run(first.before_job("account-1"))
    asyncio.run(first.before_job("account-1"))

    restarted = AccountRiskController(state_path, default_policy=policy)
    with pytest.raises(AccountRiskBudgetExceeded) as exc_info:
        asyncio.run(restarted.before_job("account-1"))
    assert exc_info.value.decision.jobs_used_today == 2
    assert restarted.health_snapshot()["account-1"]["health_status"] == "budget_exhausted"


def test_success_enforces_minimum_interval_before_next_job(tmp_path):
    fake_time = FakeTime()
    controller = AccountRiskController(
        tmp_path / "risk.db",
        default_policy=AccountRiskPolicy(min_interval_seconds=5),
        clock=fake_time.now,
        sleeper=fake_time.sleep,
    )

    asyncio.run(controller.before_job("account-1"))
    controller.record_success("account-1")
    decision = asyncio.run(controller.before_job("account-1"))

    assert decision.waited_seconds == 5
    assert fake_time.sleeps == [5]


def test_retryable_failures_apply_exponential_backoff_and_health(tmp_path):
    fake_time = FakeTime()
    controller = AccountRiskController(
        tmp_path / "risk.db",
        default_policy=AccountRiskPolicy(
            min_interval_seconds=0,
            failure_backoff_base_seconds=10,
            failure_backoff_max_seconds=60,
        ),
        clock=fake_time.now,
        sleeper=fake_time.sleep,
    )

    asyncio.run(controller.before_job("account-1"))
    controller.record_failure(
        "account-1",
        error_code=ErrorCode.RETRYABLE_NETWORK_ERROR,
        retryable=True,
    )
    assert controller.health_snapshot()["account-1"]["health_status"] == "cooling_down"
    asyncio.run(controller.before_job("account-1"))
    assert fake_time.sleeps == [10]

    controller.record_failure(
        "account-1",
        error_code=ErrorCode.RATE_LIMITED,
        retryable=True,
    )
    asyncio.run(controller.before_job("account-1"))
    assert fake_time.sleeps == [10, 20]


def test_manual_verification_uses_long_cooldown(tmp_path):
    fake_time = FakeTime()
    controller = AccountRiskController(
        tmp_path / "risk.db",
        default_policy=AccountRiskPolicy(
            min_interval_seconds=0,
            manual_verify_backoff_seconds=600,
        ),
        clock=fake_time.now,
        sleeper=fake_time.sleep,
    )

    asyncio.run(controller.before_job("account-1"))
    controller.record_failure(
        "account-1",
        error_code=ErrorCode.MANUAL_VERIFY_REQUIRED,
        retryable=True,
    )

    snapshot = controller.health_snapshot()["account-1"]
    assert snapshot["health_status"] == "manual_verification"
    assert snapshot["cooldown_remaining_seconds"] == 600


def test_account_override_uses_stricter_budget(tmp_path):
    controller = AccountRiskController(
        tmp_path / "risk.db",
        default_policy=AccountRiskPolicy(min_interval_seconds=0, daily_job_budget=10),
        account_policies={"account-1": {"daily_job_budget": 1, "min_interval_seconds": 0}},
    )

    asyncio.run(controller.before_job("account-1"))
    with pytest.raises(AccountRiskBudgetExceeded):
        asyncio.run(controller.before_job("account-1"))
    assert controller.policy_for("account-1").daily_job_budget == 1
