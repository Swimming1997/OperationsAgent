from __future__ import annotations

from intelligence_engine.config import get_settings
from intelligence_engine.domain.enums import CandidateBucket, EnqueueCommentPolicy, EnqueueDetailPolicy, JobType, SourceSurface
from intelligence_engine.domain.schemas import FeedCandidateInput
from intelligence_engine.filtering.candidate_classifier import classify_feed_prelim


def should_enqueue_detail_fetch(
    *,
    candidate: FeedCandidateInput,
    is_new: bool,
    feed_prelim_pass: bool | None,
    parent_job_type: str | None,
    manual: bool = False,
) -> bool:
    if manual:
        return True
    if not is_new:
        return False
    settings = get_settings()
    policy = settings.enqueue_detail_policy
    if policy == EnqueueDetailPolicy.MANUAL_ONLY.value:
        return False
    if policy == EnqueueDetailPolicy.ALL.value:
        return True
    if candidate.source_surface in {SourceSurface.XHS_HOME_FEED, SourceSurface.SEARCH} and candidate.visible_like_count is None:
        return True

    raw = candidate.raw_payload or {}
    prelim = classify_feed_prelim(
        title_or_summary=candidate.title_or_summary,
        visible_like_count=candidate.visible_like_count,
    )
    is_candidate = prelim.candidate_bucket != CandidateBucket.DISCARD.value
    if feed_prelim_pass is not None:
        is_candidate = feed_prelim_pass

    if policy == EnqueueDetailPolicy.CANDIDATE_ONLY.value:
        if is_candidate:
            return True
        if parent_job_type == JobType.CREATOR_MONITOR.value:
            return True
        if candidate.source_surface == SourceSurface.CREATOR_MONITOR:
            return True
        return False

    if policy == EnqueueDetailPolicy.THRESHOLD_ONLY.value:
        if is_candidate:
            return True
        if parent_job_type == JobType.CREATOR_MONITOR.value or candidate.source_surface == SourceSurface.CREATOR_MONITOR:
            return True
        if candidate.visible_like_count is not None and candidate.visible_like_count >= settings.detail_auto_like_threshold:
            return True
        search_rank = raw.get("search_rank")
        if isinstance(search_rank, int) and search_rank <= settings.detail_auto_search_rank_threshold:
            return True
        if candidate.feed_position is not None and candidate.feed_position <= settings.detail_auto_feed_position_threshold:
            return True
        return False

    return False


def should_enqueue_comment_fetch(
    *,
    comment_count: int | None,
    in_reference_library: bool = False,
    manual: bool = False,
    workflow_selected: bool = False,
) -> bool:
    if manual:
        return True
    settings = get_settings()
    policy = settings.enqueue_comment_policy
    if policy == EnqueueCommentPolicy.MANUAL_ONLY.value:
        return False
    if policy == EnqueueCommentPolicy.ALL.value:
        return True
    if in_reference_library:
        return True
    if policy == EnqueueCommentPolicy.SELECTED_ONLY.value:
        return workflow_selected or in_reference_library
    if policy == EnqueueCommentPolicy.HIGH_COMMENT_ONLY.value:
        threshold = settings.comment_auto_count_threshold
        return comment_count is not None and comment_count >= threshold
    return False
