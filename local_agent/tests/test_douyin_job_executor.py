import asyncio
from datetime import datetime, timezone

import local_agent_runtime.executors.douyin as douyin_executor_module
from local_agent_runtime.runtime import (
    AgentRuntimeConfig,
    ClaimedJobPayload,
    DouyinJobExecutor,
    PlatformJobExecutor,
)
from local_agent_runtime.contracts import FeedCandidateInput
from local_agent_runtime.enums import ContentType, JobStatus, JobType, Platform, SourceSurface


class FakeSession:
    def __init__(self, status):
        from local_agent_runtime.enums import SessionStatus

        self.status = status if not isinstance(status, str) else SessionStatus(status)
        self.page = object()
        self.message = "ok"
        self.closed = False

    async def close(self):
        self.closed = True


class FakeProvider:
    def __init__(self, session):
        self._session = session

    async def acquire(self, *, session_meta):
        self._session.acquired_meta = session_meta
        return self._session


class FakeRegistry:
    def __init__(self, session):
        self.provider = FakeProvider(session)
        self.created_for = []

    def create(self, platform):
        self.created_for.append(platform)
        return self.provider


class FakeIngestionClient:
    def __init__(self):
        self.ingested = []
        self.suggestions = []
        self.details = []
        self.comments = []
        self.creators = []

    async def ingest_feed_candidates(self, payload):
        self.ingested.append(payload)
        return {"results": [{"platform_content_id": c.platform_content_id, "is_new_content": True} for c in payload.candidates]}

    async def ingest_search_suggestions(self, payload):
        self.suggestions.append(payload)
        return {"inserted": len(payload.get("items") or [])}

    async def get_ready_session(self, account_id, agent_id):
        return {}

    async def ingest_detail(self, payload):
        self.details.append(payload)
        return {"snapshot_id": "snapshot-1", "comment_job_enqueued": True}

    async def ingest_comments(self, payload):
        self.comments.append(payload)
        return {"inserted": len(payload.comments), "updated": 0, "lead_keyword_hits": 1}

    async def ingest_creator_monitor_items(self, payload):
        self.creators.append(payload)
        return {"items_seen": len(payload.items), "new_content_count": len(payload.items)}


def _candidate(cid):
    return FeedCandidateInput(
        platform=Platform.DOUYIN,
        platform_content_id=cid,
        canonical_url=f"https://www.douyin.com/video/{cid}",
        content_type=ContentType.VIDEO,
        title_or_summary="t",
        source_surface=SourceSurface.SEARCH,
        discovered_at=datetime.now(timezone.utc),
    )


def _patch_probe(monkeypatch, captured):
    class FakeProbe:
        def __init__(self, **kwargs):
            captured.append(kwargs)

        async def collect(self, page):
            return [_candidate("111"), _candidate("222")], {"intercepted_responses": 1, "filter_apply_status": "url_params"}

    monkeypatch.setattr(douyin_executor_module, "DouyinFeedProbe", FakeProbe)


def test_douyin_executor_runs_search_collect(monkeypatch):
    from local_agent_runtime.enums import SessionStatus

    captured = []
    _patch_probe(monkeypatch, captured)
    session = FakeSession(SessionStatus.READY)
    client = FakeIngestionClient()
    executor = DouyinJobExecutor(
        client=client,
        config=AgentRuntimeConfig(cdp_url="http://127.0.0.1:9223"),
        session_registry=FakeRegistry(session),
    )
    job = ClaimedJobPayload(
        job_id="dy-1",
        job_type=JobType.SEARCH_COLLECT.value,
        account_id=None,
        payload={"platform": "douyin", "keywords": ["SCI论文"], "sort": "most_liked", "start_rank": 5, "max_items": 10},
        checkpoint={},
    )

    result = asyncio.run(executor.execute(agent_id="agent-1", job=job))

    assert result.status == JobStatus.SUCCESS.value
    assert result.result_summary["normalized_items"] == 2
    assert result.result_summary["sort"] == "most_liked"
    assert captured[0]["sort"] == "most_liked"
    assert captured[0]["start_rank"] == 5
    assert session.closed is True
    assert len(client.ingested) == 1


def test_douyin_executor_runs_homefeed(monkeypatch):
    from local_agent_runtime.enums import SessionStatus

    captured = []
    _patch_probe(monkeypatch, captured)
    session = FakeSession(SessionStatus.READY)
    client = FakeIngestionClient()
    executor = DouyinJobExecutor(
        client=client,
        config=AgentRuntimeConfig(cdp_url="http://127.0.0.1:9223"),
        session_registry=FakeRegistry(session),
    )
    job = ClaimedJobPayload(
        job_id="dy-feed",
        job_type=JobType.FEED_COLLECT.value,
        account_id=None,
        payload={"platform": "douyin", "max_items": 20, "start_rank": 3},
        checkpoint={},
    )

    result = asyncio.run(executor.execute(agent_id="agent-1", job=job))

    assert result.status == JobStatus.SUCCESS.value
    assert result.result_summary["normalized_items"] == 2
    assert result.result_summary["start_rank"] == 3
    # homefeed mode must not pass a keyword to the probe.
    assert captured[0]["keyword"] is None
    assert captured[0]["target_count"] == 20
    assert captured[0]["start_rank"] == 3
    assert len(client.ingested) == 1
    assert session.closed is True


def test_douyin_executor_runs_search_suggest(monkeypatch):
    from local_agent_runtime.enums import SessionStatus

    class FakeSuggestProbe:
        def __init__(self, *, core_keyword, **kwargs):
            self.core_keyword = core_keyword

        async def collect(self, page):
            items = [
                {"core_keyword": self.core_keyword, "suggested_keyword": "sci论文怎么写", "suggestion_rank": 1, "raw_payload": {}, "fetched_at": "t"},
                {"core_keyword": self.core_keyword, "suggested_keyword": "sci论文辅导", "suggestion_rank": 2, "raw_payload": {}, "fetched_at": "t"},
            ]
            return items, {"intercepted_responses": 1, "suggestion_count": 2, "typed_selector": "input"}

    monkeypatch.setattr(douyin_executor_module, "DouyinSearchSuggestProbe", FakeSuggestProbe)
    session = FakeSession(SessionStatus.READY)
    client = FakeIngestionClient()
    executor = DouyinJobExecutor(
        client=client,
        config=AgentRuntimeConfig(cdp_url="http://127.0.0.1:9223"),
        session_registry=FakeRegistry(session),
    )
    job = ClaimedJobPayload(
        job_id="dy-sug",
        job_type=JobType.SEARCH_SUGGEST.value,
        account_id=None,
        payload={"platform": "douyin", "core_keyword": "SCI论文"},
        checkpoint={},
    )

    result = asyncio.run(executor.execute(agent_id="agent-1", job=job))
    assert result.status == JobStatus.SUCCESS.value
    assert result.result_summary["suggestion_count"] == 2
    assert result.result_summary["ingestion_status"] == "ok"
    assert len(client.suggestions) == 1
    assert client.suggestions[0]["platform"] == "douyin"
    assert session.closed is True


def test_douyin_executor_runs_detail_fetch(monkeypatch):
    from local_agent_runtime.enums import SessionStatus

    class FakeDetailProbe:
        async def fetch_detail(self, page, **kwargs):
            from local_agent_runtime.contracts import DetailSnapshotInput
            return DetailSnapshotInput(title="详情", raw_payload={"diagnostics": {"fetch_source": "xhr_intercept"}})

    monkeypatch.setattr(douyin_executor_module, "DouyinDetailProbe", FakeDetailProbe)
    session = FakeSession(SessionStatus.READY)
    client = FakeIngestionClient()
    executor = DouyinJobExecutor(
        client=client,
        config=AgentRuntimeConfig(cdp_url="http://127.0.0.1:9223"),
        session_registry=FakeRegistry(session),
    )
    job = ClaimedJobPayload(
        job_id="dy-2",
        job_type=JobType.DETAIL_FETCH.value,
        account_id=None,
        payload={"platform": "douyin", "content_id": "content-1", "platform_content_id": "aweme-1"},
        checkpoint={},
    )

    result = asyncio.run(executor.execute(agent_id="agent-1", job=job))
    assert result.status == JobStatus.SUCCESS.value
    assert result.result_summary["snapshot_id"] == "snapshot-1"
    assert len(client.details) == 1


def test_douyin_executor_runs_comment_fetch(monkeypatch):
    from local_agent_runtime.enums import SessionStatus
    from local_agent_runtime.connectors.douyin.comment_probe import DouyinCommentFetchResult
    from local_agent_runtime.contracts import CommentSnapshotInput

    class FakeCommentProbe:
        async def fetch_comments_result(self, page, **kwargs):
            return DouyinCommentFetchResult(
                comments=[CommentSnapshotInput(platform_comment_id="c-1", body_text="怎么买")],
                surface_status="ok",
            )

    monkeypatch.setattr(douyin_executor_module, "DouyinCommentProbe", FakeCommentProbe)
    session = FakeSession(SessionStatus.READY)
    client = FakeIngestionClient()
    executor = DouyinJobExecutor(
        client=client,
        config=AgentRuntimeConfig(cdp_url="http://127.0.0.1:9223"),
        session_registry=FakeRegistry(session),
    )
    job = ClaimedJobPayload(
        job_id="dy-comment",
        job_type=JobType.COMMENT_FETCH.value,
        account_id=None,
        payload={"platform": "douyin", "content_id": "content-1", "platform_content_id": "aweme-1"},
        checkpoint={},
    )

    result = asyncio.run(executor.execute(agent_id="agent-1", job=job))
    assert result.status == JobStatus.SUCCESS.value
    assert result.result_summary["comments_inserted"] == 1
    assert len(client.comments) == 1


def test_douyin_executor_runs_creator_monitor(monkeypatch):
    from local_agent_runtime.enums import SessionStatus
    from local_agent_runtime.connectors.douyin.creator_probe import DouyinCreatorFetchResult

    class FakeCreatorProbe:
        async def fetch_latest(self, page, **kwargs):
            return DouyinCreatorFetchResult(
                creator_platform_id="sec-1",
                creator_display_name="作者",
                items=[_candidate("aweme-1")],
                profile={"follower_count": 100},
                raw_payload={"source_path": "user_posts_response_intercept"},
            )

    monkeypatch.setattr(douyin_executor_module, "DouyinCreatorProbe", FakeCreatorProbe)
    session = FakeSession(SessionStatus.READY)
    client = FakeIngestionClient()
    executor = DouyinJobExecutor(
        client=client,
        config=AgentRuntimeConfig(cdp_url="http://127.0.0.1:9223"),
        session_registry=FakeRegistry(session),
    )
    job = ClaimedJobPayload(
        job_id="dy-creator",
        job_type=JobType.CREATOR_MONITOR.value,
        account_id=None,
        payload={"platform": "douyin", "creator_monitor_id": "monitor-1", "creator_platform_id": "sec-1"},
        checkpoint={},
    )

    result = asyncio.run(executor.execute(agent_id="agent-1", job=job))
    assert result.status == JobStatus.SUCCESS.value
    assert result.result_summary["creator_platform_id"] == "sec-1"
    assert len(client.creators) == 1


def test_platform_dispatch_routes_to_douyin(monkeypatch):
    from local_agent_runtime.enums import SessionStatus

    captured = []
    _patch_probe(monkeypatch, captured)
    session = FakeSession(SessionStatus.READY)
    registry = FakeRegistry(session)
    dispatcher = PlatformJobExecutor(
        client=FakeIngestionClient(),
        config=AgentRuntimeConfig(cdp_url="http://127.0.0.1:9223"),
        session_registry=registry,
    )
    job = ClaimedJobPayload(
        job_id="dy-3",
        job_type=JobType.SEARCH_COLLECT.value,
        account_id=None,
        payload={"platform": "douyin", "keywords": ["考研"]},
        checkpoint={},
    )

    result = asyncio.run(dispatcher.execute(agent_id="agent-1", job=job))
    assert result.status == JobStatus.SUCCESS.value
    assert Platform.DOUYIN.value in registry.created_for


def test_platform_dispatch_unknown_platform():
    dispatcher = PlatformJobExecutor(client=FakeIngestionClient(), config=AgentRuntimeConfig())
    job = ClaimedJobPayload(
        job_id="x-1",
        job_type=JobType.SEARCH_COLLECT.value,
        account_id=None,
        payload={"platform": "weibo"},
        checkpoint={},
    )
    result = asyncio.run(dispatcher.execute(agent_id="agent-1", job=job))
    assert result.status == JobStatus.PARTIAL_SUCCESS.value
    assert result.result_summary["unsupported_platform"] == "weibo"
