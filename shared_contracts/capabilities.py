from shared_contracts.agents import AgentCapabilities
from shared_contracts.enums import JobType, Platform


def xhs_local_agent_capabilities(
    *,
    supports_cdp: bool,
    supports_account_login: bool,
    supported_job_types: list[str] | tuple[str, ...],
    runtime: str = "local_agent_runtime_v1",
) -> AgentCapabilities:
    return AgentCapabilities(
        platforms=[Platform.XHS.value],
        supports_cdp=supports_cdp,
        supports_account_login=supports_account_login,
        job_types=list(supported_job_types) or [item.value for item in JobType],
        runtime=runtime,
    )

