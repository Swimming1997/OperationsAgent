from sqlalchemy import Text, and_, func, select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import (
    ContentIdentity,
    ContentSnapshot,
    ReferenceLibraryEvent,
    ReferenceLibraryItem,
    utcnow,
)
from intelligence_engine.domain.enums import ReferenceLibraryItemStatus


LEGACY_LIBRARY_TYPE_MAP = {
    "benchmark_work": "uncategorized",
    "visual_material": "uncategorized",
    "lead_case": "lead",
}

LEGACY_RATING_MAP = {
    "S": "good",
    "A": "good",
    "B": "medium",
    "C": "poor",
}


def normalize_library_type(value: str) -> str:
    return LEGACY_LIBRARY_TYPE_MAP.get(value, value)


def normalize_rating(value: str | None) -> str | None:
    if value is None:
        return None
    return LEGACY_RATING_MAP.get(value, value)


class ReferenceLibraryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active_item(self, *, content_id: str, library_type: str | None = None) -> ReferenceLibraryItem | None:
        conditions = [
            ReferenceLibraryItem.content_id == content_id,
            ReferenceLibraryItem.status == ReferenceLibraryItemStatus.ACTIVE.value,
        ]
        if library_type:
            conditions.append(ReferenceLibraryItem.library_type == normalize_library_type(library_type))
        return self.db.scalar(
            select(ReferenceLibraryItem).where(and_(*conditions)).order_by(ReferenceLibraryItem.selected_at.desc().nullslast(), ReferenceLibraryItem.created_at.desc())
        )

    def count_active_for_content(self, content_id: str) -> int:
        return (
            self.db.scalar(
                select(func.count(ReferenceLibraryItem.id)).where(
                    ReferenceLibraryItem.content_id == content_id,
                    ReferenceLibraryItem.status == ReferenceLibraryItemStatus.ACTIVE.value,
                )
            )
            or 0
        )

    def content_in_active_library(self, content_id: str) -> bool:
        return self.count_active_for_content(content_id) > 0

    def create_item(
        self,
        *,
        content_id: str,
        library_type: str,
        created_by_user_id: str | None,
        created_by_employee_id: str | None,
        selected_reason: str | None,
        rating: str | None,
        manual_tags: list[str],
        material_tags: list[str],
        usage_status: str,
        note: str | None,
        metadata: dict,
        selection_sources: list[str] | None = None,
        matched_keywords: list[str] | None = None,
        selected_at=None,
    ) -> ReferenceLibraryItem:
        library_type = normalize_library_type(library_type)
        rating = normalize_rating(rating)
        existing = self.get_active_item(content_id=content_id)
        if existing:
            return existing
        now = utcnow()
        item = ReferenceLibraryItem(
            content_id=content_id,
            library_type=library_type,
            status=ReferenceLibraryItemStatus.ACTIVE.value,
            created_by_user_id=created_by_user_id,
            created_by_employee_id=created_by_employee_id,
            selected_reason=selected_reason,
            rating=rating,
            selection_sources_json=selection_sources or [],
            matched_keywords_json=matched_keywords or [],
            selected_at=selected_at or now,
            manual_tags_json=manual_tags,
            material_tags_json=material_tags,
            usage_status=usage_status,
            note=note,
            metadata_json=metadata,
        )
        self.db.add(item)
        self.db.flush()
        self._add_event(
            library_item_id=item.id,
            content_id=content_id,
            event_type="created",
            user_id=created_by_user_id,
            employee_id=created_by_employee_id,
            payload={"selected_reason": selected_reason, "rating": rating},
        )
        return item

    def update_item(
        self,
        item: ReferenceLibraryItem,
        *,
        event_type: str = "updated",
        actor_user_id: str | None = None,
        actor_employee_id: str | None = None,
        **fields,
    ) -> ReferenceLibraryItem:
        for key, value in fields.items():
            if value is not None and hasattr(item, key):
                if key == "library_type":
                    value = normalize_library_type(value)
                if key == "rating":
                    value = normalize_rating(value)
                setattr(item, key, value)
        item.updated_at = utcnow()
        self.db.flush()
        self._add_event(
            library_item_id=item.id,
            content_id=item.content_id,
            event_type=event_type,
            user_id=actor_user_id,
            employee_id=actor_employee_id,
            payload={key: value for key, value in fields.items() if value is not None},
        )
        return item

    def archive_item(self, item: ReferenceLibraryItem, *, user_id: str | None, employee_id: str | None) -> ReferenceLibraryItem:
        item.status = ReferenceLibraryItemStatus.ARCHIVED.value
        item.usage_status = "archived"
        item.updated_at = utcnow()
        self.db.flush()
        self._add_event(
            library_item_id=item.id,
            content_id=item.content_id,
            event_type="archived",
            user_id=user_id,
            employee_id=employee_id,
            payload={},
        )
        return item

    def list_items(
        self,
        *,
        page: int,
        page_size: int,
        library_type: str | None = None,
        platform: str | None = None,
        selection_source: str | None = None,
        rating: str | None = None,
        status: str | None = ReferenceLibraryItemStatus.ACTIVE.value,
        usage_status: str | None = None,
        sort_by: str = "selected_at",
        sort_order: str = "desc",
    ) -> tuple[list[dict], int]:
        conditions = []
        if library_type:
            conditions.append(ReferenceLibraryItem.library_type == normalize_library_type(library_type))
        if platform:
            conditions.append(ContentIdentity.platform == platform)
        if selection_source:
            conditions.append(func.lower(ReferenceLibraryItem.selection_sources_json.cast(Text)).contains(selection_source.lower()))
        if rating:
            conditions.append(ReferenceLibraryItem.rating == normalize_rating(rating))
        if status:
            conditions.append(ReferenceLibraryItem.status == status)
        if usage_status:
            conditions.append(ReferenceLibraryItem.usage_status == usage_status)

        count_stmt = select(func.count(ReferenceLibraryItem.id)).join(ContentIdentity, ContentIdentity.id == ReferenceLibraryItem.content_id)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = self.db.scalar(count_stmt) or 0

        sort_columns = {
            "selected_at": ReferenceLibraryItem.selected_at,
            "created_at": ReferenceLibraryItem.created_at,
            "like_count": func.coalesce(ContentSnapshot.like_count, 0),
            "comment_count": func.coalesce(ContentSnapshot.comment_count, 0),
            "collect_count": func.coalesce(ContentSnapshot.collect_count, 0),
        }
        order_column = sort_columns.get(sort_by, ReferenceLibraryItem.selected_at)
        order_expr = order_column.asc() if sort_order == "asc" else order_column.desc()

        stmt = (
            select(ReferenceLibraryItem, ContentIdentity, ContentSnapshot)
            .join(ContentIdentity, ContentIdentity.id == ReferenceLibraryItem.content_id)
            .join(ContentSnapshot, ContentSnapshot.id == ContentIdentity.latest_snapshot_id, isouter=True)
            .order_by(order_expr, ReferenceLibraryItem.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if conditions:
            stmt = stmt.where(and_(*conditions))
        rows = list(self.db.execute(stmt))
        items = []
        for item, content, snapshot in rows:
            items.append(self._item_dict(item, content, snapshot))
        return items, total

    def list_for_content(self, content_id: str) -> list[ReferenceLibraryItem]:
        stmt = (
            select(ReferenceLibraryItem)
            .where(ReferenceLibraryItem.content_id == content_id)
            .order_by(ReferenceLibraryItem.created_at.desc())
        )
        return list(self.db.scalars(stmt))

    def get_item(self, item_id: str) -> ReferenceLibraryItem | None:
        return self.db.get(ReferenceLibraryItem, item_id)

    def list_events(self, item_id: str, *, limit: int = 100) -> list[ReferenceLibraryEvent]:
        stmt = (
            select(ReferenceLibraryEvent)
            .where(ReferenceLibraryEvent.library_item_id == item_id)
            .order_by(ReferenceLibraryEvent.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def _add_event(
        self,
        *,
        library_item_id: str,
        content_id: str,
        event_type: str,
        user_id: str | None,
        employee_id: str | None,
        payload: dict,
    ) -> ReferenceLibraryEvent:
        event = ReferenceLibraryEvent(
            library_item_id=library_item_id,
            content_id=content_id,
            event_type=event_type,
            user_id=user_id,
            employee_id=employee_id,
            event_payload_json=payload,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def _item_dict(self, item: ReferenceLibraryItem, content: ContentIdentity, snapshot: ContentSnapshot | None) -> dict:
        metadata = content.metadata_json or {}
        return {
            "id": item.id,
            "content_id": item.content_id,
            "platform": content.platform,
            "library_type": item.library_type,
            "status": item.status,
            "created_by_user_id": item.created_by_user_id,
            "created_by_employee_id": item.created_by_employee_id,
            "selected_reason": item.selected_reason,
            "rating": item.rating,
            "selection_sources": item.selection_sources_json or [],
            "matched_keywords": item.matched_keywords_json or [],
            "selected_at": item.selected_at,
            "manual_tags": item.manual_tags_json or [],
            "material_tags": item.material_tags_json or [],
            "usage_status": item.usage_status,
            "note": item.note,
            "metadata": item.metadata_json or {},
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "title": snapshot.title if snapshot else metadata.get("feed_title_or_summary"),
            "author_name": snapshot.author_name if snapshot else metadata.get("author_name"),
            "cover_url": snapshot.cover_url if snapshot else metadata.get("cover_url"),
            "like_count": snapshot.like_count if snapshot else metadata.get("visible_like_count"),
            "comment_count": snapshot.comment_count if snapshot else None,
            "collect_count": snapshot.collect_count if snapshot else None,
        }
