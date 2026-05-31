from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import ContentManualTag, ManualTag, utcnow


class ManualTagRepository:
    SYSTEM_TAG_WATCH_LATER = "稍后看"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def normalize_name(name: str) -> str:
        return name.strip()

    def get_by_id(self, tag_id: str) -> ManualTag | None:
        return self.db.get(ManualTag, tag_id)

    def get_by_name(self, name: str) -> ManualTag | None:
        normalized = self.normalize_name(name)
        if not normalized:
            return None
        stmt = select(ManualTag).where(ManualTag.name == normalized)
        return self.db.scalar(stmt)

    def ensure_system_watch_later(self) -> ManualTag:
        existing = self.get_by_name(self.SYSTEM_TAG_WATCH_LATER)
        if existing:
            if not existing.is_system:
                existing.is_system = True
            if existing.status != "active":
                existing.status = "active"
                existing.archived_at = None
                existing.archived_by_user_id = None
            self.db.flush()
            return existing
        tag = ManualTag(
            name=self.SYSTEM_TAG_WATCH_LATER,
            status="active",
            is_system=True,
            created_by_user_id=None,
        )
        self.db.add(tag)
        self.db.flush()
        return tag

    def list_tags(self, *, status: str | None = "active") -> list[ManualTag]:
        stmt = select(ManualTag).order_by(ManualTag.name.asc())
        if status:
            stmt = stmt.where(ManualTag.status == status)
        return list(self.db.scalars(stmt))

    def usage_count(self, tag_id: str) -> int:
        stmt = select(func.count(ContentManualTag.id)).where(ContentManualTag.tag_id == tag_id)
        return int(self.db.scalar(stmt) or 0)

    def list_tag_summaries(self, *, status: str | None = None) -> list[dict]:
        usage_subq = (
            select(ContentManualTag.tag_id.label("tag_id"), func.count(ContentManualTag.id).label("usage_count"))
            .group_by(ContentManualTag.tag_id)
            .subquery()
        )
        stmt = (
            select(ManualTag, func.coalesce(usage_subq.c.usage_count, 0))
            .outerjoin(usage_subq, usage_subq.c.tag_id == ManualTag.id)
            .order_by(func.coalesce(usage_subq.c.usage_count, 0).desc(), ManualTag.name.asc())
        )
        if status:
            stmt = stmt.where(ManualTag.status == status)
        rows = self.db.execute(stmt).all()
        return [
            {
                "id": tag.id,
                "name": tag.name,
                "status": tag.status,
                "is_system": tag.is_system,
                "created_by_user_id": tag.created_by_user_id,
                "usage_count": int(usage_count or 0),
                "created_at": tag.created_at,
                "updated_at": tag.updated_at,
                "archived_at": tag.archived_at,
            }
            for tag, usage_count in rows
        ]

    def create_tag(self, *, name: str, created_by_user_id: str | None, is_system: bool = False) -> ManualTag:
        normalized = self.normalize_name(name)
        if not normalized:
            raise ValueError("tag name required")
        existing = self.get_by_name(normalized)
        if existing:
            if existing.status == "active":
                raise ValueError("tag name already exists")
            existing.status = "active"
            existing.archived_at = None
            existing.archived_by_user_id = None
            existing.is_system = existing.is_system or is_system
            if created_by_user_id and not existing.created_by_user_id:
                existing.created_by_user_id = created_by_user_id
            self.db.flush()
            return existing
        tag = ManualTag(
            name=normalized,
            status="active",
            is_system=is_system,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(tag)
        self.db.flush()
        return tag

    def archive_tag(self, tag: ManualTag, *, archived_by_user_id: str | None) -> ManualTag:
        tag.status = "archived"
        tag.archived_at = utcnow()
        tag.archived_by_user_id = archived_by_user_id
        self.db.flush()
        return tag

    def restore_tag(self, tag: ManualTag) -> ManualTag:
        tag.status = "active"
        tag.archived_at = None
        tag.archived_by_user_id = None
        self.db.flush()
        return tag

    def delete_tag(self, tag: ManualTag) -> None:
        self.db.query(ContentManualTag).filter(ContentManualTag.tag_id == tag.id).delete()
        self.db.delete(tag)
        self.db.flush()

    def list_content_tag_rows(self, content_id: str) -> list[tuple[ContentManualTag, ManualTag]]:
        stmt = (
            select(ContentManualTag, ManualTag)
            .join(ManualTag, ManualTag.id == ContentManualTag.tag_id)
            .where(ContentManualTag.content_id == content_id)
            .order_by(ManualTag.name.asc())
        )
        return list(self.db.execute(stmt).all())

    def list_content_tag_names(self, content_id: str) -> list[str]:
        return [tag.name for _, tag in self.list_content_tag_rows(content_id)]

    def list_content_tag_ids(self, content_id: str) -> list[str]:
        stmt = select(ContentManualTag.tag_id).where(ContentManualTag.content_id == content_id)
        return list(self.db.scalars(stmt))

    def replace_content_tags(self, *, content_id: str, tag_ids: list[str]) -> list[ManualTag]:
        unique_ids = list(dict.fromkeys(tag_ids))
        if unique_ids:
            tags = list(self.db.scalars(select(ManualTag).where(ManualTag.id.in_(unique_ids))))
            if len(tags) != len(unique_ids):
                raise ValueError("tag not found")
        else:
            tags = []
        self.db.query(ContentManualTag).filter(ContentManualTag.content_id == content_id).delete()
        for tag in tags:
            self.db.add(ContentManualTag(content_id=content_id, tag_id=tag.id))
        self.db.flush()
        return tags

    def content_has_tag(self, *, content_id: str, tag_id: str) -> bool:
        stmt = select(ContentManualTag.id).where(
            and_(ContentManualTag.content_id == content_id, ContentManualTag.tag_id == tag_id)
        )
        return self.db.scalar(stmt) is not None

    def add_content_tag(self, *, content_id: str, tag_id: str) -> None:
        if self.content_has_tag(content_id=content_id, tag_id=tag_id):
            return
        self.db.add(ContentManualTag(content_id=content_id, tag_id=tag_id))
        self.db.flush()
