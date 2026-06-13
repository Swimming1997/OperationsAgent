from typing import Any

from pydantic import Field

from shared_contracts.base import ApiModel


class AgentCapabilities(ApiModel):
    platforms: list[str] = Field(default_factory=list)
    supports_cdp: bool = False
    supports_account_login: bool = False
    job_types: list[str] = Field(default_factory=list)
    runtime: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentHeartbeat(ApiModel):
    status: str
    running_job_ids: list[str] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    agent_version: str | None = None

