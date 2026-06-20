import asyncio
from datetime import datetime, timezone

import pytest

from local_agent_runtime.contracts import (
    CommentIngestionRequest,
    CommentSnapshotInput,
    DetailIngestionRequest,
    DetailSnapshotInput,
    FeedCandidateIngestionRequest,
    FeedCandidateInput,
)
from local_agent_runtime.enums import ContentType, Platform, SourceSurface
from local_agent_runtime.storage import LocalFirstIngestionGateway, LocalIntelligenceRepository


def _candidate(*, like_count=10):
    return FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="note-1",
        canonical_url="https://www.xiaohongshu.com/explore/note-1",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="本地优先测试",
        cover_url="https://img.example/cover.jpg",
        author_platform_id="creator-1",
        author_name="测试作者",
        visible_like_count=like_count,
        source_surface=SourceSurface.SEARCH,
        discovered_at=datetime.now(timezone.utc),
        raw_payload={"search_keyword": "本地优先"},
    )


def test_local_repository_initializes_all_p2_tables(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")

    for table in (
        "creator",
        "content",
        "content_source",
        "comment_hit",
        "search_suggestion",
        "collect_task",
        "collect_run",
        "ingestion_outbox",
        "material_export",
        "local_setting",
    ):
        assert repository.table_count(table) == 0


def test_local_setting_persists_across_repository_instances(tmp_path):
    database_path = tmp_path / "local.db"
    repository = LocalIntelligenceRepository(database_path)
    repository.set_setting("central_server_url", "https://operations.example.com")

    reopened = LocalIntelligenceRepository(database_path)

    assert reopened.get_setting("central_server_url") == "https://operations.example.com"


def test_feed_upsert_deduplicates_content_and_updates_metrics(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    first = FeedCandidateIngestionRequest(job_id="job-1", account_id="account-1", candidates=[_candidate(like_count=10)])
    second = FeedCandidateIngestionRequest(job_id="job-2", account_id="account-1", candidates=[_candidate(like_count=25)])

    first_result = repository.upsert_feed_candidates(first)
    second_result = repository.upsert_feed_candidates(second)

    assert first_result[0]["is_new_content"] is True
    assert second_result[0]["is_new_content"] is False
    assert repository.table_count("content") == 1
    assert repository.table_count("creator") == 1
    assert repository.table_count("content_source") == 1
    assert repository.get_content(platform="xhs", platform_content_id="note-1")["like_count"] == 25
    assert repository.get_content(platform="xhs", platform_content_id="note-1")["processing_status"] == "pending"


def test_content_processing_status_is_persistent_and_not_overwritten_by_recollect(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    request = FeedCandidateIngestionRequest(job_id="job-1", candidates=[_candidate()])
    repository.upsert_feed_candidates(request)
    content_id = repository.get_content(platform="xhs", platform_content_id="note-1")["id"]

    assert repository.update_content_processing_status(
        content_ids=[content_id],
        status="discarded",
    ) == 1
    repository.upsert_feed_candidates(
        FeedCandidateIngestionRequest(job_id="job-2", candidates=[_candidate(like_count=99)])
    )

    content = repository.get_content(platform="xhs", platform_content_id="note-1")
    assert content["processing_status"] == "discarded"
    assert content["like_count"] == 99
    discarded = repository.list_contents(processing_status="discarded")
    pending = repository.list_contents(processing_status="pending")
    assert discarded["total"] == 1
    assert pending["total"] == 0


def test_queue_material_marks_content_as_material(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    repository.upsert_feed_candidates(
        FeedCandidateIngestionRequest(job_id="job-1", candidates=[_candidate()])
    )
    content_id = repository.get_content(platform="xhs", platform_content_id="note-1")["id"]

    repository.queue_material_export(
        content_id=content_id,
        library_type="uncategorized",
        rating=None,
        material_tags=[],
        note=None,
        selected_reason="test",
    )

    assert repository.get_content_detail(content_id)["processing_status"] == "material"


def test_feed_upsert_preserves_search_card_images(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    candidate = _candidate()
    candidate.raw_payload = {
        "search_keyword": "本地优先",
        "api_raw": {
            "model_type": "note",
            "note_card": {
                "image_list": [
                    {"info_list": [{"url": "https://img.example/1.webp"}]},
                    {"info_list": [{"url": "https://img.example/2.webp"}]},
                ]
            },
        },
    }

    repository.upsert_feed_candidates(
        FeedCandidateIngestionRequest(job_id="job-images", candidates=[candidate])
    )

    detail = repository.get_content_detail(
        repository.get_content(platform="xhs", platform_content_id="note-1")["id"]
    )
    assert detail["image_urls"] == [
        "https://img.example/1.webp",
        "https://img.example/2.webp",
    ]


def test_detail_and_comment_hits_update_existing_local_content(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    repository.upsert_feed_candidates(
        FeedCandidateIngestionRequest(job_id="job-feed", account_id="account-1", candidates=[_candidate()])
    )
    repository.apply_central_content_mappings(
        [{"platform": "xhs", "platform_content_id": "note-1", "content_id": "central-1"}]
    )

    local_content_id = repository.upsert_detail(
        DetailIngestionRequest(
            job_id="job-detail",
            content_id="central-1",
            snapshot=DetailSnapshotInput(
                title="完整标题",
                body_text="完整正文",
                like_count=30,
                comment_count=2,
                image_urls=["https://img.example/1.jpg"],
            ),
        )
    )
    result = repository.upsert_comments(
        CommentIngestionRequest(
            job_id="job-comments",
            content_id="central-1",
            comments=[
                CommentSnapshotInput(
                    platform_comment_id="comment-1",
                    body_text="请问怎么买，多少钱？",
                    author_name="潜在客户",
                ),
                CommentSnapshotInput(
                    platform_comment_id="comment-2",
                    body_text="普通评论",
                    author_name="路人",
                ),
            ],
        )
    )

    content = repository.get_content(platform="xhs", platform_content_id="note-1")
    assert local_content_id == content["id"]
    assert content["title"] == "完整标题"
    assert content["body_text"] == "完整正文"
    assert content["acquisition_hit_count"] == 1
    assert result == {"inserted": 2, "updated": 0}
    assert repository.table_count("comment_hit") == 2

    listing = repository.list_contents(keyword="完整", platform="xhs", source_type="search")
    assert listing["total"] == 1
    assert listing["items"][0]["platform_content_id"] == "note-1"
    detail = repository.get_content_detail(content["id"])
    assert detail["body_text"] == "完整正文"
    assert detail["sources"][0]["source_type"] == "search"
    assert len(detail["comment_hits"]) == 2


def test_detail_fetch_does_not_change_content_list_order(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    older = _candidate()
    older.platform_content_id = "older-note"
    older.title_or_summary = "较早采集"
    older.discovered_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = _candidate()
    newer.platform_content_id = "newer-note"
    newer.title_or_summary = "较晚采集"
    newer.discovered_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    repository.upsert_feed_candidates(
        FeedCandidateIngestionRequest(job_id="stable-order", candidates=[older, newer])
    )
    before = [item["platform_content_id"] for item in repository.list_contents()["items"]]

    repository.upsert_detail(
        DetailIngestionRequest(
            job_id="older-detail",
            content_id="older-note",
            snapshot=DetailSnapshotInput(
                body_text="补抓正文",
                publish_time=datetime(2026, 6, 20, tzinfo=timezone.utc),
                raw_payload={"platform_content_id": "older-note"},
            ),
        )
    )

    after = [item["platform_content_id"] for item in repository.list_contents()["items"]]
    assert before == ["newer-note", "older-note"]
    assert after == before


def test_search_suggestions_are_upserted(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    payload = {
        "platform": "douyin",
        "core_keyword": "考研",
        "items": [
            {"suggested_keyword": "考研复习规划", "suggestion_rank": 1},
            {"suggested_keyword": "考研复习规划", "suggestion_rank": 2},
        ],
    }

    assert repository.upsert_search_suggestions(payload, default_platform="xhs") == 2
    assert repository.table_count("search_suggestion") == 1


def test_collect_run_tracks_retry_and_terminal_status(tmp_path):
    repository = LocalIntelligenceRepository(tmp_path / "local.db")

    repository.start_collect_run(central_job_id="job-1", job_type="search_collect")
    repository.finish_collect_run(
        central_job_id="job-1",
        status="failed",
        error_summary={"code": "temporary"},
    )
    repository.start_collect_run(central_job_id="job-1", job_type="search_collect")
    repository.finish_collect_run(
        central_job_id="job-1",
        status="success",
        item_count=12,
    )

    run = repository.get_collect_run("job-1")
    assert run["status"] == "success"
    assert run["attempts"] == 2
    assert run["item_count"] == 12


def test_gateway_persists_before_remote_failure_and_records_outbox(tmp_path):
    class FailingRemote:
        async def ingest_feed_candidates(self, payload):
            raise RuntimeError("central unavailable")

    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    gateway = LocalFirstIngestionGateway(remote=FailingRemote(), repository=repository)
    payload = FeedCandidateIngestionRequest(
        job_id="job-offline",
        account_id="account-1",
        candidates=[_candidate()],
    )

    with pytest.raises(RuntimeError, match="central unavailable"):
        asyncio.run(gateway.ingest_feed_candidates(payload))

    assert repository.table_count("content") == 1
    assert repository.table_count("ingestion_outbox") == 1


def test_gateway_replays_pending_outbox(tmp_path):
    class RecoveringRemote:
        def __init__(self):
            self.available = False
            self.calls = 0

        async def ingest_feed_candidates(self, payload):
            self.calls += 1
            if not self.available:
                raise RuntimeError("central unavailable")
            return {
                "results": [
                    {
                        "platform": "xhs",
                        "platform_content_id": payload.candidates[0].platform_content_id,
                        "content_id": "central-1",
                    }
                ]
            }

    repository = LocalIntelligenceRepository(tmp_path / "local.db")
    remote = RecoveringRemote()
    gateway = LocalFirstIngestionGateway(remote=remote, repository=repository)
    payload = FeedCandidateIngestionRequest(
        job_id="job-replay",
        account_id="account-1",
        candidates=[_candidate()],
    )

    with pytest.raises(RuntimeError):
        asyncio.run(gateway.ingest_feed_candidates(payload))
    remote.available = True
    replay = asyncio.run(gateway.flush_pending_outbox())

    content = repository.get_content(platform="xhs", platform_content_id="note-1")
    assert replay == {"sent": 1, "failed": 0}
    assert content["central_content_id"] == "central-1"
    with repository.connection() as connection:
        status = connection.execute("SELECT status FROM ingestion_outbox").fetchone()[0]
    assert status == "sent"
