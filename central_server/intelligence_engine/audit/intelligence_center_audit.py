from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from intelligence_engine.db.models import (
    CommentSnapshot,
    ContentDiscoveryEvent,
    ContentIdentity,
    ContentSnapshot,
    ContentWorkflowState,
    Job,
    PlatformAccount,
    ReferenceLibraryItem,
)
from intelligence_engine.domain.enums import ContentDataStatus, JobStatus, JobType, SourceSurface
from intelligence_engine.domain.intelligence_pool import (
    derive_data_status,
    extract_manual_tags,
    extract_platform_tags,
    extract_search_tags,
)


SEARCH_CONTEXT_FIELDS = (
    "search_keyword",
    "core_keyword",
    "search_sort",
    "note_type",
    "publish_time",
    "search_scope",
    "location_filter",
    "search_rank",
)

KNOWN_SOURCE_SURFACES = {
    SourceSurface.XHS_HOME_FEED.value,
    SourceSurface.DOUYIN_VIDEO_HOME_FEED.value,
    SourceSurface.DOUYIN_IMAGE_HOME_FEED.value,
    SourceSurface.SEARCH.value,
    SourceSurface.CREATOR_MONITOR.value,
    SourceSurface.ACCOUNT_POSTED_NOTES.value,
    SourceSurface.MANUAL_IMPORT.value,
}

FEED_SOURCE_SURFACES = {
    SourceSurface.XHS_HOME_FEED.value,
    SourceSurface.DOUYIN_VIDEO_HOME_FEED.value,
    SourceSurface.DOUYIN_IMAGE_HOME_FEED.value,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _meta_value(meta: dict[str, Any] | None, *keys: str) -> Any:
    if not meta:
        return None
    for key in keys:
        value = meta.get(key)
        if value not in (None, "", [], {}):
            return value
    raw = meta.get("raw_payload")
    if isinstance(raw, dict):
        for key in keys:
            value = raw.get(key)
            if value not in (None, "", [], {}):
                return value
    return None


def _content_status_row(db: Session, content: ContentIdentity) -> dict[str, Any]:
    comment_count = db.scalar(select(func.count(CommentSnapshot.id)).where(CommentSnapshot.content_id == content.id)) or 0
    metadata = content.metadata_json or {}
    flags = metadata.get("enrichment_flags") if isinstance(metadata.get("enrichment_flags"), dict) else {}
    return {
        "content_id": content.id,
        "latest_snapshot_id": content.latest_snapshot_id,
        "comment_snapshot_count": comment_count,
        "detail_fetch_failed": bool(flags.get("detail_failed")),
        "comment_fetch_failed": bool(flags.get("comment_failed")),
    }


def _derive_for_content(db: Session, content: ContentIdentity) -> str:
    row = _content_status_row(db, content)
    return derive_data_status(
        latest_snapshot_id=row["latest_snapshot_id"],
        comment_snapshot_count=row["comment_snapshot_count"],
        detail_fetch_failed=row["detail_fetch_failed"],
        comment_fetch_failed=row["comment_fetch_failed"],
    )


def _top_counter(items: list[str], limit: int = 50) -> list[dict[str, Any]]:
    counter = Counter(items)
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def audit_pool_totals(db: Session) -> dict[str, int]:
    return {
        "content_identity_total": db.scalar(select(func.count(ContentIdentity.id))) or 0,
        "discovery_event_total": db.scalar(select(func.count(ContentDiscoveryEvent.id))) or 0,
        "snapshot_total": db.scalar(select(func.count(ContentSnapshot.id))) or 0,
        "comment_snapshot_total": db.scalar(select(func.count(CommentSnapshot.id))) or 0,
        "workflow_state_total": db.scalar(select(func.count(ContentWorkflowState.id))) or 0,
        "reference_library_items_total": db.scalar(select(func.count(ReferenceLibraryItem.id))) or 0,
    }


def audit_data_status_distribution(db: Session) -> dict[str, Any]:
    contents = list(db.scalars(select(ContentIdentity)))
    distribution = Counter(_derive_for_content(db, content) for content in contents)
    samples: list[dict[str, Any]] = []
    by_status: dict[str, list[ContentIdentity]] = defaultdict(list)
    for content in contents:
        by_status[_derive_for_content(db, content)].append(content)
    for status in (
        ContentDataStatus.CARD_ONLY.value,
        ContentDataStatus.DETAIL_READY.value,
        ContentDataStatus.COMMENTS_READY.value,
        ContentDataStatus.DETAIL_FAILED.value,
        ContentDataStatus.COMMENTS_FAILED.value,
    ):
        for content in by_status.get(status, [])[:4]:
            row = _content_status_row(db, content)
            samples.append(
                {
                    "content_id": content.id,
                    "expected_status": status,
                    "derived_status": status,
                    "latest_snapshot_id": row["latest_snapshot_id"],
                    "comment_snapshot_count": row["comment_snapshot_count"],
                    "detail_fetch_failed": row["detail_fetch_failed"],
                    "comment_fetch_failed": row["comment_fetch_failed"],
                    "match": True,
                }
            )
    samples = samples[:20]
    return {
        "distribution": dict(distribution),
        "sample_validation": samples,
        "sample_size": len(samples),
    }


def audit_source_distribution(db: Session) -> dict[str, Any]:
    rows = list(
        db.execute(
            select(ContentDiscoveryEvent.source_surface, func.count(ContentDiscoveryEvent.id)).group_by(ContentDiscoveryEvent.source_surface)
        )
    )
    by_surface = {surface or "unknown": count for surface, count in rows}
    feed_count = sum(by_surface.get(key, 0) for key in FEED_SOURCE_SURFACES)
    search_count = by_surface.get(SourceSurface.SEARCH.value, 0)
    creator_count = by_surface.get(SourceSurface.CREATOR_MONITOR.value, 0)
    unknown_count = sum(count for surface, count in by_surface.items() if surface not in KNOWN_SOURCE_SURFACES)

    inconsistent: list[dict[str, Any]] = []
    events = list(db.scalars(select(ContentDiscoveryEvent).order_by(ContentDiscoveryEvent.discovered_at.desc()).limit(500)))
    for event in events:
        meta = event.discovery_meta_json or {}
        job = db.get(Job, event.job_id) if event.job_id else None
        job_type = job.job_type if job else None
        issues: list[str] = []
        if not event.source_surface:
            issues.append("missing_source_surface")
        if event.source_surface == SourceSurface.SEARCH.value and not _meta_value(meta, "search_keyword"):
            issues.append("search_source_missing_keyword")
        if job_type == JobType.SEARCH_COLLECT.value and event.source_surface != SourceSurface.SEARCH.value:
            issues.append("search_job_non_search_surface")
        if job_type == JobType.FEED_COLLECT.value and event.source_surface not in FEED_SOURCE_SURFACES:
            issues.append("feed_job_unexpected_surface")
        if job_type == JobType.XHS_ACCOUNT_POSTED_NOTES.value and event.source_surface != SourceSurface.ACCOUNT_POSTED_NOTES.value:
            issues.append("account_posted_job_unexpected_surface")
        if issues:
            inconsistent.append(
                {
                    "event_id": event.id,
                    "content_id": event.content_id,
                    "source_surface": event.source_surface,
                    "job_id": event.job_id,
                    "job_type": job_type,
                    "issues": issues,
                }
            )
        if len(inconsistent) >= 30:
            break

    return {
        "by_source_surface": by_surface,
        "feed_source_count": feed_count,
        "search_source_count": search_count,
        "creator_monitor_source_count": creator_count,
        "unknown_source_count": unknown_count,
        "inconsistent_samples": inconsistent,
    }


def audit_search_context_integrity(db: Session) -> dict[str, Any]:
    search_content_ids = {
        row[0]
        for row in db.execute(
            select(ContentDiscoveryEvent.content_id).where(ContentDiscoveryEvent.source_surface == SourceSurface.SEARCH.value).distinct()
        )
    }
    total = len(search_content_ids)
    field_stats: list[dict[str, Any]] = []
    missing_keyword_samples: list[dict[str, Any]] = []
    missing_rank_samples: list[dict[str, Any]] = []
    default_only_sort_samples: list[dict[str, Any]] = []
    filter_apply_status_counter: Counter[str] = Counter()

    for field in SEARCH_CONTEXT_FIELDS:
        non_empty = 0
        example: Any = None
        for content_id in search_content_ids:
            metas = list(
                db.scalars(
                    select(ContentDiscoveryEvent.discovery_meta_json).where(
                        ContentDiscoveryEvent.content_id == content_id,
                        ContentDiscoveryEvent.source_surface == SourceSurface.SEARCH.value,
                    )
                )
            )
            for meta in metas:
                value = _meta_value(meta, field, f"{field}_filter")
                if value not in (None, "", [], {}):
                    non_empty += 1
                    example = example or value
                    break
        field_stats.append(
            {
                "field": field,
                "non_empty_count": non_empty,
                "completeness_rate": round(non_empty / total, 4) if total else 0.0,
                "example_value": example,
            }
        )

    for content_id in list(search_content_ids)[:500]:
        content = db.get(ContentIdentity, content_id)
        metas = list(
            db.scalars(
                select(ContentDiscoveryEvent.discovery_meta_json).where(
                    ContentDiscoveryEvent.content_id == content_id,
                    ContentDiscoveryEvent.source_surface == SourceSurface.SEARCH.value,
                )
            )
        )
        has_keyword = any(_meta_value(meta, "search_keyword") for meta in metas)
        has_rank = any(_meta_value(meta, "search_rank") is not None for meta in metas)
        sort_values = {_meta_value(meta, "search_sort") for meta in metas if _meta_value(meta, "search_sort")}
        apply_statuses = {_meta_value(meta, "filter_apply_status") for meta in metas if _meta_value(meta, "filter_apply_status")}
        for status in apply_statuses:
            filter_apply_status_counter[str(status)] += 1
        if not has_keyword and len(missing_keyword_samples) < 20:
            missing_keyword_samples.append({"content_id": content_id, "title": (content.metadata_json or {}).get("feed_title_or_summary") if content else None})
        if not has_rank and len(missing_rank_samples) < 20:
            missing_rank_samples.append({"content_id": content_id})
        if sort_values <= {"comprehensive", None} and apply_statuses <= {None, "not_implemented"} and len(default_only_sort_samples) < 20:
            default_only_sort_samples.append({"content_id": content_id, "search_sort_values": sorted(value for value in sort_values if value)})

    return {
        "search_content_total": total,
        "field_stats": field_stats,
        "missing_search_keyword_samples": missing_keyword_samples,
        "missing_search_rank_samples": missing_rank_samples,
        "default_only_search_sort_samples": default_only_sort_samples,
        "filter_apply_status_counts": dict(filter_apply_status_counter),
        "filter_context_note": "当前只能记录 requested filter，尚不能证明 Local Agent 已实际点选小红书筛选控件。",
        "filter_context_todo": "Local Agent 后续需要上报 applied_filter_context。",
    }


def audit_tags(db: Session) -> dict[str, Any]:
    contents = list(db.scalars(select(ContentIdentity)))
    platform_tag_counter: Counter[str] = Counter()
    manual_tag_counter: Counter[str] = Counter()
    search_tag_counter: Counter[str] = Counter()
    platform_non_empty = 0
    manual_non_empty = 0
    search_non_empty = 0
    platform_samples: list[dict[str, Any]] = []

    for content in contents:
        snapshot = db.get(ContentSnapshot, content.latest_snapshot_id) if content.latest_snapshot_id else None
        metadata = content.metadata_json or {}
        platform_tags = extract_platform_tags(metadata, snapshot.raw_payload_json if snapshot else None)
        manual_tags = extract_manual_tags(metadata)
        metas = list(db.scalars(select(ContentDiscoveryEvent.discovery_meta_json).where(ContentDiscoveryEvent.content_id == content.id)))
        search_tags = extract_search_tags(metadata, [meta for meta in metas if meta])
        if platform_tags:
            platform_non_empty += 1
            platform_tag_counter.update(platform_tags)
            if len(platform_samples) < 10:
                platform_samples.append({"content_id": content.id, "platform_tags": platform_tags, "from_detail": bool(snapshot and (snapshot.raw_payload_json or {}).get("platform_tags"))})
        if manual_tags:
            manual_non_empty += 1
            manual_tag_counter.update(manual_tags)
        if search_tags:
            search_non_empty += 1
            search_tag_counter.update(search_tags)

    total = len(contents) or 1
    return {
        "platform_tags_non_empty_count": platform_non_empty,
        "manual_tags_non_empty_count": manual_non_empty,
        "search_tags_non_empty_count": search_non_empty,
        "platform_tags_coverage_rate": round(platform_non_empty / total, 4),
        "manual_tags_coverage_rate": round(manual_non_empty / total, 4),
        "search_tags_coverage_rate": round(search_non_empty / total, 4),
        "platform_tags_top_50": _top_counter(list(platform_tag_counter.elements())),
        "manual_tags_top_50": _top_counter(list(manual_tag_counter.elements())),
        "search_tags_top_50": _top_counter(list(search_tag_counter.elements())),
        "platform_tag_samples": platform_samples,
    }


def audit_discovery_strength(db: Session) -> dict[str, Any]:
    account_counts = dict(
        db.execute(
            select(ContentDiscoveryEvent.content_id, func.count(func.distinct(ContentDiscoveryEvent.account_id)))
            .group_by(ContentDiscoveryEvent.content_id)
        ).all()
    )
    discovery_counts = dict(db.execute(select(ContentDiscoveryEvent.content_id, func.count(ContentDiscoveryEvent.id)).group_by(ContentDiscoveryEvent.content_id)).all())
    keyword_counts: dict[str, set[str]] = defaultdict(set)
    for meta, content_id in db.execute(select(ContentDiscoveryEvent.discovery_meta_json, ContentDiscoveryEvent.content_id)):
        keyword = _meta_value(meta, "search_keyword")
        if keyword:
            keyword_counts[content_id].add(str(keyword))

    multi_account_2 = sum(1 for count in account_counts.values() if count and count >= 2)
    multi_account_3 = sum(1 for count in account_counts.values() if count and count >= 3)
    multi_keyword = sum(1 for keywords in keyword_counts.values() if len(keywords) >= 2)

    top_rows: list[dict[str, Any]] = []
    ranked = sorted(discovery_counts.items(), key=lambda item: item[1], reverse=True)[:50]
    for content_id, discovery_count in ranked:
        content = db.get(ContentIdentity, content_id)
        latest = db.scalar(select(func.max(ContentDiscoveryEvent.discovered_at)).where(ContentDiscoveryEvent.content_id == content_id))
        top_rows.append(
            {
                "content_id": content_id,
                "title": (content.metadata_json or {}).get("feed_title_or_summary") if content else None,
                "discovery_count": discovery_count,
                "discovered_account_count": account_counts.get(content_id, 0),
                "discovered_search_keyword_count": len(keyword_counts.get(content_id, set())),
                "latest_discovered_at": _iso(latest),
            }
        )

    return {
        "multi_account_discovered_gte_2": multi_account_2,
        "multi_account_discovered_gte_3": multi_account_3,
        "multi_search_keyword_discovered_gte_2": multi_keyword,
        "discovery_count_top_50": top_rows,
    }


def audit_dedup_quality(db: Session) -> dict[str, Any]:
    duplicate_platform_ids = list(
        db.execute(
            select(ContentIdentity.platform, ContentIdentity.platform_content_id, func.count(ContentIdentity.id))
            .group_by(ContentIdentity.platform, ContentIdentity.platform_content_id)
            .having(func.count(ContentIdentity.id) > 1)
        )
    )
    contents = list(db.scalars(select(ContentIdentity)))
    title_author_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    url_prefix_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    for content in contents:
        metadata = content.metadata_json or {}
        title = (metadata.get("feed_title_or_summary") or "").strip()
        author = (metadata.get("author_name") or "").strip()
        if title and author:
            title_author_map[(title, author)].append(content.id)
        if content.canonical_url:
            prefix = re.sub(r"/explore/[^/?#]+", "/explore/*", content.canonical_url.strip())
            url_prefix_map[(content.platform, prefix)].append(content.id)

    title_author_dupes = [
        {"title": key[0], "author_name": key[1], "content_ids": ids}
        for key, ids in title_author_map.items()
        if len(ids) > 1
    ][:20]
    url_dupes = [
        {"platform": key[0], "canonical_url_prefix": key[1], "content_ids": ids}
        for key, ids in url_prefix_map.items()
        if len(ids) > 1
    ][:20]

    return {
        "duplicate_platform_content_id_groups": [
            {"platform": platform, "platform_content_id": platform_content_id, "count": count}
            for platform, platform_content_id, count in duplicate_platform_ids
        ],
        "title_author_duplicate_samples": title_author_dupes,
        "canonical_url_prefix_duplicate_samples": url_dupes,
    }


def audit_enrichment_policy(db: Session, *, window_hours: int = 24) -> dict[str, Any]:
    since = _utcnow() - timedelta(hours=window_hours)
    jobs = list(db.scalars(select(Job).where(Job.created_at >= since).order_by(Job.created_at.desc())))
    detail_jobs = [job for job in jobs if job.job_type == JobType.DETAIL_FETCH.value]
    comment_jobs = [job for job in jobs if job.job_type == JobType.COMMENT_FETCH.value]
    card_items = db.scalar(select(func.count(ContentIdentity.id)).where(ContentIdentity.first_seen_at >= since)) or 0
    detail_ready_items = 0
    for content in db.scalars(select(ContentIdentity).where(ContentIdentity.first_seen_at >= since)):
        if content.latest_snapshot_id:
            detail_ready_items += 1

    def _is_manual(job: Job) -> bool:
        return bool((job.payload_json or {}).get("manual_enqueue"))

    auto_detail = sum(1 for job in detail_jobs if not _is_manual(job))
    manual_detail = sum(1 for job in detail_jobs if _is_manual(job))
    auto_comment = sum(1 for job in comment_jobs if not _is_manual(job))
    manual_comment = sum(1 for job in comment_jobs if _is_manual(job))

    success_statuses = {JobStatus.SUCCESS.value, JobStatus.PARTIAL_SUCCESS.value}
    detail_success = sum(1 for job in detail_jobs if job.status in success_statuses)
    detail_failed = sum(1 for job in detail_jobs if job.status == JobStatus.FAILED.value)
    comment_success = sum(1 for job in comment_jobs if job.status in success_statuses)
    comment_failed = sum(1 for job in comment_jobs if job.status == JobStatus.FAILED.value)

    detail_ratio = round(len(detail_jobs) / card_items, 4) if card_items else 0.0
    comment_ratio = round(len(comment_jobs) / detail_ready_items, 4) if detail_ready_items else 0.0
    runaway_risk = card_items >= 100 and detail_ratio >= 0.95

    return {
        "window_hours": window_hours,
        "since": _iso(since),
        "card_items": card_items,
        "detail_ready_items": detail_ready_items,
        "auto_detail_fetch_created": auto_detail,
        "manual_detail_fetch_created": manual_detail,
        "auto_comment_fetch_created": auto_comment,
        "manual_comment_fetch_created": manual_comment,
        "detail_fetch_success": detail_success,
        "detail_fetch_failed": detail_failed,
        "comment_fetch_success": comment_success,
        "comment_fetch_failed": comment_failed,
        "detail_fetch_ratio": detail_ratio,
        "comment_fetch_ratio": comment_ratio,
        "runaway_all_detail_fetch_risk": runaway_risk,
    }


def audit_reference_library(db: Session) -> dict[str, Any]:
    items = list(db.scalars(select(ReferenceLibraryItem)))
    duplicate_active = list(
        db.execute(
            select(ReferenceLibraryItem.content_id, func.count(ReferenceLibraryItem.id))
            .where(ReferenceLibraryItem.status == "active")
            .group_by(ReferenceLibraryItem.content_id)
            .having(func.count(ReferenceLibraryItem.id) > 1)
        )
    )
    missing_user = [item.id for item in items if not item.created_by_user_id]
    missing_reason = [item.id for item in items if not item.selected_reason]
    missing_created_at = [item.id for item in items if not item.created_at]

    manual_tags: list[str] = []
    material_tags: list[str] = []
    for item in items:
        manual_tags.extend(item.manual_tags_json or [])
        material_tags.extend(item.material_tags_json or [])

    return {
        "total": len(items),
        "active_count": sum(1 for item in items if item.status == "active"),
        "archived_count": sum(1 for item in items if item.status == "archived"),
        "by_library_type": dict(Counter(item.library_type for item in items)),
        "by_created_by_user_id": dict(Counter(item.created_by_user_id or "null" for item in items)),
        "by_created_by_employee_id": dict(Counter(item.created_by_employee_id or "null" for item in items)),
        "by_rating": dict(Counter(item.rating or "null" for item in items)),
        "manual_tags_top_50": _top_counter(manual_tags),
        "material_tags_top_50": _top_counter(material_tags),
        "duplicate_active_groups": [
            {"content_id": content_id, "count": count}
            for content_id, count in duplicate_active
        ],
        "missing_created_by_user_id": missing_user[:20],
        "missing_selected_reason": missing_reason[:20],
        "missing_created_at": missing_created_at,
    }


def build_manual_validation_checklist() -> list[dict[str, str]]:
    return [
        {"section": "推荐页采集", "item": "10 个采集号，每个号前 50 条", "status": "pending"},
        {"section": "推荐页采集", "item": "是否入公共池 / 记录来源账号 / feed_position / 去重 / discovered_account_count", "status": "pending"},
        {"section": "推荐页采集", "item": "是否没有无脑全量详情补采", "status": "pending"},
        {"section": "搜索词采集", "item": "核心词：医学；长尾词：医学sci求助", "status": "pending"},
        {"section": "搜索词采集", "item": "筛选组合：综合/不限/半年内/前100；最多点赞/图文/半年内/前100；最多评论/不限/半年内/前100", "status": "pending"},
        {"section": "搜索词采集", "item": "是否记录 search_keyword/search_sort/note_type/publish_time/search_rank", "status": "pending"},
        {"section": "搜索词采集", "item": "是否区分 requested filter 与 applied filter", "status": "pending"},
        {"section": "对标账号采集", "item": "5 个对标账号，每个最新 5 条", "status": "pending"},
        {"section": "对标账号采集", "item": "creator source / 新发识别 / 自动补详情 / 入公共池 / 可入对标素材库", "status": "pending"},
        {"section": "入对标素材库", "item": "从公共池手动加入 20 条", "status": "pending"},
        {"section": "入对标素材库", "item": "入库人/时间/原因/筛选/重复 active 不重复创建", "status": "pending"},
    ]


def run_intelligence_center_audit(db: Session, *, window_hours: int = 24) -> dict[str, Any]:
    run_id = uuid4().hex[:12]
    generated_at = _utcnow()
    report = {
        "run_id": run_id,
        "generated_at": _iso(generated_at),
        "window_hours": window_hours,
        "pool_totals": audit_pool_totals(db),
        "data_status": audit_data_status_distribution(db),
        "source_distribution": audit_source_distribution(db),
        "search_context": audit_search_context_integrity(db),
        "tags": audit_tags(db),
        "discovery_strength": audit_discovery_strength(db),
        "dedup_quality": audit_dedup_quality(db),
        "enrichment_policy": audit_enrichment_policy(db, window_hours=window_hours),
        "reference_library": audit_reference_library(db),
        "manual_validation_checklist": build_manual_validation_checklist(),
        "findings": [],
    }

    findings: list[dict[str, Any]] = []
    if report["search_context"]["filter_context_note"]:
        findings.append({"severity": "info", "code": "requested_filter_only", "message": report["search_context"]["filter_context_note"]})
    if report["enrichment_policy"]["runaway_all_detail_fetch_risk"]:
        findings.append({"severity": "warning", "code": "runaway_detail_fetch", "message": "最近窗口内卡片几乎全部触发 detail_fetch，存在补采失控风险"})
    if report["reference_library"]["duplicate_active_groups"]:
        findings.append({"severity": "error", "code": "duplicate_active_reference_library", "message": "发现重复 active 对标素材库记录"})
    if report["dedup_quality"]["duplicate_platform_content_id_groups"]:
        findings.append({"severity": "error", "code": "duplicate_platform_content_id", "message": "发现 platform+platform_content_id 重复 ContentIdentity"})
    report["findings"] = findings
    return report


def render_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 情报中心验收审计报告",
        "",
        f"- run_id: `{report['run_id']}`",
        f"- generated_at: {report['generated_at']}",
        f"- window_hours: {report['window_hours']}",
        "",
        "## 1. 公共池总量",
        "",
    ]
    for key, value in report["pool_totals"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## 2. 数据状态分布", ""])
    for key, value in report["data_status"]["distribution"].items():
        lines.append(f"- {key}: {value}")
    lines.append(f"- 抽样验证: {report['data_status']['sample_size']} 条")

    lines.extend(["", "## 3. 来源分布", ""])
    src = report["source_distribution"]
    lines.append(f"- 推荐页来源: {src['feed_source_count']}")
    lines.append(f"- 搜索来源: {src['search_source_count']}")
    lines.append(f"- 对标账号来源: {src['creator_monitor_source_count']}")
    lines.append(f"- 未知来源: {src['unknown_source_count']}")

    lines.extend(["", "## 4. 搜索上下文完整性", ""])
    lines.append("| 字段 | 非空数量 | 完整率 | 示例 |")
    lines.append("| --- | ---: | ---: | --- |")
    for row in report["search_context"]["field_stats"]:
        lines.append(f"| {row['field']} | {row['non_empty_count']} | {row['completeness_rate']:.2%} | {row.get('example_value') or '-'} |")
    lines.append("")
    lines.append(f"> {report['search_context']['filter_context_note']}")
    lines.append(f"> TODO: {report['search_context']['filter_context_todo']}")

    lines.extend(["", "## 5. 标签完整性", ""])
    tags = report["tags"]
    lines.append(f"- platform_tags 非空: {tags['platform_tags_non_empty_count']} ({tags['platform_tags_coverage_rate']:.2%})")
    lines.append(f"- manual_tags 非空: {tags['manual_tags_non_empty_count']} ({tags['manual_tags_coverage_rate']:.2%})")
    lines.append(f"- search_tags 非空: {tags['search_tags_non_empty_count']} ({tags['search_tags_coverage_rate']:.2%})")

    lines.extend(["", "## 6. 发现强度", ""])
    strength = report["discovery_strength"]
    lines.append(f"- 被 2+ 账号发现: {strength['multi_account_discovered_gte_2']}")
    lines.append(f"- 被 3+ 账号发现: {strength['multi_account_discovered_gte_3']}")
    lines.append(f"- 被多个搜索词发现: {strength['multi_search_keyword_discovered_gte_2']}")

    lines.extend(["", "## 7. 去重质量", ""])
    dedup = report["dedup_quality"]
    lines.append(f"- platform+platform_content_id 重复组: {len(dedup['duplicate_platform_content_id_groups'])}")
    lines.append(f"- title+author 疑似重复样本: {len(dedup['title_author_duplicate_samples'])}")

    lines.extend(["", "## 8. 分层补采策略效果", ""])
    enrich = report["enrichment_policy"]
    lines.append(f"- 卡片入池: {enrich['card_items']}")
    lines.append(f"- 自动 detail_fetch: {enrich['auto_detail_fetch_created']}")
    lines.append(f"- 手动 detail_fetch: {enrich['manual_detail_fetch_created']}")
    lines.append(f"- 自动 comment_fetch: {enrich['auto_comment_fetch_created']}")
    lines.append(f"- 手动 comment_fetch: {enrich['manual_comment_fetch_created']}")
    lines.append(f"- detail_fetch 成功/失败: {enrich['detail_fetch_success']} / {enrich['detail_fetch_failed']}")
    lines.append(f"- comment_fetch 成功/失败: {enrich['comment_fetch_success']} / {enrich['comment_fetch_failed']}")
    lines.append(f"- 补采比例 detail/card: {enrich['detail_fetch_ratio']:.2%}")
    lines.append(f"- 评论补采比例 comment/detail_ready: {enrich['comment_fetch_ratio']:.2%}")
    lines.append(f"- 失控风险: {'是' if enrich['runaway_all_detail_fetch_risk'] else '否'}")

    lines.extend(["", "## 9. 对标素材库验收", ""])
    ref = report["reference_library"]
    lines.append(f"- 总数: {ref['total']} / active: {ref['active_count']} / archived: {ref['archived_count']}")
    lines.append(f"- duplicate active: {len(ref['duplicate_active_groups'])}")
    lines.append(f"- missing created_by_user_id: {len(ref['missing_created_by_user_id'])}")

    lines.extend(["", "## 10. 真实链路手工验收清单", ""])
    for item in report["manual_validation_checklist"]:
        lines.append(f"- [{item['status']}] {item['section']} · {item['item']}")

    if report["findings"]:
        lines.extend(["", "## 发现的问题", ""])
        for finding in report["findings"]:
            lines.append(f"- **{finding['severity']}** `{finding['code']}`: {finding['message']}")

    return "\n".join(lines) + "\n"


def write_audit_outputs(report: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = report["run_id"]
    md_path = output_dir / f"intelligence_center_audit_{run_id}.summary.md"
    json_path = output_dir / f"intelligence_center_audit_{run_id}.summary.json"
    ndjson_path = output_dir / f"intelligence_center_audit_{run_id}.ndjson"
    md_path.write_text(render_audit_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with ndjson_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"record_type": "run_header", **{k: report[k] for k in ("run_id", "generated_at", "window_hours")}}, ensure_ascii=False) + "\n")
        for section in (
            "pool_totals",
            "data_status",
            "source_distribution",
            "search_context",
            "tags",
            "discovery_strength",
            "dedup_quality",
            "enrichment_policy",
            "reference_library",
            "findings",
        ):
            handle.write(json.dumps({"record_type": "section", "section": section, "payload": report[section]}, ensure_ascii=False) + "\n")
        for sample in report["data_status"].get("sample_validation", []):
            handle.write(json.dumps({"record_type": "data_status_sample", **sample}, ensure_ascii=False) + "\n")
        for sample in report["source_distribution"].get("inconsistent_samples", []):
            handle.write(json.dumps({"record_type": "source_inconsistent_sample", **sample}, ensure_ascii=False) + "\n")
        for sample in report["search_context"].get("missing_search_keyword_samples", []):
            handle.write(json.dumps({"record_type": "missing_search_keyword_sample", **sample}, ensure_ascii=False) + "\n")
    return {"markdown": str(md_path), "json": str(json_path), "ndjson": str(ndjson_path)}


def build_data_quality_overview(db: Session, *, window_hours: int = 24) -> dict[str, Any]:
    audit = run_intelligence_center_audit(db, window_hours=window_hours)
    enrich = audit["enrichment_policy"]
    search = audit["search_context"]
    tags = audit["tags"]
    since = _utcnow() - timedelta(hours=window_hours)
    detail_total = enrich["detail_fetch_success"] + enrich["detail_fetch_failed"]
    comment_total = enrich["comment_fetch_success"] + enrich["comment_fetch_failed"]
    search_rates = [row["completeness_rate"] for row in search["field_stats"]]
    abnormal_accounts = db.scalar(
        select(func.count(PlatformAccount.id)).where(PlatformAccount.health_status.in_(["warning", "cooling_down", "blocked", "disabled"]))
    ) or 0
    today_comments = db.scalar(select(func.count(CommentSnapshot.id)).where(CommentSnapshot.fetched_at >= since)) or 0
    today_reference_library = db.scalar(select(func.count(ReferenceLibraryItem.id)).where(ReferenceLibraryItem.created_at >= since)) or 0
    return {
        "generated_at": audit["generated_at"],
        "window_hours": window_hours,
        "today_new_contents": enrich["card_items"],
        "today_card_count": audit["data_status"]["distribution"].get(ContentDataStatus.CARD_ONLY.value, 0),
        "today_detail_count": enrich["detail_ready_items"],
        "today_comment_count": today_comments,
        "today_reference_library_count": today_reference_library,
        "detail_fetch_success_rate": round(enrich["detail_fetch_success"] / detail_total, 4) if detail_total else None,
        "comment_fetch_success_rate": round(enrich["comment_fetch_success"] / comment_total, 4) if comment_total else None,
        "search_context_completeness_rate": round(sum(search_rates) / len(search_rates), 4) if search_rates else 0.0,
        "platform_tags_coverage_rate": tags["platform_tags_coverage_rate"],
        "multi_discovery_content_count": audit["discovery_strength"]["multi_account_discovered_gte_2"],
        "abnormal_account_count": abnormal_accounts,
        "runaway_detail_fetch_risk": enrich["runaway_all_detail_fetch_risk"],
        "filter_context_note": search["filter_context_note"],
    }
