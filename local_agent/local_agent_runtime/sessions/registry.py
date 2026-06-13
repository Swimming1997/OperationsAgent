"""Default session-provider registry wiring.

Keeps platform-specific imports out of the engine core: the engine defines the
registry shape, this module registers concrete providers. Add Douyin here once
its provider exists.
"""

from __future__ import annotations

from local_agent_runtime.engine.session import SessionProviderRegistry
from local_agent_runtime.enums import Platform
from local_agent_runtime.sessions.douyin_browser_session import DouyinBrowserSessionProvider
from local_agent_runtime.sessions.xhs_browser_session import XhsBrowserSessionProvider


def build_default_session_registry() -> SessionProviderRegistry:
    registry = SessionProviderRegistry()
    registry.register(Platform.XHS, XhsBrowserSessionProvider)
    registry.register(Platform.DOUYIN, DouyinBrowserSessionProvider)
    return registry


default_session_registry = build_default_session_registry()
