from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import AccountSession, Employee, LocalAgent, PlatformAccount, utcnow
from intelligence_engine.domain.enums import AccountStatus, AgentStatus


class AccountRepository:
    def __init__(self, db: Session):
        self.db = db

    def ensure_employee(self, employee_id: str | None, display_name: str = "default") -> str | None:
        if not employee_id:
            return None
        employee = self.db.get(Employee, employee_id)
        if not employee:
            employee = Employee(id=employee_id, display_name=display_name)
            self.db.add(employee)
            self.db.flush()
        return employee.id

    def _normalize_device_name(
        self,
        device_name: str | None,
        *,
        machine_fingerprint: str | None,
        exclude_agent_id: str | None = None,
    ) -> str | None:
        if not device_name:
            return device_name
        stmt = select(LocalAgent).where(
            LocalAgent.device_name == device_name,
            LocalAgent.status != "retired",
        )
        if exclude_agent_id:
            stmt = stmt.where(LocalAgent.id != exclude_agent_id)
        conflicts = list(self.db.scalars(stmt))
        if not conflicts:
            return device_name
        if machine_fingerprint and any(item.machine_fingerprint == machine_fingerprint for item in conflicts):
            return device_name
        tag = (machine_fingerprint or exclude_agent_id or "dup")[:8]
        return f"{device_name} [{tag}]"

    def register_agent(
        self,
        *,
        agent_id: str | None = None,
        employee_id: str | None,
        device_name: str | None,
        machine_fingerprint: str | None,
        agent_version: str | None,
        capabilities: dict,
    ) -> LocalAgent:
        existing = self.db.get(LocalAgent, agent_id) if agent_id else None
        if not existing and machine_fingerprint:
            existing = self.db.scalar(select(LocalAgent).where(LocalAgent.machine_fingerprint == machine_fingerprint))
        if existing:
            if existing.status == "retired":
                existing.status = AgentStatus.OFFLINE.value
            if employee_id:
                existing.employee_id = employee_id
            if device_name:
                existing.device_name = self._normalize_device_name(
                    device_name,
                    machine_fingerprint=machine_fingerprint or existing.machine_fingerprint,
                    exclude_agent_id=existing.id,
                )
            if machine_fingerprint:
                existing.machine_fingerprint = machine_fingerprint
            existing.status = AgentStatus.ONLINE.value
            existing.last_heartbeat_at = utcnow()
            existing.capabilities_json = capabilities
            existing.agent_version = agent_version
            return existing
        self.ensure_employee(employee_id)
        normalized_name = self._normalize_device_name(
            device_name,
            machine_fingerprint=machine_fingerprint,
        )
        agent = LocalAgent(
            employee_id=employee_id,
            device_name=normalized_name,
            machine_fingerprint=machine_fingerprint,
            agent_version=agent_version,
            capabilities_json=capabilities,
            status=AgentStatus.ONLINE.value,
            last_heartbeat_at=utcnow(),
        )
        self.db.add(agent)
        self.db.flush()
        return agent

    def heartbeat(
        self,
        *,
        agent_id: str,
        status: AgentStatus,
        capabilities: dict | None = None,
        agent_version: str | None = None,
    ) -> LocalAgent:
        agent = self.db.get(LocalAgent, agent_id)
        if not agent:
            raise KeyError(f"agent not found: {agent_id}")
        status_value = getattr(status, "value", status)
        agent.status = status_value
        if status_value != AgentStatus.OFFLINE.value:
            agent.last_heartbeat_at = utcnow()
        if agent_version:
            agent.agent_version = agent_version
        if capabilities:
            agent.capabilities_json = capabilities
        return agent

    def create_account(
        self,
        *,
        employee_id: str | None,
        platform: str,
        display_name: str,
        external_account_id: str | None,
        business_account_type: str | None,
        business_account_type_id: str | None = None,
        default_agent_id: str | None,
        metadata: dict,
    ) -> PlatformAccount:
        self.ensure_employee(employee_id)
        account = PlatformAccount(
            employee_id=employee_id,
            platform=platform,
            display_name=display_name,
            external_account_id=external_account_id,
            business_account_type=business_account_type,
            business_account_type_id=business_account_type_id,
            default_agent_id=default_agent_id,
            metadata_json=metadata,
            status=AccountStatus.ACTIVE.value,
        )
        self.db.add(account)
        self.db.flush()
        return account

    def list_accounts(self, *, platform: str | None = None, status: str | None = None) -> list[PlatformAccount]:
        stmt = select(PlatformAccount)
        if platform:
            stmt = stmt.where(PlatformAccount.platform == platform)
        if status:
            stmt = stmt.where(PlatformAccount.status == status)
        return list(self.db.scalars(stmt.order_by(PlatformAccount.created_at.desc())))

    def create_session(
        self,
        *,
        account: PlatformAccount,
        local_agent_id: str,
        session_type: str,
        profile_ref: str | None,
        cookie_ref: str | None,
        status: str,
        session_meta: dict,
    ) -> AccountSession:
        account_session = AccountSession(
            account_id=account.id,
            local_agent_id=local_agent_id,
            platform=account.platform,
            session_type=session_type,
            profile_ref=profile_ref,
            cookie_ref=cookie_ref,
            status=status,
            session_meta_json=session_meta,
            last_validated_at=utcnow() if status == "ready" else None,
        )
        self.db.add(account_session)
        self.db.flush()
        return account_session
