import pytest

from local_agent_runtime.connectors.base.connector import ConnectorRegistry


class FakeConnector:
    platform = "fake"

    def capabilities(self):
        return {"platforms": ["fake"]}

    def supports(self, job_type: str) -> bool:
        return job_type == "feed_collect"

    async def execute(self, *, job, session, client):
        return {"ok": True}


def test_connector_registry_resolves_supported_connector():
    registry = ConnectorRegistry()
    connector = FakeConnector()
    registry.register(connector)

    assert registry.resolve("fake", "feed_collect") is connector


def test_connector_registry_rejects_unsupported_job():
    registry = ConnectorRegistry()
    registry.register(FakeConnector())

    with pytest.raises(KeyError):
        registry.resolve("fake", "detail_fetch")

