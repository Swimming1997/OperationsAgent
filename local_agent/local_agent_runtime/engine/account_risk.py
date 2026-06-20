from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from local_agent_runtime.enums import ErrorCode
from shared_contracts.failure_policy import classify_failure


@dataclass(frozen=True)
class AccountRiskPolicy:
    min_interval_seconds: float = 3.0
    daily_job_budget: int = 200
    failure_backoff_base_seconds: float = 30.0
    failure_backoff_max_seconds: float = 1800.0
    manual_verify_backoff_seconds: float = 21600.0

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any] | None,
        *,
        fallback: "AccountRiskPolicy | None" = None,
    ) -> "AccountRiskPolicy":
        base = fallback or cls()
        if not data:
            return base
        values = asdict(base)
        for key in values:
            if key not in data:
                continue
            try:
                values[key] = int(data[key]) if key == "daily_job_budget" else float(data[key])
            except (TypeError, ValueError):
                continue
        values["min_interval_seconds"] = max(0.0, values["min_interval_seconds"])
        values["daily_job_budget"] = max(1, values["daily_job_budget"])
        values["failure_backoff_base_seconds"] = max(0.0, values["failure_backoff_base_seconds"])
        values["failure_backoff_max_seconds"] = max(
            values["failure_backoff_base_seconds"],
            values["failure_backoff_max_seconds"],
        )
        values["manual_verify_backoff_seconds"] = max(0.0, values["manual_verify_backoff_seconds"])
        return cls(**values)


@dataclass(frozen=True)
class AccountRiskDecision:
    account_id: str
    admitted: bool
    waited_seconds: float = 0.0
    reason: str | None = None
    health_status: str = "healthy"
    jobs_used_today: int = 0
    daily_job_budget: int = 0


class AccountRiskBudgetExceeded(RuntimeError):
    def __init__(self, decision: AccountRiskDecision):
        super().__init__(decision.reason or "daily account job budget exceeded")
        self.decision = decision


class AccountRiskController:
    """Persistent, platform-neutral account protection for claimed jobs."""

    def __init__(
        self,
        state_path: str | Path,
        *,
        default_policy: AccountRiskPolicy | None = None,
        account_policies: Mapping[str, Mapping[str, Any]] | None = None,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
    ):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.default_policy = default_policy or AccountRiskPolicy()
        self.account_policies = {
            str(account_id): AccountRiskPolicy.from_mapping(payload, fallback=self.default_policy)
            for account_id, payload in (account_policies or {}).items()
            if isinstance(payload, Mapping)
        }
        self._clock = clock or time.time
        self._sleeper = sleeper or asyncio.sleep
        self._lock = threading.RLock()
        self._initialize()

    def policy_for(self, account_id: str) -> AccountRiskPolicy:
        return self.account_policies.get(account_id, self.default_policy)

    async def before_job(self, account_id: str | None) -> AccountRiskDecision:
        key = self._account_key(account_id)
        policy = self.policy_for(key)
        now = self._clock()
        row = self._read_state(key)
        wait_until = max(
            float(row["backoff_until"] or 0),
            float(row["last_finished_at"] or 0) + policy.min_interval_seconds,
        )
        waited = max(0.0, wait_until - now)
        if waited:
            await self._sleeper(waited)
            now = self._clock()

        day = self._utc_day(now)
        denied: AccountRiskDecision | None = None
        with self._lock, self._connect() as connection:
            current = self._read_state(key, connection=connection)
            jobs_used = int(current["jobs_used_today"] or 0) if current["budget_day"] == day else 0
            if jobs_used >= policy.daily_job_budget:
                denied = AccountRiskDecision(
                    account_id=key,
                    admitted=False,
                    waited_seconds=waited,
                    reason="daily_job_budget_exceeded",
                    health_status="budget_exhausted",
                    jobs_used_today=jobs_used,
                    daily_job_budget=policy.daily_job_budget,
                )
                connection.execute(
                    "UPDATE account_risk_state SET health_status = ?, updated_at = ? WHERE account_id = ?",
                    (denied.health_status, now, key),
                )
            else:
                jobs_used += 1
                connection.execute(
                    """
                    UPDATE account_risk_state
                    SET budget_day = ?, jobs_used_today = ?, health_status = ?, updated_at = ?
                    WHERE account_id = ?
                    """,
                    (day, jobs_used, "healthy", now, key),
                )
        if denied is not None:
            raise AccountRiskBudgetExceeded(denied)
        return AccountRiskDecision(
            account_id=key,
            admitted=True,
            waited_seconds=waited,
            health_status="healthy",
            jobs_used_today=jobs_used,
            daily_job_budget=policy.daily_job_budget,
        )

    def record_success(self, account_id: str | None) -> None:
        key = self._account_key(account_id)
        now = self._clock()
        with self._lock, self._connect() as connection:
            self._ensure_row(connection, key)
            connection.execute(
                """
                UPDATE account_risk_state
                SET last_finished_at = ?, consecutive_failures = 0, backoff_until = 0,
                    health_status = 'healthy', last_error_code = NULL, updated_at = ?
                WHERE account_id = ?
                """,
                (now, now, key),
            )

    def record_failure(
        self,
        account_id: str | None,
        *,
        error_code: ErrorCode,
        retryable: bool,
    ) -> None:
        key = self._account_key(account_id)
        policy = self.policy_for(key)
        failure_policy = classify_failure(error_code)
        now = self._clock()
        with self._lock, self._connect() as connection:
            row = self._read_state(key, connection=connection)
            failures = int(row["consecutive_failures"] or 0) + 1
            backoff = 0.0
            health = "degraded"
            if error_code == ErrorCode.MANUAL_VERIFY_REQUIRED:
                backoff = policy.manual_verify_backoff_seconds
                health = "manual_verification"
            elif retryable or failure_policy.retryable:
                backoff = min(
                    policy.failure_backoff_max_seconds,
                    policy.failure_backoff_base_seconds * (2 ** max(0, failures - 1)),
                )
                health = (
                    failure_policy.account_health
                    if failure_policy.account_health in {"cooling_down", "manual_verification"}
                    else "cooling_down"
                ) if backoff else "degraded"
            connection.execute(
                """
                UPDATE account_risk_state
                SET last_finished_at = ?, consecutive_failures = ?, backoff_until = ?,
                    health_status = ?, last_error_code = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (now, failures, now + backoff, health, error_code.value, now, key),
            )

    def health_snapshot(self) -> dict[str, dict[str, Any]]:
        now = self._clock()
        day = self._utc_day(now)
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM account_risk_state ORDER BY account_id").fetchall()
        snapshot: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row["account_id"])
            policy = self.policy_for(key)
            jobs_used = int(row["jobs_used_today"] or 0) if row["budget_day"] == day else 0
            snapshot[key] = {
                "health_status": row["health_status"],
                "jobs_used_today": jobs_used,
                "daily_job_budget": policy.daily_job_budget,
                "consecutive_failures": int(row["consecutive_failures"] or 0),
                "cooldown_remaining_seconds": round(max(0.0, float(row["backoff_until"] or 0) - now), 3),
                "last_error_code": row["last_error_code"],
            }
        return snapshot

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS account_risk_state (
                    account_id TEXT PRIMARY KEY,
                    budget_day TEXT,
                    jobs_used_today INTEGER NOT NULL DEFAULT 0,
                    last_finished_at REAL NOT NULL DEFAULT 0,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    backoff_until REAL NOT NULL DEFAULT 0,
                    health_status TEXT NOT NULL DEFAULT 'healthy',
                    last_error_code TEXT,
                    updated_at REAL NOT NULL DEFAULT 0
                )
                """
            )

    def _read_state(self, account_id: str, *, connection: sqlite3.Connection | None = None) -> sqlite3.Row:
        if connection is not None:
            self._ensure_row(connection, account_id)
            return connection.execute(
                "SELECT * FROM account_risk_state WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        with self._lock, self._connect() as owned:
            self._ensure_row(owned, account_id)
            return owned.execute(
                "SELECT * FROM account_risk_state WHERE account_id = ?",
                (account_id,),
            ).fetchone()

    @staticmethod
    def _ensure_row(connection: sqlite3.Connection, account_id: str) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO account_risk_state (account_id) VALUES (?)",
            (account_id,),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.state_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _account_key(account_id: str | None) -> str:
        return str(account_id or "__unbound__")

    @staticmethod
    def _utc_day(timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
