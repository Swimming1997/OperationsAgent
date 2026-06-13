from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import CandidateDecision, CommentSnapshot, ContentIdentity, ContentSnapshot
from intelligence_engine.domain.enums import CandidateBucket
from intelligence_engine.services.lead_detection import LeadDetectionService
from intelligence_engine.services.rule_profile import RuleProfileService


@dataclass(frozen=True)
class ReferenceSelectionTarget:
    library_type: str
    rating: str
    matched_keywords: list[str]
    reason: str


class ContentScreeningService:
    """Map screened content into a reference-library selection target."""

    def __init__(self, db: Session):
        self.db = db
        self.leads = LeadDetectionService()

    def evaluate_reference_target(
        self,
        *,
        content: ContentIdentity,
        snapshot: ContentSnapshot | None,
        decision: CandidateDecision,
    ) -> ReferenceSelectionTarget | None:
        lead_result = self.leads.detect_intent_keywords(decision)
        business_keywords = list(decision.business_keyword_hits_json or [])
        like_count = self.like_count(content=content, snapshot=snapshot)

        if lead_result.has_intent:
            profile = self._profile_config(platform=content.platform, library_type="lead")
            rating = self._rating_for_like_count(like_count, profile["rating_thresholds"], default="watching")
            return ReferenceSelectionTarget(
                library_type="lead",
                rating=rating or "watching",
                matched_keywords=lead_result.matched_keywords,
                reason=f"命中求推关键词：{', '.join(lead_result.matched_keywords)}；点赞数 {like_count or 0} -> {rating or 'watching'}",
            )

        if decision.candidate_bucket not in {CandidateBucket.CONTENT_CANDIDATE.value, CandidateBucket.PENDING_ENRICHMENT.value}:
            return None

        profile = self._profile_config(platform=content.platform, library_type="non_lead")
        rating = self._rating_for_like_count(like_count, profile["rating_thresholds"], default=None)
        if not rating:
            return None
        return ReferenceSelectionTarget(
            library_type="non_lead",
            rating=rating,
            matched_keywords=business_keywords,
            reason=f"未命中求推词；点赞数 {like_count or 0} -> {rating}",
        )

    def input_snapshot(
        self,
        *,
        content: ContentIdentity,
        snapshot: ContentSnapshot | None,
        decision: CandidateDecision,
    ) -> dict[str, Any]:
        comments = list(
            self.db.scalars(
                select(CommentSnapshot.body_text)
                .where(CommentSnapshot.content_id == content.id)
                .order_by(CommentSnapshot.created_at.desc())
                .limit(20)
            )
        )
        return {
            "platform": content.platform,
            "content_id": content.id,
            "title": snapshot.title if snapshot else (content.metadata_json or {}).get("feed_title_or_summary"),
            "like_count": self.like_count(content=content, snapshot=snapshot),
            "comment_count": snapshot.comment_count if snapshot else None,
            "candidate_bucket": decision.candidate_bucket,
            "business_keyword_hits": decision.business_keyword_hits_json or [],
            "lead_keyword_hits": decision.lead_keyword_hits_json or [],
            "comment_keyword_hits": decision.comment_keyword_hits_json or [],
            "comment_sample_count": len(comments),
        }

    @staticmethod
    def like_count(*, content: ContentIdentity, snapshot: ContentSnapshot | None) -> int | None:
        if snapshot and snapshot.like_count is not None:
            return snapshot.like_count
        metadata = content.metadata_json or {}
        visible_like = metadata.get("visible_like_count")
        return visible_like if isinstance(visible_like, int) else None

    def _profile_config(self, *, platform: str, library_type: str) -> dict[str, Any]:
        profile = RuleProfileService(self.db).get_enabled(platform=platform, library_type=library_type)
        if not profile:
            RuleProfileService(self.db).ensure_defaults()
            profile = RuleProfileService(self.db).get_enabled(platform=platform, library_type=library_type)
        return profile.config_json if profile else {"rating_thresholds": {}}

    @staticmethod
    def _rating_for_like_count(like_count: int | None, thresholds: dict[str, int], *, default: str | None) -> str | None:
        count = like_count or 0
        rating = default
        ordered = [("poor", thresholds.get("poor")), ("medium", thresholds.get("medium")), ("good", thresholds.get("good"))]
        for label, threshold in ordered:
            if threshold is not None and count >= int(threshold):
                rating = label
        return rating
