"""Platform-agnostic browser session contracts.

Every platform connector (XHS, Douyin, ...) acquires a logged-in browser
session the same way: connect to a local Chrome (via CDP or a persistent
profile), land on the platform home, and report whether the session is
``READY`` / ``EXPIRED`` / ``MANUAL_VERIFY_REQUIRED`` / ``UNAVAILABLE``.

This module defines the structural contract for that, plus a small registry so
the runtime can resolve "which provider handles platform X" without hard-coding
a specific platform. XHS's existing ``XhsBrowserSessionProvider`` /
``XhsSessionAcquireResult`` already match these protocols structurally, so they
require no changes — they just get registered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from local_agent_runtime.enums import Platform, SessionStatus


@runtime_checkable
class AcquiredSession(Protocol):
    """A browser session result: enough to run a probe and clean up."""

    status: SessionStatus
    page: Any

    async def close(self) -> None: ...


@dataclass
class BrowserSessionResult:
    """Reusable browser session result for new platform providers.

    XHS keeps its own ``XhsSessionAcquireResult`` for backward compatibility;
    new platforms (Douyin, ...) should use this shared type so cleanup and the
    ``AcquiredSession`` contract are implemented once.
    """

    status: SessionStatus
    message: str
    playwright: Any | None = None
    browser: Any | None = None
    context: Any | None = None
    page: Any | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    detached_cdp: bool = False

    async def close(self) -> None:
        if self.detached_cdp:
            if self.browser:
                try:
                    await self.browser.close()
                except Exception:
                    pass
            if self.playwright:
                await self.playwright.stop()
            return
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


class BrowserSessionProvider(Protocol):
    """Acquires a browser session for one account on one platform."""

    async def acquire(self, *, session_meta: dict[str, Any]) -> AcquiredSession: ...


ProviderFactory = Callable[[], BrowserSessionProvider]


def _platform_key(platform: Platform | str) -> str:
    if isinstance(platform, Platform):
        return platform.value
    return str(platform).strip().lower()


class SessionProviderRegistry:
    """Maps a platform key to a factory that builds its session provider.

    The runtime uses this to route session acquisition by ``job.payload`` /
    account platform, so adding Douyin is just one ``register`` call rather than
    new branching in the runtime.
    """

    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, platform: Platform | str, factory: ProviderFactory) -> None:
        self._factories[_platform_key(platform)] = factory

    def is_registered(self, platform: Platform | str) -> bool:
        return _platform_key(platform) in self._factories

    def create(self, platform: Platform | str) -> BrowserSessionProvider:
        key = _platform_key(platform)
        try:
            factory = self._factories[key]
        except KeyError as exc:
            raise KeyError(
                f"no browser session provider registered for platform: {key!r}; "
                f"supported: {self.supported_platforms()}"
            ) from exc
        return factory()

    def supported_platforms(self) -> list[str]:
        return sorted(self._factories)
