from __future__ import annotations

from intelligence_engine.db.models import LocalAgent
from intelligence_engine.services.agent_presence import is_agent_live


def agent_supports_account_login(agent: LocalAgent) -> bool:
    capabilities = agent.capabilities_json or {}
    return capabilities.get("supports_account_login") is True


def agent_sort_key(agent: LocalAgent) -> tuple:
    live = is_agent_live(agent)
    login = agent_supports_account_login(agent)
    heartbeat = agent.last_heartbeat_at
    heartbeat_ts = heartbeat.timestamp() if heartbeat is not None else 0.0
    retired = agent.status == "retired"
    return (
        retired,
        not live,
        not login,
        -heartbeat_ts,
    )


def sort_agents_for_display(agents: list[LocalAgent]) -> list[LocalAgent]:
    return sorted(agents, key=agent_sort_key)
