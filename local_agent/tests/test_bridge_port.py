from __future__ import annotations

import pytest

from local_agent_runtime.bridge_port import is_tcp_port_in_use, pick_available_bridge_port


def test_pick_available_bridge_port_returns_preferred_when_free(monkeypatch):
    monkeypatch.setattr(
        "local_agent_runtime.bridge_port.is_tcp_port_in_use",
        lambda _host, port: port != 18765,
    )
    port, replaced = pick_available_bridge_port("127.0.0.1", 18765)
    assert port == 18765
    assert replaced is None


def test_pick_available_bridge_port_skips_in_use(monkeypatch):
    monkeypatch.setattr(
        "local_agent_runtime.bridge_port.is_tcp_port_in_use",
        lambda _host, port: port in {18765, 18766},
    )
    port, replaced = pick_available_bridge_port("127.0.0.1", 18765)
    assert port == 18767
    assert replaced == 18765


def test_pick_available_bridge_port_raises_when_exhausted(monkeypatch):
    monkeypatch.setattr("local_agent_runtime.bridge_port.is_tcp_port_in_use", lambda _host, _port: True)
    with pytest.raises(RuntimeError, match="no free bridge port"):
        pick_available_bridge_port("127.0.0.1", 18765, max_attempts=3)


def test_is_tcp_port_in_use_on_free_port():
    assert is_tcp_port_in_use("127.0.0.1", 59999) is False
