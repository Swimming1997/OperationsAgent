from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from intelligence_engine.db.models import ContentIdentity, ContentSnapshot, ReferenceLibraryItem
from intelligence_engine.domain.enums import ReferenceLibrarySelectionSource
from intelligence_engine.services.content_screening import ContentScreeningService
from intelligence_engine.storage.repositories.reference_library_repository import (
    ReferenceLibraryRepository,
    normalize_library_type,
    normalize_rating,
)
from intelligence_engine.storage.repositories.workflow_repository import WorkflowRepository
from intelligence_engine.services.rule_profile import RuleProfileService


@dataclass(frozen=True)
class SelectionActor:
    user_id: str | None = None
    employee_id: str | None = None


class BenchmarkSelectionService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ReferenceLibraryRepository(db)

    def manual_select(
        self,
        *,
        content_id: str,
        library_type: str,
        actor: SelectionActor,
        selected_reason: str | None = None,
        rating: str | None = None,
        manual_tags: list[str] | None = None,
        material_tags: list[str] | None = None,
        usage_status: str = "unused",
        note: str | None = None,
        metadata: dict[str, Any] | None = None,
        matched_keywords: list[str] | None = None,
        selection_sources: list[str] | None = None,
    ) -> ReferenceLibraryItem:
        if not self.db.get(ContentIdentity, content_id):
            raise ValueError("content not found")

        library_type = normalize_library_type(library_type)
        rating = normalize_rating(rating)
        sources = self._merge_sources(selection_sources or [], ReferenceLibrarySelectionSource.MANUAL.value)
        item_metadata = dict(metadata or {})
        item_metadata["selection_locked_by_manual"] = True

        existing = self.repo.get_active_item(content_id=content_id)
        if existing:
            merged_metadata = dict(existing.metadata_json or {})
            merged_metadata.update(item_metadata)
            updates: dict[str, Any] = {
                "library_type": library_type,
                "selection_sources_json": self._merge_sources(existing.selection_sources_json or [], *sources),
                "metadata_json": merged_metadata,
            }
            if selected_reason is not None:
                updates["selected_reason"] = selected_reason
            if rating is not None:
                updates["rating"] = rating
            if manual_tags is not None:
                updates["manual_tags_json"] = manual_tags
            if material_tags is not None:
                updates["material_tags_json"] = material_tags
            if usage_status is not None:
                updates["usage_status"] = usage_status
            if note is not None:
                updates["note"] = note
            if matched_keywords is not None:
                updates["matched_keywords_json"] = matched_keywords
            return self.repo.update_item(
                existing,
                **updates,
                event_type="manual_selected",
                actor_user_id=actor.user_id,
                actor_employee_id=actor.employee_id,
            )

        return self.repo.create_item(
            content_id=content_id,
            library_type=library_type,
            created_by_user_id=actor.user_id,
            created_by_employee_id=actor.employee_id,
            selected_reason=selected_reason,
            rating=rating,
            manual_tags=manual_tags or [],
            material_tags=material_tags or [],
            usage_status=usage_status,
            note=note,
            metadata=item_metadata,
            selection_sources=sources,
            matched_keywords=matched_keywords or [],
        )

    def ai_select_by_rules(
        self,
        *,
        content_id: str,
        trigger_source: str = "manual_re_evaluate",
        actor: SelectionActor | None = None,
    ) -> tuple[ReferenceLibraryItem | None, str, dict[str, Any]]:
        content = self.db.get(ContentIdentity, content_id)
        if not content:
            raise ValueError("content not found")

        existing = self.repo.get_active_item(content_id=content_id)
        if existing and (existing.metadata_json or {}).get("selection_locked_by_manual"):
            return existing, "skipped_manual_locked", {"content_id": content_id}

        decision = WorkflowRepository(self.db).latest_decision_for_content(content_id)
        snapshot = self.db.get(ContentSnapshot, content.latest_snapshot_id) if content.latest_snapshot_id else None
        if not decision:
            return existing, "skipped_no_candidate_decision", {"content_id": content_id}

        screening = ContentScreeningService(self.db)
        target = screening.evaluate_reference_target(content=content, snapshot=snapshot, decision=decision)
        if not target:
            return existing, "skipped_no_rule_match", {"content_id": content_id, "candidate_bucket": decision.candidate_bucket}

        library_type = target.library_type
        rule_profile = RuleProfileService(self.db).get_enabled(platform=content.platform, library_type=library_type)
        if not rule_profile:
            RuleProfileService(self.db).ensure_defaults(created_by_user_id=actor.user_id if actor else None)
            rule_profile = RuleProfileService(self.db).get_enabled(platform=content.platform, library_type=library_type)
        if not rule_profile:
            return existing, "skipped_no_rule_profile", {"content_id": content_id, "platform": content.platform, "library_type": library_type}

        input_snapshot = screening.input_snapshot(content=content, snapshot=snapshot, decision=decision)
        matched_keywords = target.matched_keywords
        metadata = {
            "ai_reason": target.reason,
            "rule_profile_id": rule_profile.id,
            "rule_profile_version": rule_profile.version,
            "trigger_source": trigger_source,
            "input_snapshot_json": input_snapshot,
            "selection_locked_by_manual": False,
        }
        evaluation_key = f"{content_id}:{rule_profile.id}:{rule_profile.version}:{trigger_source}"
        selected_reason = target.reason
        actor = actor or SelectionActor()

        if existing:
            existing_keys = list((existing.metadata_json or {}).get("ai_evaluation_keys") or [])
            if evaluation_key in existing_keys:
                return existing, "skipped_duplicate_evaluation", {"content_id": content_id, "ai_reason": target.reason}
            metadata["ai_evaluation_keys"] = [*existing_keys, evaluation_key]
            item = self.repo.update_item(
                existing,
                library_type=library_type,
                rating=target.rating,
                selected_reason=selected_reason,
                matched_keywords_json=matched_keywords,
                selection_sources_json=self._merge_sources(existing.selection_sources_json or [], ReferenceLibrarySelectionSource.AI.value),
                metadata_json={**(existing.metadata_json or {}), **metadata},
                event_type="ai_re_evaluated",
                actor_user_id=actor.user_id,
                actor_employee_id=actor.employee_id,
            )
            return item, "updated", metadata

        metadata["ai_evaluation_keys"] = [evaluation_key]
        item = self.repo.create_item(
            content_id=content_id,
            library_type=library_type,
            created_by_user_id=actor.user_id,
            created_by_employee_id=actor.employee_id,
            selected_reason=selected_reason,
            rating=target.rating,
            manual_tags=[],
            material_tags=[],
            usage_status="unused",
            note=None,
            metadata=metadata,
            selection_sources=[ReferenceLibrarySelectionSource.AI.value],
            matched_keywords=matched_keywords,
        )
        return item, "created", metadata

    @staticmethod
    def _merge_sources(existing: list[str], *sources: str) -> list[str]:
        merged: list[str] = []
        for source in [*existing, *sources]:
            if source and source not in merged:
                merged.append(source)
        return merged
