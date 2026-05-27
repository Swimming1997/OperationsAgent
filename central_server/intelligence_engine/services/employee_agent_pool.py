"""运营员工维度的 Local Agent 池（与平台账号无强绑定）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import AccountSession, LocalAgent, PlatformAccount
from intelligence_engine.domain.enums import AgentStatus, SessionStatus


def agents_for_employee(db: Session, employee_id: str | None) -> list[LocalAgent]:
    if not employee_id:
        return []
    return list(
        db.scalars(
            select(LocalAgent)
            .where(LocalAgent.employee_id == employee_id)
            .where(LocalAgent.status != AgentStatus.RETIRED.value)
            .order_by(LocalAgent.last_heartbeat_at.desc().nullslast(), LocalAgent.created_at.desc())
        )
    )


def register_agents_to_employee(
    db: Session,
    *,
    agent_ids: list[str],
    employee_id: str,
    force: bool,
) -> list[LocalAgent]:
    registered: list[LocalAgent] = []
    for agent_id in agent_ids:
        agent = db.get(LocalAgent, agent_id)
        if not agent:
            raise KeyError(f"agent not found: {agent_id}")
        if agent.employee_id and agent.employee_id != employee_id and not force:
            raise AgentEmployeeConflictError(agent_id=agent.id, bound_employee_id=agent.employee_id)
        agent.employee_id = employee_id
        registered.append(agent)
    db.flush()
    return registered


def account_session_health_for_employee_pool(db: Session, account: PlatformAccount) -> str | None:
    if not account.employee_id:
        row = db.scalar(
            select(AccountSession.status)
            .where(AccountSession.account_id == account.id)
            .order_by(AccountSession.last_validated_at.desc().nullslast(), AccountSession.created_at.desc())
            .limit(1)
        )
        return row
    statuses = list(
        db.scalars(
            select(AccountSession.status)
            .join(LocalAgent, LocalAgent.id == AccountSession.local_agent_id)
            .where(AccountSession.account_id == account.id)
            .where(LocalAgent.employee_id == account.employee_id)
            .order_by(AccountSession.last_validated_at.desc().nullslast(), AccountSession.created_at.desc())
        )
    )
    if not statuses:
        return None
    if SessionStatus.READY.value in statuses:
        return SessionStatus.READY.value
    if SessionStatus.MANUAL_VERIFY_REQUIRED.value in statuses:
        return SessionStatus.MANUAL_VERIFY_REQUIRED.value
    if SessionStatus.EXPIRED.value in statuses:
        return SessionStatus.EXPIRED.value
    return statuses[0]


def _device_name_matches(central_name: str | None, local_name: str | None) -> bool:
    if not central_name or not local_name:
        return False
    if central_name == local_name:
        return True
    return central_name.startswith(f"{local_name} [")


def find_agent_for_discover_item(
    db: Session,
    *,
    agent_id: str | None = None,
    device_name: str | None = None,
    machine_fingerprint: str | None = None,
) -> LocalAgent | None:
    if agent_id:
        agent = db.get(LocalAgent, agent_id)
        if agent and agent.status != AgentStatus.RETIRED.value:
            return agent
    if machine_fingerprint:
        agent = db.scalar(
            select(LocalAgent).where(
                LocalAgent.machine_fingerprint == machine_fingerprint,
                LocalAgent.status != AgentStatus.RETIRED.value,
            )
        )
        if agent:
            return agent
    if device_name:
        for agent in db.scalars(select(LocalAgent).where(LocalAgent.status != AgentStatus.RETIRED.value)):
            if _device_name_matches(agent.device_name, device_name):
                return agent
    return None


def resolve_discovered_agents(
    db: Session,
    items: list[dict],
) -> list[tuple[LocalAgent, int | None]]:
    """按 discover 条目在中央库中解析 Agent（去重）。"""
    resolved: list[tuple[LocalAgent, int | None]] = []
    seen: set[str] = set()
    for item in items:
        agent = find_agent_for_discover_item(
            db,
            agent_id=item.get("agent_id"),
            device_name=item.get("device_name"),
            machine_fingerprint=item.get("machine_fingerprint"),
        )
        if not agent or agent.id in seen:
            continue
        seen.add(agent.id)
        bridge_port = item.get("bridge_port")
        resolved.append((agent, int(bridge_port) if bridge_port is not None else None))
    return resolved


class AgentEmployeeConflictError(Exception):
    def __init__(self, *, agent_id: str, bound_employee_id: str):
        self.agent_id = agent_id
        self.bound_employee_id = bound_employee_id
        super().__init__(f"agent {agent_id} bound to employee {bound_employee_id}")
