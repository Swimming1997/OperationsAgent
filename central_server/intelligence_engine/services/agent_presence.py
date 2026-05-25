from __future__ import annotations

from datetime import datetime, timezone

from intelligence_engine.db.models import LocalAgent, utcnow
from intelligence_engine.domain.enums import AgentStatus

HEARTBEAT_ONLINE_SECONDS = 90


def _normalize_heartbeat(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def is_agent_live(agent: LocalAgent, *, max_age_seconds: int = HEARTBEAT_ONLINE_SECONDS) -> bool:
    if agent.status in ("offline", "retired"):
        return False
    heartbeat = _normalize_heartbeat(agent.last_heartbeat_at)
    if not heartbeat:
        return False
    return (utcnow() - heartbeat).total_seconds() <= max_age_seconds


def effective_agent_status(agent: LocalAgent, *, max_age_seconds: int = HEARTBEAT_ONLINE_SECONDS) -> str:
    if is_agent_live(agent, max_age_seconds=max_age_seconds):
        return AgentStatus.ONLINE.value
    return AgentStatus.OFFLINE.value


def sync_agent_presence(agent: LocalAgent, *, max_age_seconds: int = HEARTBEAT_ONLINE_SECONDS) -> bool:
    """Persist effective status when stale DB status disagrees. Returns True if mutated."""
    effective = effective_agent_status(agent, max_age_seconds=max_age_seconds)
    if agent.status != effective:
        agent.status = effective
        return True
    return False
