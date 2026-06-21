import asyncio
import json
from datetime import datetime, timezone

import httpx
import local_agent_runtime.runtime as runtime_module

from local_agent_runtime.config import load_agent_runtime_config
from local_agent_runtime.runtime import (
    AgentRuntimeConfig,
    CenterClient,
    ClaimedJobPayload,
    JobExecutionResult,
    LocalAgentRuntime,
    RuntimeFailure,
    XhsJobExecutor,
)
from local_agent_runtime.contracts import FeedCandidateInput
from local_agent_runtime.connectors.xhs.creator import XhsCreatorFetchError, XhsCreatorFetchResult, XhsCreatorItem, _current_account_profile_from_page
from local_agent_runtime.enums import ContentType, ErrorCode, FeedType, JobStatus, JobType, Platform, SourceSurface
from local_agent_runtime.engine.account_risk import AccountRiskController, AccountRiskPolicy
from local_agent_runtime.engine.poll_backoff import IdlePollBackoff


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

    async def report_account_snapshots(self, agent_id, accounts):
        self.events.append(("account_snapshots", agent_id, accounts))


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


class FakeIngestionClient:
    async def ingest_feed_candidates(self, payload):
        return {
            "results": [
                {
                    "platform_content_id": item.platform_content_id,
                    "is_new_content": True,
                    "detail_job_enqueued": item.visible_like_count is None,
                }
                for item in payload.candidates
            ]
        }


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

[risk_control]
enabled = true
state_path = "data/test-risk.db"
min_interval_seconds = 7
daily_job_budget = 50

[risk_control.accounts."account-1"]
min_interval_seconds = 12
daily_job_budget = 20
""",
        encoding="utf-8",
    )
    config = load_agent_runtime_config(config_path)
    assert config.center_base_url == "http://center.local"
    assert config.agent_id == "agent-x"
    assert config.account_sessions["account-1"]["cdp_url"] == "http://127.0.0.1:9222"
    assert config.risk_control_enabled is True
    assert config.default_risk_policy["min_interval_seconds"] == 7
    assert config.default_risk_policy["daily_job_budget"] == 50
    assert config.account_risk_policies["account-1"]["daily_job_budget"] == 20


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


def test_runtime_reports_cookie_free_account_snapshots():
    client = FakeCenterClient()
    runtime = LocalAgentRuntime(config=AgentRuntimeConfig(machine_fingerprint="snap-agent"), client=client)
    runtime.account_snapshot_provider = lambda: [
        {
            "id": "acc-1",
            "platform": "xhs",
            "display_name": "号一",
            "platform_nickname": "昵称",
            "auth_status": "active",
            "health_status": "healthy",
            "consecutive_failures": 2,
            "cookie": "should-not-be-forwarded",
        },
        {"platform": "xhs"},  # missing id -> skipped
    ]

    asyncio.run(runtime.run_once())

    reports = [event for event in client.events if event[0] == "account_snapshots"]
    assert len(reports) == 1
    _, agent_id, accounts = reports[0]
    assert agent_id == "agent-1"
    assert len(accounts) == 1
    snapshot = accounts[0]
    assert snapshot["local_account_id"] == "acc-1"
    assert snapshot["auth_status"] == "active"
    assert snapshot["consecutive_failures"] == 2
    assert "cookie" not in snapshot


def test_runtime_skips_account_snapshots_without_provider():
    client = FakeCenterClient()
    runtime = LocalAgentRuntime(config=AgentRuntimeConfig(machine_fingerprint="snap-agent"), client=client)

    asyncio.run(runtime.run_once())

    assert not [event for event in client.events if event[0] == "account_snapshots"]


def test_runtime_reports_failure_with_existing_error_code():
    job = ClaimedJobPayload(job_id="job-1", job_type=JobType.CREATOR_MONITOR.value, account_id="account-1", payload={}, checkpoint={"cursor": "a"})
    failure = RuntimeFailure(ErrorCode.MANUAL_VERIFY_REQUIRED, "manual verify required", retryable=True)
    client = FakeCenterClient(jobs=[job])
    runtime = LocalAgentRuntime(config=AgentRuntimeConfig(agent_id="agent-1"), client=client, executor=FakeExecutor(failure=failure))

    handled = asyncio.run(runtime.run_once())

    assert handled == 1
    assert ("fail", "job-1", ErrorCode.MANUAL_VERIFY_REQUIRED.value, "manual verify required", {"cursor": "a"}) in client.events


def test_runtime_rejects_claimed_job_when_account_daily_budget_is_exhausted(tmp_path):
    jobs = [
        ClaimedJobPayload(job_id="job-1", job_type=JobType.FEED_COLLECT.value, account_id="account-1", payload={}, checkpoint={}),
        ClaimedJobPayload(job_id="job-2", job_type=JobType.FEED_COLLECT.value, account_id="account-1", payload={}, checkpoint={}),
    ]
    client = FakeCenterClient(jobs=jobs)
    executor = FakeExecutor()
    risk = AccountRiskController(
        tmp_path / "risk.db",
        default_policy=AccountRiskPolicy(min_interval_seconds=0, daily_job_budget=1),
    )
    runtime = LocalAgentRuntime(
        config=AgentRuntimeConfig(agent_id="agent-1", max_jobs_per_claim=2),
        client=client,
        executor=executor,
        account_risk=risk,
    )

    handled = asyncio.run(runtime.run_once())

    assert handled == 2
    assert executor.seen == [("agent-1", JobType.FEED_COLLECT.value)]
    assert any(event[0] == "fail" and event[1] == "job-2" and event[2] == ErrorCode.RATE_LIMITED.value for event in client.events)


def test_runtime_heartbeat_reports_account_risk_health(tmp_path):
    risk = AccountRiskController(
        tmp_path / "risk.db",
        default_policy=AccountRiskPolicy(min_interval_seconds=0),
    )
    asyncio.run(risk.before_job("account-1"))
    risk.record_failure("account-1", error_code=ErrorCode.RATE_LIMITED, retryable=True)
    client = FakeCenterClient()
    runtime = LocalAgentRuntime(
        config=AgentRuntimeConfig(agent_id="agent-1"),
        client=client,
        account_risk=risk,
    )

    asyncio.run(runtime.run_once())

    heartbeat = next(event for event in client.events if event[0] == "heartbeat")
    assert heartbeat[3]["metadata"]["account_risk"]["account-1"]["health_status"] == "cooling_down"


def test_runtime_run_forever_survives_transient_center_request_error(monkeypatch):
    calls = {"count": 0, "sleeps": 0}
    runtime = LocalAgentRuntime(
        config=AgentRuntimeConfig(agent_id="agent-1", poll_interval_seconds=0.01),
        client=FakeCenterClient(),
        poll_backoff=IdlePollBackoff(
            minimum_seconds=0.01,
            maximum_seconds=0.1,
            multiplier=2,
            jitter_ratio=0,
        ),
    )

    async def flaky_run_once():
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ReadError("temporary read error")
        raise asyncio.CancelledError()

    async def fake_sleep(_seconds):
        calls["sleeps"] += 1

    monkeypatch.setattr(runtime, "run_once", flaky_run_once)
    monkeypatch.setattr(runtime_module.asyncio, "sleep", fake_sleep)

    try:
        asyncio.run(runtime.run_forever())
    except asyncio.CancelledError:
        pass

    assert calls == {"count": 2, "sleeps": 1}


def test_runtime_run_forever_resets_idle_backoff_after_work(monkeypatch):
    delays = []
    results = [0, 0, 1]
    calls = {"count": 0}
    runtime = LocalAgentRuntime(
        config=AgentRuntimeConfig(agent_id="agent-1", poll_interval_seconds=2),
        client=FakeCenterClient(),
        poll_backoff=IdlePollBackoff(
            minimum_seconds=2,
            maximum_seconds=10,
            multiplier=2,
            jitter_ratio=0,
        ),
    )

    async def fake_run_once():
        index = calls["count"]
        calls["count"] += 1
        if index >= len(results):
            raise asyncio.CancelledError()
        return results[index]

    async def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(runtime, "run_once", fake_run_once)
    monkeypatch.setattr(runtime_module.asyncio, "sleep", fake_sleep)

    try:
        asyncio.run(runtime.run_forever())
    except asyncio.CancelledError:
        pass

    assert delays == [2, 4, 2]


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


def test_default_capabilities_include_account_posted_notes():
    payload = runtime_module.build_agent_capabilities_payload(AgentRuntimeConfig())
    assert JobType.XHS_ACCOUNT_POSTED_NOTES.value in payload["job_types"]


def test_account_posted_notes_job_ingests_candidates(monkeypatch):
    async def fake_fetch_current(self, page, *, limit=20):
        return XhsCreatorFetchResult(
            creator_platform_id="5f58bd990000000001003753",
            creator_display_name="当前账号",
            items=[
                XhsCreatorItem(
                    platform_content_id="note-1",
                    canonical_url="https://www.xiaohongshu.com/explore/note-1",
                    title_or_summary="已发布笔记",
                    cover_url=None,
                    publish_time=None,
                    xsec_token="token",
                    xsec_source="pc_feed",
                    raw_payload={"note_id": "note-1"},
                )
            ],
            raw_payload={"account_asset_source": "current_account_posted_notes"},
        )

    monkeypatch.setattr(runtime_module.XhsCreatorConnector, "fetch_current_account_posted_notes", fake_fetch_current)
    executor = XhsJobExecutor(client=FakeIngestionClient(), config=AgentRuntimeConfig(agent_id="agent-1"))
    job = ClaimedJobPayload(
        job_id="job-account-posted",
        job_type=JobType.XHS_ACCOUNT_POSTED_NOTES.value,
        account_id="account-1",
        payload={"max_items": 10},
        checkpoint={},
    )

    result = asyncio.run(executor._run_account_posted_notes(job, object()))

    assert result.status == JobStatus.SUCCESS.value
    assert result.checkpoint["items_seen"] == 1
    assert result.result_summary["source_surface"] == SourceSurface.ACCOUNT_POSTED_NOTES.value
    assert result.result_summary["new_content_count"] == 1


def test_account_posted_notes_fallback_reads_profile_link():
    class FakeLocator:
        async def evaluate_all(self, script):
            return [
                {
                    "href": "https://www.xiaohongshu.com/user/profile/613a04fe000000000201d25c?channel_type=web_user_board",
                    "text": "我",
                    "cls": "link-wrapper",
                }
            ]

    class FakePage:
        def locator(self, selector):
            assert selector == 'a[href*="/user/profile/"]'
            return FakeLocator()

    user_id, home_url = asyncio.run(_current_account_profile_from_page(FakePage()))

    assert user_id == "613a04fe000000000201d25c"
    assert home_url.startswith("https://www.xiaohongshu.com/user/profile/")


def test_search_collect_job_uses_search_probe(monkeypatch):
    class FakeSearchProbe:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def collect(self, page):
            return [
                FeedCandidateInput(
                    platform=Platform.XHS,
                    platform_content_id="search-note-1",
                    canonical_url="https://www.xiaohongshu.com/explore/search-note-1",
                    content_type=ContentType.IMAGE_TEXT,
                    title_or_summary="搜索结果",
                    source_surface=SourceSurface.SEARCH,
                    feed_type=FeedType.XHS_HOME_FEED,
                    discovered_at=datetime.now(timezone.utc),
                    raw_payload={"search_keyword": "论文"},
                )
            ], {"searched_keyword_count": 1, "total_items_seen": 1}

    monkeypatch.setattr(runtime_module, "XhsSearchProbe", FakeSearchProbe)
    executor = XhsJobExecutor(client=FakeIngestionClient(), config=AgentRuntimeConfig(agent_id="agent-1"))
    job = ClaimedJobPayload(
        job_id="job-search",
        job_type=JobType.SEARCH_COLLECT.value,
        account_id="account-1",
        payload={"keywords": ["论文"], "max_items": 5},
        checkpoint={},
    )

    result = asyncio.run(executor._run_search_collect(job, object()))

    assert result.status == JobStatus.SUCCESS.value
    assert result.result_summary["new_content_count"] == 1
    assert result.result_summary["detail_jobs_enqueued"] == 1


def test_creator_monitor_fetch_error_maps_to_runtime_failure(monkeypatch):
    async def fail_fetch_latest(self, page, **kwargs):
        raise XhsCreatorFetchError(
            "小红书 user_posted 接口暂时不可用（HTTP 500，jarvis-gateway 创建调用器失败），请稍后重试；这不是对标账号没有笔记。",
            error_code=ErrorCode.RETRYABLE_NETWORK_ERROR.value,
            retryable=True,
            raw_context={"response_meta": {"http_status": 500}},
        )

    monkeypatch.setattr(runtime_module.XhsCreatorConnector, "fetch_latest", fail_fetch_latest)
    executor = XhsJobExecutor(client=FakeIngestionClient(), config=AgentRuntimeConfig(agent_id="agent-1"))
    job = ClaimedJobPayload(
        job_id="job-creator",
        job_type=JobType.CREATOR_MONITOR.value,
        account_id="account-1",
        payload={"creator_monitor_id": "monitor-1"},
        checkpoint={},
    )

    try:
        asyncio.run(executor._run_creator_monitor(job, object()))
    except RuntimeFailure as exc:
        assert exc.code == ErrorCode.RETRYABLE_NETWORK_ERROR
        assert exc.retryable is True
        assert exc.raw_context["response_meta"]["http_status"] == 500
    else:
        raise AssertionError("expected RuntimeFailure")


def test_creator_monitor_public_id_resolution_failure_maps_to_runtime_failure(monkeypatch):
    async def fail_resolve_public_id(self, page, **kwargs):
        raise XhsCreatorFetchError(
            "未能通过小红书号找到对标账号主页：1479543583",
            error_code=ErrorCode.CREATOR_NOT_FOUND.value,
            retryable=False,
            raw_context={"public_identifier": "1479543583"},
        )

    monkeypatch.setattr(runtime_module.XhsCreatorConnector, "fetch_latest", fail_resolve_public_id)
    executor = XhsJobExecutor(client=FakeIngestionClient(), config=AgentRuntimeConfig(agent_id="agent-1"))
    job = ClaimedJobPayload(
        job_id="job-creator",
        job_type=JobType.CREATOR_MONITOR.value,
        account_id="account-1",
        payload={"creator_monitor_id": "monitor-1", "creator_platform_id": "1479543583"},
        checkpoint={},
    )

    try:
        asyncio.run(executor._run_creator_monitor(job, object()))
    except RuntimeFailure as exc:
        assert exc.code == ErrorCode.CREATOR_NOT_FOUND
        assert exc.retryable is False
        assert exc.raw_context["public_identifier"] == "1479543583"
    else:
        raise AssertionError("expected RuntimeFailure")


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


def test_feed_summary_counts_missing_like_detail_jobs(monkeypatch):
    candidates = [
        FeedCandidateInput(
            platform=Platform.XHS,
            platform_content_id="with-like",
            canonical_url="https://x.test/with-like",
            content_type=ContentType.IMAGE_TEXT,
            title_or_summary="有点赞",
            visible_like_count=12,
            source_surface=SourceSurface.XHS_HOME_FEED,
            feed_type=FeedType.XHS_HOME_FEED,
            feed_position=1,
            discovered_at=datetime.now(timezone.utc),
        ),
        FeedCandidateInput(
            platform=Platform.XHS,
            platform_content_id="missing-like",
            canonical_url="https://x.test/missing-like",
            content_type=ContentType.IMAGE_TEXT,
            title_or_summary="待补点赞",
            visible_like_count=None,
            source_surface=SourceSurface.XHS_HOME_FEED,
            feed_type=FeedType.XHS_HOME_FEED,
            feed_position=2,
            discovered_at=datetime.now(timezone.utc),
        ),
    ]

    class FakeProbe:
        def __init__(self, *, target_count):
            self.target_count = target_count

        async def collect(self, page):
            return candidates, {"target_count": self.target_count, "actual_count": len(candidates)}

    monkeypatch.setattr(runtime_module, "XhsHomeFeedProbe", FakeProbe)
    executor = XhsJobExecutor(client=FakeIngestionClient(), config=AgentRuntimeConfig())
    job = ClaimedJobPayload(job_id="feed-job", job_type=JobType.FEED_COLLECT.value, account_id="account-1", payload={"target_count": 2}, checkpoint={})

    result = asyncio.run(executor._run_feed(job, page=object()))

    assert result.result_summary["missing_visible_like_count"] == 1
    assert result.result_summary["missing_visible_like_detail_jobs_enqueued"] == 1
    assert result.result_summary["detail_jobs_enqueued"] == 1
