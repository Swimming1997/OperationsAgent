import asyncio
import json

import httpx

from local_agent_runtime.config import load_agent_runtime_config
from local_agent_runtime.runtime import (
    AgentRuntimeConfig,
    CenterClient,
    ClaimedJobPayload,
    JobExecutionResult,
    LocalAgentRuntime,
    RuntimeFailure,
)
from local_agent_runtime.enums import ErrorCode, JobStatus, JobType


class FakeCenterClient:
    def __init__(self, jobs=None):
        self.jobs = jobs or []
        self.events = []

    async def register_agent(self, config):
        self.events.append(("register", config.machine_fingerprint))
        return "agent-1"

    async def heartbeat(self, agent_id, running_job_ids, *, status="online", capabilities=None, agent_version=None):
        self.events.append(("heartbeat", agent_id, tuple(running_job_ids), capabilities))

    async def claim_login_sessions(self, agent_id, *, max_sessions=1):
        self.events.append(("claim_login_sessions", agent_id, max_sessions))
        return []

    async def claim_jobs(self, agent_id, supported_job_types, max_jobs):
        self.events.append(("claim", agent_id, tuple(supported_job_types), max_jobs))
        claimed = self.jobs[:max_jobs]
        self.jobs = self.jobs[max_jobs:]
        return claimed

    async def start_job(self, job_id, agent_id):
        self.events.append(("start", job_id, agent_id))

    async def progress_job(self, job_id, agent_id, checkpoint, partial_metrics=None):
        self.events.append(("progress", job_id, checkpoint, partial_metrics or {}))

    async def complete_job(self, job_id, agent_id, status, result_summary):
        self.events.append(("complete", job_id, status, result_summary))

    async def fail_job(self, job_id, agent_id, failure, checkpoint):
        self.events.append(("fail", job_id, failure.code.value, failure.message, checkpoint))


class FakeExecutor:
    def __init__(self, result=None, failure=None):
        self.result = result or JobExecutionResult(status=JobStatus.SUCCESS.value, checkpoint={"step": "done"}, result_summary={"ok": True})
        self.failure = failure
        self.seen = []

    async def execute(self, *, agent_id, job):
        self.seen.append((agent_id, job.job_type))
        if self.failure:
            raise self.failure
        return self.result


def test_agent_config_loads_toml_account_mapping(tmp_path):
    config_path = tmp_path / "agent.toml"
    config_path.write_text(
        """
center_url = "http://center.local"
agent_id = "agent-x"
machine_fingerprint = "machine-x"
claim_interval_seconds = 2
max_concurrent_jobs = 1

[accounts]
"account-1" = { platform = "xhs", session_mode = "cdp", cdp_url = "http://127.0.0.1:9222" }
""",
        encoding="utf-8",
    )
    config = load_agent_runtime_config(config_path)
    assert config.center_base_url == "http://center.local"
    assert config.agent_id == "agent-x"
    assert config.account_sessions["account-1"]["cdp_url"] == "http://127.0.0.1:9222"


def test_runtime_claims_and_completes_job_lifecycle():
    job = ClaimedJobPayload(job_id="job-1", job_type=JobType.FEED_COLLECT.value, account_id="account-1", payload={}, checkpoint={})
    client = FakeCenterClient(jobs=[job])
    executor = FakeExecutor()
    runtime = LocalAgentRuntime(config=AgentRuntimeConfig(machine_fingerprint="test-agent"), client=client, executor=executor)

    handled = asyncio.run(runtime.run_once())

    assert handled == 1
    assert ("register", "test-agent") in client.events
    assert ("start", "job-1", "agent-1") in client.events
    assert any(event[0] == "progress" and event[1] == "job-1" for event in client.events)
    assert any(event[0] == "complete" and event[1] == "job-1" and event[2] == JobStatus.SUCCESS.value for event in client.events)
    assert executor.seen == [("agent-1", JobType.FEED_COLLECT.value)]


def test_runtime_reports_failure_with_existing_error_code():
    job = ClaimedJobPayload(job_id="job-1", job_type=JobType.CREATOR_MONITOR.value, account_id="account-1", payload={}, checkpoint={"cursor": "a"})
    failure = RuntimeFailure(ErrorCode.MANUAL_VERIFY_REQUIRED, "manual verify required", retryable=True)
    client = FakeCenterClient(jobs=[job])
    runtime = LocalAgentRuntime(config=AgentRuntimeConfig(agent_id="agent-1"), client=client, executor=FakeExecutor(failure=failure))

    handled = asyncio.run(runtime.run_once())

    assert handled == 1
    assert ("fail", "job-1", ErrorCode.MANUAL_VERIFY_REQUIRED.value, "manual verify required", {"cursor": "a"}) in client.events


def test_runtime_routes_creator_monitor_job_type():
    job = ClaimedJobPayload(
        job_id="job-creator",
        job_type=JobType.CREATOR_MONITOR.value,
        account_id="account-1",
        payload={"creator_monitor_id": "monitor-1"},
        checkpoint={},
    )
    executor = FakeExecutor(JobExecutionResult(status=JobStatus.SUCCESS.value, result_summary={"items_seen": 3}))
    client = FakeCenterClient(jobs=[job])
    runtime = LocalAgentRuntime(config=AgentRuntimeConfig(agent_id="agent-1"), client=client, executor=executor)

    asyncio.run(runtime.run_once())

    assert executor.seen == [("agent-1", JobType.CREATOR_MONITOR.value)]
    assert any(event[0] == "complete" and event[3]["items_seen"] == 3 for event in client.events)


def test_center_client_http_job_lifecycle_uses_json_protocol():
    events = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        events.append((request.method, request.url.path, body))
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/api/agents/register":
            return httpx.Response(200, json={"agent_id": "agent-http"})
        if request.url.path == "/api/agents/agent-http/jobs/claim":
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "job_id": "job-http",
                            "job_type": "feed_collect",
                            "account_id": "account-1",
                            "payload": {"platform": "xhs"},
                            "checkpoint": {},
                            "claim_expires_at": "2026-05-24T00:00:00Z",
                        }
                    ]
                },
            )
        if request.url.path in {"/api/jobs/job-http/start", "/api/jobs/job-http/complete"}:
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={"error": "unexpected"})

    async def run_flow():
        client = CenterClient(base_url="http://central.test")
        await client._client.aclose()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://central.test")
        try:
            await client.check_health()
            agent_id = await client.register_agent(AgentRuntimeConfig(machine_fingerprint="machine-http"))
            jobs = await client.claim_jobs(agent_id, (JobType.FEED_COLLECT.value,), 1)
            await client.start_job(jobs[0].job_id, agent_id)
            await client.complete_job(jobs[0].job_id, agent_id, JobStatus.SUCCESS.value, {"ok": True})
            return agent_id, jobs
        finally:
            await client.aclose()

    agent_id, jobs = asyncio.run(run_flow())

    assert agent_id == "agent-http"
    assert jobs[0].job_id == "job-http"
    assert ("POST", "/api/jobs/job-http/complete", {"agent_id": "agent-http", "status": "success", "result_summary": {"ok": True}}) in events
