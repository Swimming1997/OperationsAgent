from datetime import datetime

from sqlalchemy import Text, and_, func, or_, select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import (
    User,
    CandidateDecision,
    CommentSnapshot,
    ContentAssignment,
    ContentDiscoveryEvent,
    ContentIdentity,
    ContentOperatorNote,
    ContentSnapshot,
    ContentWorkflowState,
    ReferenceLibraryItem,
    utcnow,
)
from intelligence_engine.domain.enums import CandidateBucket, ContentDataStatus, ContentWorkflowStatus, ReferenceLibraryItemStatus
from intelligence_engine.domain.intelligence_pool import (
    aggregate_search_context,
    derive_data_status,
    extract_manual_tags,
    extract_platform_tags,
    extract_search_tags,
)
from intelligence_engine.storage.repositories.reference_library_repository import ReferenceLibraryRepository


def enum_value(value):
    return getattr(value, "value", value)


class WorkflowRepository:
    def __init__(self, db: Session):
        self.db = db

    def ensure_state(self, content_id: str) -> ContentWorkflowState:
        state = self.db.scalar(select(ContentWorkflowState).where(ContentWorkflowState.content_id == content_id))
        if state:
            return state
        state = ContentWorkflowState(content_id=content_id, workflow_status=ContentWorkflowStatus.PENDING_REVIEW.value)
        self.db.add(state)
        self.db.flush()
        return state

    def assign(self, *, content_id: str, assigned_to_user_id: str, assigned_by_user_id: str | None, remark: str | None) -> ContentWorkflowState:
        now = utcnow()
        state = self.ensure_state(content_id)
        state.workflow_status = ContentWorkflowStatus.ASSIGNED.value
        state.assigned_to_user_id = assigned_to_user_id
        state.assigned_by_user_id = assigned_by_user_id
        state.assigned_at = now
        state.reviewed_at = now
        self.db.add(
            ContentAssignment(
                content_id=content_id,
                assigned_to_user_id=assigned_to_user_id,
                assigned_by_user_id=assigned_by_user_id,
                assigned_at=now,
                status=ContentWorkflowStatus.ASSIGNED.value,
                remark=remark,
            )
        )
        self.db.flush()
        return state

    def set_status(self, *, content_id: str, status: ContentWorkflowStatus | str, user_id: str | None = None, note: str | None = None) -> ContentWorkflowState:
        now = utcnow()
        state = self.ensure_state(content_id)
        status_value = enum_value(status)
        state.workflow_status = status_value
        state.reviewed_at = now
        if status_value == ContentWorkflowStatus.SELECTED.value:
            state.selected_at = now
        elif status_value == ContentWorkflowStatus.DISCARDED.value:
            state.discarded_at = now
        if note:
            self.add_note(content_id=content_id, user_id=user_id, note=note)
        self.db.flush()
        return state

    def add_note(self, *, content_id: str, user_id: str | None, note: str) -> ContentOperatorNote:
        row = ContentOperatorNote(content_id=content_id, user_id=user_id, note=note)
        self.db.add(row)
        state = self.ensure_state(content_id)
        state.latest_operator_note = note
        self.db.flush()
        return row

    def update_manual_tags(self, *, content_id: str, manual_tags: list[str], user_id: str | None) -> ContentIdentity:
        content = self.db.get(ContentIdentity, content_id)
        if not content:
            raise ValueError("content not found")
        metadata = dict(content.metadata_json or {})
        metadata["manual_tags"] = manual_tags
        content.metadata_json = metadata
        tag_text = ", ".join(manual_tags) if manual_tags else "（已清空）"
        self.add_note(content_id=content_id, user_id=user_id, note=f"更新运营标签：{tag_text}")
        self.db.flush()
        return content

    def list_notes(self, *, content_id: str) -> list[ContentOperatorNote]:
        stmt = select(ContentOperatorNote).where(ContentOperatorNote.content_id == content_id).order_by(ContentOperatorNote.created_at.desc())
        return list(self.db.scalars(stmt))

    def list_intelligence_contents(
        self,
        *,
        page: int,
        page_size: int,
        platform: str | None = None,
        source_surface: str | None = None,
        candidate_bucket: str | None = None,
        workflow_status: str | None = None,
        assigned_to_user_id: str | None = None,
        business_keyword: str | None = None,
        search_keyword: str | None = None,
        discovered_after: datetime | None = None,
        discovered_before: datetime | None = None,
        data_status: str | None = None,
        tag: str | None = None,
        platform_tag: str | None = None,
        manual_tag: str | None = None,
        search_sort: str | None = None,
        note_type_filter: str | None = None,
        publish_time_filter: str | None = None,
        min_like_count: int | None = None,
        min_comment_count: int | None = None,
        min_collect_count: int | None = None,
        sort_by: str = "latest_discovered_at",
        sort_order: str = "desc",
        pool_only: bool = True,
    ) -> tuple[list[dict], int]:
        base_conditions = []
        if pool_only and not candidate_bucket:
            base_conditions.append(
                or_(
                    CandidateDecision.id.is_(None),
                    CandidateDecision.candidate_bucket.in_(
                        [
                            CandidateBucket.CONTENT_CANDIDATE.value,
                            CandidateBucket.LEAD_CANDIDATE.value,
                            CandidateBucket.PENDING_ENRICHMENT.value,
                        ]
                    ),
                )
            )
        if platform:
            base_conditions.append(ContentIdentity.platform == platform)
        if source_surface:
            base_conditions.append(ContentDiscoveryEvent.source_surface == source_surface)
        if candidate_bucket:
            base_conditions.append(CandidateDecision.candidate_bucket == candidate_bucket)
        if workflow_status:
            base_conditions.append(ContentWorkflowState.workflow_status == workflow_status)
        if assigned_to_user_id:
            base_conditions.append(ContentWorkflowState.assigned_to_user_id == assigned_to_user_id)
        if business_keyword:
            keyword = business_keyword.lower()
            base_conditions.append(
                or_(
                    func.lower(CandidateDecision.business_keyword_hits_json.cast(Text)).contains(keyword),
                    func.lower(ContentIdentity.metadata_json.cast(Text)).contains(keyword),
                    func.lower(ContentSnapshot.title).contains(keyword),
                    func.lower(ContentSnapshot.body_text).contains(keyword),
                )
            )
        if search_keyword:
            keyword = search_keyword.lower()
            base_conditions.append(func.lower(ContentDiscoveryEvent.discovery_meta_json.cast(Text)).contains(keyword))
        if discovered_after:
            base_conditions.append(ContentDiscoveryEvent.discovered_at >= discovered_after)
        if discovered_before:
            base_conditions.append(ContentDiscoveryEvent.discovered_at <= discovered_before)
        if search_sort:
            base_conditions.append(func.lower(ContentDiscoveryEvent.discovery_meta_json.cast(Text)).contains(search_sort.lower()))
        if note_type_filter:
            base_conditions.append(func.lower(ContentDiscoveryEvent.discovery_meta_json.cast(Text)).contains(note_type_filter.lower()))
        if publish_time_filter:
            base_conditions.append(func.lower(ContentDiscoveryEvent.discovery_meta_json.cast(Text)).contains(publish_time_filter.lower()))
        if min_like_count is not None:
            base_conditions.append(func.coalesce(ContentSnapshot.like_count, 0) >= min_like_count)
        if min_comment_count is not None:
            base_conditions.append(func.coalesce(ContentSnapshot.comment_count, 0) >= min_comment_count)
        if min_collect_count is not None:
            base_conditions.append(func.coalesce(ContentSnapshot.collect_count, 0) >= min_collect_count)
        if manual_tag:
            base_conditions.append(func.lower(ContentIdentity.metadata_json.cast(Text)).contains(manual_tag.lower()))
        if platform_tag:
            base_conditions.append(
                or_(
                    func.lower(ContentIdentity.metadata_json.cast(Text)).contains(platform_tag.lower()),
                    func.lower(ContentSnapshot.raw_payload_json.cast(Text)).contains(platform_tag.lower()),
                )
            )
        if tag:
            lowered = tag.lower()
            base_conditions.append(
                or_(
                    func.lower(ContentIdentity.metadata_json.cast(Text)).contains(lowered),
                    func.lower(ContentSnapshot.raw_payload_json.cast(Text)).contains(lowered),
                    func.lower(ContentDiscoveryEvent.discovery_meta_json.cast(Text)).contains(lowered),
                )
            )
        if data_status == ContentDataStatus.CARD_ONLY.value:
            base_conditions.append(ContentIdentity.latest_snapshot_id.is_(None))
        elif data_status == ContentDataStatus.DETAIL_READY.value:
            base_conditions.append(ContentIdentity.latest_snapshot_id.isnot(None))

        latest_decision = (
            select(
                CandidateDecision.id.label("decision_id"),
                CandidateDecision.content_id.label("content_id"),
                func.row_number()
                .over(
                    partition_by=CandidateDecision.content_id,
                    order_by=(CandidateDecision.evaluated_at.desc(), CandidateDecision.created_at.desc()),
                )
                .label("rn"),
            )
            .subquery()
        )
        discovery_count_expr = func.count(ContentDiscoveryEvent.id)
        discovered_account_count_expr = func.count(func.distinct(ContentDiscoveryEvent.account_id))
        latest_discovered_expr = func.max(ContentDiscoveryEvent.discovered_at)

        joins = (
            select(ContentIdentity.id)
            .join(ContentDiscoveryEvent, ContentDiscoveryEvent.content_id == ContentIdentity.id, isouter=True)
            .join(ContentSnapshot, ContentSnapshot.id == ContentIdentity.latest_snapshot_id, isouter=True)
            .join(latest_decision, (latest_decision.c.content_id == ContentIdentity.id) & (latest_decision.c.rn == 1), isouter=True)
            .join(CandidateDecision, CandidateDecision.id == latest_decision.c.decision_id, isouter=True)
            .join(ContentWorkflowState, ContentWorkflowState.content_id == ContentIdentity.id, isouter=True)
        )
        if base_conditions:
            joins = joins.where(and_(*base_conditions))
        total = self.db.scalar(select(func.count()).select_from(joins.distinct().subquery())) or 0

        order_column = latest_discovered_expr
        if sort_by == "first_seen_at":
            order_column = ContentIdentity.first_seen_at
        elif sort_by == "last_seen_at":
            order_column = ContentIdentity.last_seen_at
        elif sort_by == "like_count":
            order_column = func.coalesce(ContentSnapshot.like_count, 0)
        elif sort_by == "comment_count":
            order_column = func.coalesce(ContentSnapshot.comment_count, 0)
        elif sort_by == "collect_count":
            order_column = func.coalesce(ContentSnapshot.collect_count, 0)
        elif sort_by == "discovery_count":
            order_column = discovery_count_expr
        elif sort_by == "discovered_account_count":
            order_column = discovered_account_count_expr
        order_expr = order_column.desc() if sort_order != "asc" else order_column.asc()

        stmt = (
            select(
                ContentIdentity,
                ContentSnapshot,
                CandidateDecision,
                ContentWorkflowState,
                User,
                latest_discovered_expr.label("latest_discovered_at"),
                discovery_count_expr.label("discovery_count"),
                discovered_account_count_expr.label("discovered_account_count"),
            )
            .join(ContentDiscoveryEvent, ContentDiscoveryEvent.content_id == ContentIdentity.id, isouter=True)
            .join(ContentSnapshot, ContentSnapshot.id == ContentIdentity.latest_snapshot_id, isouter=True)
            .join(latest_decision, (latest_decision.c.content_id == ContentIdentity.id) & (latest_decision.c.rn == 1), isouter=True)
            .join(CandidateDecision, CandidateDecision.id == latest_decision.c.decision_id, isouter=True)
            .join(ContentWorkflowState, ContentWorkflowState.content_id == ContentIdentity.id, isouter=True)
            .join(User, User.id == ContentWorkflowState.assigned_to_user_id, isouter=True)
        )
        if base_conditions:
            stmt = stmt.where(and_(*base_conditions))
        stmt = (
            stmt.group_by(ContentIdentity.id, ContentSnapshot.id, CandidateDecision.id, ContentWorkflowState.id, User.id)
            .order_by(order_expr)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list(self.db.execute(stmt))
        ref_repo = ReferenceLibraryRepository(self.db)
        items = []
        for content, snapshot, decision, state, assignee, latest_discovered_at, discovery_count, discovered_account_count in rows:
            if not state:
                state = self.ensure_state(content.id)
            summary = self._discovery_summary(content.id)
            discovery_meta_rows = self._discovery_meta_rows(content.id)
            search_context = aggregate_search_context(discovery_meta_rows)
            metadata = content.metadata_json or {}
            comment_count = summary.get("comment_snapshot_count") or 0
            enrichment_flags = metadata.get("enrichment_flags") if isinstance(metadata.get("enrichment_flags"), dict) else {}
            status_value = derive_data_status(
                latest_snapshot_id=content.latest_snapshot_id,
                comment_snapshot_count=comment_count,
                detail_fetch_failed=bool(enrichment_flags.get("detail_failed")),
                comment_fetch_failed=bool(enrichment_flags.get("comment_failed")),
            )
            if data_status in {ContentDataStatus.COMMENTS_READY.value, ContentDataStatus.DETAIL_FAILED.value, ContentDataStatus.COMMENTS_FAILED.value}:
                if status_value != data_status:
                    continue
            platform_tags = extract_platform_tags(metadata, snapshot.raw_payload_json if snapshot else None)
            manual_tags = extract_manual_tags(metadata)
            search_tags = extract_search_tags(metadata, discovery_meta_rows)
            items.append(
                {
                    "content_id": content.id,
                    "platform": content.platform,
                    "platform_content_id": content.platform_content_id,
                    "content_type": content.content_type,
                    "canonical_url": content.canonical_url,
                    "title": snapshot.title if snapshot else metadata.get("feed_title_or_summary"),
                    "author_name": snapshot.author_name if snapshot else metadata.get("author_name"),
                    "cover_url": snapshot.cover_url if snapshot else metadata.get("cover_url"),
                    "like_count": snapshot.like_count if snapshot else metadata.get("visible_like_count"),
                    "comment_count": snapshot.comment_count if snapshot else None,
                    "collect_count": snapshot.collect_count if snapshot else None,
                    "candidate_bucket": decision.candidate_bucket if decision else CandidateBucket.PENDING_ENRICHMENT.value,
                    "business_keyword_hits": decision.business_keyword_hits_json if decision else [],
                    "lead_keyword_hits": decision.lead_keyword_hits_json if decision else [],
                    "comment_keyword_hits": decision.comment_keyword_hits_json if decision else [],
                    "workflow_status": state.workflow_status,
                    "assigned_to_user_id": state.assigned_to_user_id,
                    "assigned_to_user_display_name": assignee.display_name if assignee else None,
                    "latest_operator_note": state.latest_operator_note,
                    "latest_snapshot_time": snapshot.fetched_at if snapshot else None,
                    "latest_discovered_at": latest_discovered_at,
                    "discovery_sources_summary": summary,
                    "first_seen_at": content.first_seen_at,
                    "last_seen_at": content.last_seen_at,
                    "data_status": status_value,
                    "discovery_count": int(discovery_count or 0),
                    "discovered_account_count": int(discovered_account_count or 0),
                    "discovered_search_keyword_count": search_context["discovered_search_keyword_count"],
                    "platform_tags": platform_tags,
                    "search_tags": search_tags,
                    "manual_tags": manual_tags,
                    "search_keyword": search_context["search_keyword"],
                    "search_sort": search_context["search_sort"],
                    "note_type_filter": search_context["note_type_filter"],
                    "publish_time_filter": search_context["publish_time_filter"],
                    "search_scope_filter": search_context["search_scope_filter"],
                    "location_filter": search_context["location_filter"],
                    "best_search_rank": search_context["best_search_rank"],
                    "best_feed_position": search_context["best_feed_position"] or self._best_feed_position(discovery_meta_rows),
                    "reference_library_count": ref_repo.count_active_for_content(content.id),
                }
            )
        if data_status in {ContentDataStatus.COMMENTS_READY.value, ContentDataStatus.DETAIL_FAILED.value, ContentDataStatus.COMMENTS_FAILED.value}:
            total = len(items)
        if sort_by in {"best_search_rank", "best_feed_position", "discovered_search_keyword_count", "reference_library_count"}:
            reverse = sort_order != "asc"
            key_map = {
                "best_search_rank": lambda item: item.get("best_search_rank") if item.get("best_search_rank") is not None else 999999,
                "best_feed_position": lambda item: item.get("best_feed_position") if item.get("best_feed_position") is not None else 999999,
                "discovered_search_keyword_count": lambda item: item.get("discovered_search_keyword_count") or 0,
                "reference_library_count": lambda item: item.get("reference_library_count") or 0,
            }
            items.sort(key=key_map[sort_by], reverse=reverse)
        return items, total

    def latest_decision_for_content(self, content_id: str) -> CandidateDecision | None:
        stmt = select(CandidateDecision).where(CandidateDecision.content_id == content_id).order_by(CandidateDecision.evaluated_at.desc()).limit(1)
        return self.db.scalar(stmt)

    def assignment_history(self, content_id: str) -> list[ContentAssignment]:
        stmt = select(ContentAssignment).where(ContentAssignment.content_id == content_id).order_by(ContentAssignment.assigned_at.desc())
        return list(self.db.scalars(stmt))

    def discovery_events(self, content_id: str) -> list[ContentDiscoveryEvent]:
        stmt = select(ContentDiscoveryEvent).where(ContentDiscoveryEvent.content_id == content_id).order_by(ContentDiscoveryEvent.discovered_at.desc())
        return list(self.db.scalars(stmt))

    def _discovery_meta_rows(self, content_id: str) -> list[dict]:
        rows = list(
            self.db.scalars(
                select(ContentDiscoveryEvent.discovery_meta_json).where(ContentDiscoveryEvent.content_id == content_id)
            )
        )
        return [row for row in rows if row]

    def _best_feed_position(self, discovery_meta_rows: list[dict]) -> int | None:
        positions = [row.get("feed_position") for row in discovery_meta_rows if isinstance(row.get("feed_position"), int)]
        return min(positions) if positions else None

    def _discovery_summary(self, content_id: str) -> dict:
        rows = list(
            self.db.execute(
                select(ContentDiscoveryEvent.source_surface, func.count(ContentDiscoveryEvent.id))
                .where(ContentDiscoveryEvent.content_id == content_id)
                .group_by(ContentDiscoveryEvent.source_surface)
            )
        )
        comment_count = self.db.scalar(select(func.count(CommentSnapshot.id)).where(CommentSnapshot.content_id == content_id)) or 0
        keyword_rows = self._discovery_meta_rows(content_id)
        search_keywords: set[str] = set()
        for meta in keyword_rows:
            for key in ("search_keyword",):
                value = meta.get(key)
                if value:
                    search_keywords.add(str(value))
            for value in meta.get("search_keywords") or []:
                if value:
                    search_keywords.add(str(value))
        return {
            "source_surfaces": {surface: count for surface, count in rows},
            "comment_snapshot_count": comment_count,
            "search_keywords": sorted(search_keywords),
        }
