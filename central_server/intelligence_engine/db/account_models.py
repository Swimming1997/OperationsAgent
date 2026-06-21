from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, select, text
from sqlalchemy.orm import Mapped, mapped_column, object_session

from intelligence_engine.db.base import Base
from intelligence_engine.db.model_base import JsonType, TimestampMixin, new_uuid, utcnow


class LocalAgent(Base, TimestampMixin):
    __tablename__ = "local_agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    employee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("employees.id"))
    device_name: Mapped[str | None] = mapped_column(String(255))
    machine_fingerprint: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="offline", nullable=False)
    agent_version: Mapped[str | None] = mapped_column(String(64))
    capabilities_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformAccount(Base, TimestampMixin):
    __tablename__ = "platform_accounts"
    __table_args__ = (
        Index(
            "uq_platform_accounts_unique_external",
            "platform",
            "external_account_id",
            unique=True,
            sqlite_where=text("external_account_id IS NOT NULL"),
            postgresql_where=text("external_account_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    employee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("employees.id"))
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(String(255))
    business_account_type: Mapped[str | None] = mapped_column(String(128))
    business_account_type_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("business_account_types.id"))
    status: Mapped[str] = mapped_column(String(64), default="active", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    auth_status: Mapped[str] = mapped_column(String(32), default="not_logged_in", nullable=False)
    account_role: Mapped[str] = mapped_column(String(64), default="intelligence_collector", nullable=False)
    health_status: Mapped[str] = mapped_column(String(64), default="healthy", nullable=False)
    profile_key: Mapped[str | None] = mapped_column(String(255))
    platform_nickname: Mapped[str | None] = mapped_column(String(255))
    platform_home_url: Mapped[str | None] = mapped_column(String(512))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    login_cdp_port: Mapped[int | None] = mapped_column(Integer)


class AccountLoginSession(Base, TimestampMixin):
    __tablename__ = "account_login_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    platform_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("platform_accounts.id"), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("local_agents.id"))
    status: Mapped[str] = mapped_column(String(64), default="created", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    profile_key: Mapped[str] = mapped_column(String(255), nullable=False)
    cdp_port: Mapped[int | None] = mapped_column(Integer)
    claimed_by_agent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("local_agents.id"))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountSession(Base, TimestampMixin):
    __tablename__ = "account_sessions"
    __table_args__ = (UniqueConstraint("account_id", "local_agent_id", "session_type", name="uq_account_session_per_agent_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("platform_accounts.id"), nullable=False)
    local_agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("local_agents.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    session_type: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_ref: Mapped[str | None] = mapped_column(String(255))
    cookie_ref: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64), default="unavailable", nullable=False)
    session_meta_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountAgentBinding(Base, TimestampMixin):
    __tablename__ = "account_agent_bindings"
    __table_args__ = (UniqueConstraint("account_id", "agent_id", name="uq_account_agent_binding"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("platform_accounts.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("local_agents.id"), nullable=False)
    employee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("employees.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentAccountSnapshot(Base, TimestampMixin):
    """Read-only mirror of a local agent's platform accounts (local-first).

    The local agent owns its accounts; it periodically reports a Cookie-free
    snapshot so central can monitor login / health status. Central never writes
    these rows except through the agent report endpoint.
    """

    __tablename__ = "agent_account_snapshots"
    __table_args__ = (
        UniqueConstraint("agent_id", "local_account_id", name="uq_agent_account_snapshot"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("local_agents.id"), nullable=False)
    local_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    platform_nickname: Mapped[str | None] = mapped_column(String(255))
    external_account_id: Mapped[str | None] = mapped_column(String(255))
    account_role: Mapped[str] = mapped_column(String(64), default="intelligence_collector", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    auth_status: Mapped[str] = mapped_column(String(32), default="not_logged_in", nullable=False)
    health_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


def _get_default_agent_id(account: PlatformAccount) -> str | None:
    session = object_session(account)
    if not session:
        return getattr(account, "_default_agent_id_override", None)
    binding = session.scalar(
        select(AccountAgentBinding)
        .where(AccountAgentBinding.account_id == account.id)
        .where(AccountAgentBinding.enabled.is_(True))
        .order_by(AccountAgentBinding.updated_at.desc(), AccountAgentBinding.created_at.desc())
        .limit(1)
    )
    return binding.agent_id if binding else None


def _set_default_agent_id(account: PlatformAccount, agent_id: str | None) -> None:
    session = object_session(account)
    if not session:
        account._default_agent_id_override = agent_id
        return
    bindings = list(
        session.scalars(
            select(AccountAgentBinding)
            .where(AccountAgentBinding.account_id == account.id)
            .where(AccountAgentBinding.enabled.is_(True))
        )
    )
    if agent_id is None:
        for binding in bindings:
            binding.enabled = False
        session.flush()
        return
    for binding in bindings:
        binding.enabled = binding.agent_id == agent_id
        if binding.enabled:
            binding.employee_id = account.employee_id
    if not any(binding.agent_id == agent_id for binding in bindings):
        session.add(AccountAgentBinding(account_id=account.id, agent_id=agent_id, employee_id=account.employee_id, enabled=True))
    session.flush()


PlatformAccount.default_agent_id = property(_get_default_agent_id, _set_default_agent_id)


def _get_default_agent_id(account: PlatformAccount) -> str | None:
    session = object_session(account)
    if not session:
        return getattr(account, "_default_agent_id_override", None)
    binding = session.scalar(
        select(AccountAgentBinding)
        .where(AccountAgentBinding.account_id == account.id)
        .where(AccountAgentBinding.enabled.is_(True))
        .order_by(AccountAgentBinding.updated_at.desc(), AccountAgentBinding.created_at.desc())
        .limit(1)
    )
    return binding.agent_id if binding else None


def _set_default_agent_id(account: PlatformAccount, agent_id: str | None) -> None:
    session = object_session(account)
    if not session:
        account._default_agent_id_override = agent_id
        return
    bindings = list(
        session.scalars(
            select(AccountAgentBinding)
            .where(AccountAgentBinding.account_id == account.id)
            .where(AccountAgentBinding.enabled.is_(True))
        )
    )
    if agent_id is None:
        for binding in bindings:
            binding.enabled = False
        session.flush()
        return
    for binding in bindings:
        binding.enabled = binding.agent_id == agent_id
        if binding.enabled:
            binding.employee_id = account.employee_id
    if not any(binding.agent_id == agent_id for binding in bindings):
        session.add(AccountAgentBinding(account_id=account.id, agent_id=agent_id, employee_id=account.employee_id, enabled=True))
    session.flush()


PlatformAccount.default_agent_id = property(_get_default_agent_id, _set_default_agent_id)
