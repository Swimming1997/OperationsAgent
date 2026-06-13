from __future__ import annotations

from typing import Any, Protocol


class PlatformConnector(Protocol):
    """Common contract for platform-specific collectors."""

    @property
    def platform(self) -> str:
        ...

    def capabilities(self) -> dict[str, Any]:
        ...

    def supports(self, job_type: str) -> bool:
        ...

    async def execute(self, *, job: Any, session: Any, client: Any) -> Any:
        ...


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, PlatformConnector] = {}

    def register(self, connector: PlatformConnector) -> None:
        self._connectors[connector.platform] = connector

    def resolve(self, platform: str, job_type: str) -> PlatformConnector:
        connector = self._connectors.get(platform)
        if not connector or not connector.supports(job_type):
            raise KeyError(f"unsupported connector job: {platform}.{job_type}")
        return connector


__all__ = ["ConnectorRegistry", "PlatformConnector"]
