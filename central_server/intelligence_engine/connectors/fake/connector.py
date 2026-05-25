from datetime import datetime, timedelta, timezone

from intelligence_engine.connectors.base.models import CommentSnapshot, DetailSnapshot, FeedCandidate
from intelligence_engine.domain.enums import ContentType, FeedType, Platform, SourceSurface


class FakeConnector:
    def collect_feed(self, *, platform: Platform, feed_type: FeedType, target_count: int) -> list[FeedCandidate]:
        now = datetime.now(timezone.utc)
        candidates: list[FeedCandidate] = []
        for index in range(target_count):
            content_type = ContentType.VIDEO if feed_type == FeedType.DOUYIN_VIDEO_HOME_FEED else ContentType.IMAGE_TEXT
            platform_content_id = f"{platform.value}-{feed_type.value}-{index:03d}"
            title = f"SCI论文投稿经验 {index}" if index % 5 == 0 else f"运营内容样本 {index}"
            candidates.append(
                FeedCandidate(
                    platform=platform,
                    platform_content_id=platform_content_id,
                    canonical_url=f"https://fake.local/{platform.value}/{platform_content_id}",
                    content_type=content_type,
                    title_or_summary=title,
                    cover_url=f"https://fake.local/covers/{platform_content_id}.jpg",
                    author_platform_id=f"author-{index % 7}",
                    author_name=f"作者{index % 7}",
                    visible_like_count=100 + index * 20,
                    source_surface=SourceSurface(feed_type.value),
                    feed_type=feed_type,
                    feed_position=index + 1,
                    discovered_at=now + timedelta(seconds=index),
                    raw_payload={"fake": True, "index": index},
                )
            )
        return candidates

    def fetch_detail(self, *, platform: Platform, platform_content_id: str) -> DetailSnapshot:
        now = datetime.now(timezone.utc)
        index = int(platform_content_id.rsplit("-", 1)[-1])
        title = f"SCI论文投稿与期刊发表案例 {index}" if index % 5 == 0 else f"内容详情样本 {index}"
        body = "这是一条假详情，用于跑通引擎骨架。包含论文、投稿、期刊等关键词。" if index % 5 == 0 else "普通内容详情。"
        return DetailSnapshot(
            title=title,
            body_text=body,
            author_platform_id=f"author-{index % 7}",
            author_name=f"作者{index % 7}",
            cover_url=f"https://fake.local/covers/{platform_content_id}.jpg",
            image_urls=[f"https://fake.local/images/{platform_content_id}-1.jpg"],
            video_url=f"https://fake.local/videos/{platform_content_id}.mp4" if platform == Platform.DOUYIN else None,
            like_count=100 + index * 20,
            comment_count=5 + index,
            collect_count=index,
            share_count=index // 2,
            publish_time=now - timedelta(days=index % 10),
            raw_payload={"fake": True, "detail_for": platform_content_id},
        )

    def fetch_comments(self, *, platform_content_id: str, limit: int = 20) -> list[CommentSnapshot]:
        comments: list[CommentSnapshot] = []
        for index in range(limit):
            body = "求推荐，怎么联系" if index in {0, 7} else f"评论样本 {index}"
            comments.append(
                CommentSnapshot(
                    platform_comment_id=f"{platform_content_id}-comment-{index:02d}",
                    author_platform_id=f"commenter-{index}",
                    author_name=f"评论者{index}",
                    body_text=body,
                    like_count=index,
                    created_time=datetime.now(timezone.utc) - timedelta(minutes=index),
                    raw_payload={"fake": True, "index": index},
                )
            )
        return comments

    def fetch_creator_latest(self, *, platform: Platform, creator_platform_id: str, max_items: int = 3) -> list[FeedCandidate]:
        feed_type = FeedType.XHS_HOME_FEED if platform == Platform.XHS else FeedType.DOUYIN_VIDEO_HOME_FEED
        source_surface = SourceSurface.CREATOR_MONITOR
        now = datetime.now(timezone.utc)
        items: list[FeedCandidate] = []
        for index in range(max_items):
            platform_content_id = f"{platform.value}-creator-{creator_platform_id}-{index:03d}"
            items.append(
                FeedCandidate(
                    platform=platform,
                    platform_content_id=platform_content_id,
                    canonical_url=f"https://fake.local/{platform.value}/creator/{creator_platform_id}/{index}",
                    content_type=ContentType.IMAGE_TEXT if platform == Platform.XHS else ContentType.VIDEO,
                    title_or_summary=f"对标账号新作品 SCI投稿线索 {index}",
                    cover_url=f"https://fake.local/covers/{platform_content_id}.jpg",
                    author_platform_id=creator_platform_id,
                    author_name=f"对标账号{creator_platform_id}",
                    visible_like_count=800 + index,
                    source_surface=source_surface,
                    feed_type=feed_type,
                    feed_position=index + 1,
                    discovered_at=now + timedelta(seconds=index),
                    raw_payload={"fake": True, "creator_platform_id": creator_platform_id, "index": index},
                )
            )
        return items
