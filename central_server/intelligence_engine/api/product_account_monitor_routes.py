"""Read-only account monitoring (local-first mirror).

Local agents own their platform accounts and report Cookie-free snapshots; this
router only exposes them for monitoring. There are no write endpoints here.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from intelligence_engine.db.models import AgentAccountSnapshot, Employee, LocalAgent
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import UserRoleName
from intelligence_engine.domain.product_schemas import AccountMonitorList, AccountMonitorRow
from intelligence_engine.security.auth import Principal, require_any_role
from intelligence_engine.services.agent_presence import effective_agent_status
from intelligence_engine.storage.repositories.account_repository import AccountRepository

router = APIRouter(prefix="/api")


@router.get("/product/account-monitor", response_model=AccountMonitorList)
def list_account_monitor(
    db: Session = Depends(get_db),
    _principal: Principal = Depends(
        require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)
    ),
) -> AccountMonitorList:
    rows: list[AgentAccountSnapshot] = AccountRepository(db).list_agent_account_snapshots()
    agent_cache: dict[str, LocalAgent | None] = {}
    employee_cache: dict[str, str | None] = {}
    items: list[AccountMonitorRow] = []
    for row in rows:
        agent = agent_cache.get(row.agent_id)
        if row.agent_id not in agent_cache:
            agent = db.get(LocalAgent, row.agent_id)
            agent_cache[row.agent_id] = agent
        employee_name: str | None = None
        if agent and agent.employee_id:
            if agent.employee_id not in employee_cache:
                employee = db.get(Employee, agent.employee_id)
                employee_cache[agent.employee_id] = employee.display_name if employee else None
            employee_name = employee_cache[agent.employee_id]
        items.append(
            AccountMonitorRow(
                id=row.id,
                agent_id=row.agent_id,
                agent_device_name=agent.device_name if agent else None,
                agent_status=effective_agent_status(agent) if agent else None,
                employee_display_name=employee_name,
                local_account_id=row.local_account_id,
                platform=row.platform,
                display_name=row.display_name,
                platform_nickname=row.platform_nickname,
                account_role=row.account_role,
                status=row.status,
                auth_status=row.auth_status,
                health_status=row.health_status,
                consecutive_failures=row.consecutive_failures,
                last_verified_at=row.last_verified_at,
                reported_at=row.reported_at,
            )
        )
    return AccountMonitorList(items=items, total=len(items))
