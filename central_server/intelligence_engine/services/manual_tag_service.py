from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from intelligence_engine.db.models import ContentIdentity, ManualTag
from intelligence_engine.domain.enums import UserRoleName
from intelligence_engine.security.auth import Principal
from intelligence_engine.storage.repositories.manual_tag_repository import ManualTagRepository
from intelligence_engine.storage.repositories.workflow_repository import WorkflowRepository


@dataclass(frozen=True)
class ManualTagActionError(Exception):
    code: str
    message: str


class ManualTagService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ManualTagRepository(db)

    def ensure_bootstrap(self) -> None:
        self.repo.ensure_system_watch_later()

    def list_active_tags(self) -> list[dict]:
        self.ensure_bootstrap()
        return self.repo.list_tag_summaries(status="active")

    def list_manageable_tags(self) -> list[dict]:
        self.ensure_bootstrap()
        return self.repo.list_tag_summaries(status=None)

    def create_tag(self, *, name: str, principal: Principal) -> dict:
        self._ensure_write_role(principal)
        try:
            tag = self.repo.create_tag(name=name, created_by_user_id=principal.user_id)
        except ValueError as exc:
            raise ManualTagActionError("invalid_tag_name", str(exc)) from exc
        return self._summary(tag)

    def set_content_tags(
        self,
        *,
        content_id: str,
        tag_ids: list[str],
        principal: Principal,
        user_id: str | None = None,
    ) -> ContentIdentity:
        self._ensure_write_role(principal)
        content = self.db.get(ContentIdentity, content_id)
        if not content:
            raise ValueError("content not found")
        self.ensure_bootstrap()
        try:
            tags = self.repo.replace_content_tags(content_id=content_id, tag_ids=tag_ids)
        except ValueError as exc:
            raise ManualTagActionError("tag_not_found", str(exc)) from exc
        metadata = dict(content.metadata_json or {})
        metadata["manual_tags"] = [tag.name for tag in tags]
        content.metadata_json = metadata
        actor = user_id or principal.user_id
        tag_text = ", ".join(metadata["manual_tags"]) if metadata["manual_tags"] else "（已清空）"
        WorkflowRepository(self.db).add_note(content_id=content_id, user_id=actor, note=f"更新运营标签：{tag_text}")
        self.db.flush()
        return content

    def add_watch_later_tag(self, *, content_id: str, principal: Principal, user_id: str | None = None) -> ContentIdentity:
        self._ensure_write_role(principal)
        watch_later = self.repo.ensure_system_watch_later()
        current_ids = self.repo.list_content_tag_ids(content_id)
        if watch_later.id not in current_ids:
            current_ids.append(watch_later.id)
        return self.set_content_tags(content_id=content_id, tag_ids=current_ids, principal=principal, user_id=user_id)

    def delete_tag_for_operator(self, *, tag_id: str, principal: Principal) -> None:
        if not principal.has_role(UserRoleName.OPERATOR):
            raise ManualTagActionError("forbidden", "insufficient role")
        if principal.has_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR):
            raise ManualTagActionError("forbidden", "use management delete endpoints")
        tag = self.repo.get_by_id(tag_id)
        if not tag:
            raise ManualTagActionError("not_found", "tag not found")
        if tag.is_system:
            raise ManualTagActionError("forbidden", "system tag cannot be deleted")
        if tag.created_by_user_id != principal.user_id:
            raise ManualTagActionError("forbidden", "operator can only delete own tags")
        usage_count = self.repo.usage_count(tag.id)
        if usage_count > 0:
            raise ManualTagActionError("tag_in_use", f"tag is used by {usage_count} contents")
        self.repo.delete_tag(tag)

    def archive_tag(self, *, tag_id: str, principal: Principal) -> dict:
        self._ensure_manage_role(principal)
        tag = self.repo.get_by_id(tag_id)
        if not tag:
            raise ManualTagActionError("not_found", "tag not found")
        if tag.status == "archived":
            return self._summary(tag)
        tag = self.repo.archive_tag(tag, archived_by_user_id=principal.user_id)
        return self._summary(tag)

    def restore_tag(self, *, tag_id: str, principal: Principal) -> dict:
        self._ensure_manage_role(principal)
        tag = self.repo.get_by_id(tag_id)
        if not tag:
            raise ManualTagActionError("not_found", "tag not found")
        tag = self.repo.restore_tag(tag)
        return self._summary(tag)

    def hard_delete_tag(self, *, tag_id: str, principal: Principal) -> None:
        self._ensure_manage_role(principal)
        tag = self.repo.get_by_id(tag_id)
        if not tag:
            raise ManualTagActionError("not_found", "tag not found")
        if tag.is_system:
            raise ManualTagActionError("forbidden", "system tag cannot be hard deleted")
        from sqlalchemy import select

        from intelligence_engine.db.models import ContentManualTag

        affected_content_ids = list(
            self.db.scalars(select(ContentManualTag.content_id).where(ContentManualTag.tag_id == tag_id))
        )
        self.repo.delete_tag(tag)
        for content_id in affected_content_ids:
            content = self.db.get(ContentIdentity, content_id)
            if not content:
                continue
            metadata = dict(content.metadata_json or {})
            metadata["manual_tags"] = self.repo.list_content_tag_names(content_id)
            content.metadata_json = metadata
        self.db.flush()

    def can_operator_delete(self, *, summary: dict, principal: Principal) -> bool:
        if not principal.has_role(UserRoleName.OPERATOR) or principal.has_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR):
            return False
        if summary.get("is_system"):
            return False
        if summary.get("created_by_user_id") != principal.user_id:
            return False
        return int(summary.get("usage_count") or 0) == 0

    def _summary(self, tag: ManualTag) -> dict:
        return {
            "id": tag.id,
            "name": tag.name,
            "status": tag.status,
            "is_system": tag.is_system,
            "created_by_user_id": tag.created_by_user_id,
            "usage_count": self.repo.usage_count(tag.id),
            "created_at": tag.created_at,
            "updated_at": tag.updated_at,
            "archived_at": tag.archived_at,
        }

    @staticmethod
    def _ensure_write_role(principal: Principal) -> None:
        if not principal.has_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR):
            raise ManualTagActionError("forbidden", "insufficient role")

    @staticmethod
    def _ensure_manage_role(principal: Principal) -> None:
        if not principal.has_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR):
            raise ManualTagActionError("forbidden", "insufficient role")
