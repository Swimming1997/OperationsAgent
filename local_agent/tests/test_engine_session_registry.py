import pytest

from local_agent_runtime.engine.session import (
    AcquiredSession,
    SessionProviderRegistry,
)
from local_agent_runtime.enums import Platform, SessionStatus
from local_agent_runtime.sessions.registry import build_default_session_registry
from local_agent_runtime.sessions.xhs_browser_session import (
    XhsBrowserSessionProvider,
    XhsSessionAcquireResult,
)


class _StubProvider:
    async def acquire(self, *, session_meta):  # pragma: no cover - trivial
        return XhsSessionAcquireResult(status=SessionStatus.UNAVAILABLE, message="stub")


def test_default_registry_routes_xhs_and_douyin():
    registry = build_default_session_registry()
    assert registry.is_registered(Platform.XHS)
    assert registry.is_registered("xhs")
    assert registry.is_registered(Platform.DOUYIN)
    provider = registry.create(Platform.XHS)
    assert isinstance(provider, XhsBrowserSessionProvider)


def test_unregistered_platform_raises():
    registry = SessionProviderRegistry()
    assert not registry.is_registered("weibo")
    with pytest.raises(KeyError):
        registry.create("weibo")


def test_register_accepts_enum_and_string_keys():
    registry = SessionProviderRegistry()
    registry.register(Platform.DOUYIN, _StubProvider)
    assert registry.is_registered("douyin")
    assert registry.is_registered(Platform.DOUYIN)
    assert "douyin" in registry.supported_platforms()


def test_xhs_session_result_satisfies_acquired_session_protocol():
    result = XhsSessionAcquireResult(status=SessionStatus.READY, message="ok")
    assert isinstance(result, AcquiredSession)
