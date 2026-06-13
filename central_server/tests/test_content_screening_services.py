from intelligence_engine.db.models import CandidateDecision, ContentIdentity, ContentSnapshot, utcnow
from intelligence_engine.domain.enums import CandidateBucket, ContentType, Platform
from intelligence_engine.services.content_screening import ContentScreeningService
from intelligence_engine.services.lead_detection import LeadDetectionService
from intelligence_engine.services.rule_profile import RuleProfileService


def _content_with_snapshot(db_session, *, like_count: int = 120) -> tuple[ContentIdentity, ContentSnapshot]:
    content = ContentIdentity(
        id="screening-content-1",
        platform=Platform.XHS.value,
        platform_content_id="screening-note-1",
        canonical_url="https://example.com/screening-note-1",
        content_type=ContentType.IMAGE_TEXT.value,
        first_seen_at=utcnow(),
        last_seen_at=utcnow(),
        latest_snapshot_id=None,
        metadata_json={"visible_like_count": like_count},
    )
    snapshot = ContentSnapshot(
        id="screening-snapshot-1",
        content_id=content.id,
        title="SCI 投稿避坑",
        body_text="论文投稿经验",
        like_count=like_count,
        comment_count=8,
        fetched_at=utcnow(),
    )
    db_session.add_all([content, snapshot])
    content.latest_snapshot_id = snapshot.id
    db_session.flush()
    return content, snapshot


def test_lead_detection_collects_title_and_comment_intent_keywords():
    decision = CandidateDecision(
        content_id="content-1",
        snapshot_id="snapshot-1",
        business_keyword_hits_json=["论文"],
        lead_keyword_hits_json=["求推"],
        comment_keyword_hits_json=["怎么联系"],
        like_threshold_hit=True,
        comment_threshold_hit=False,
        candidate_bucket=CandidateBucket.LEAD_CANDIDATE.value,
        decision_reason_json={},
        evaluated_at=utcnow(),
    )

    result = LeadDetectionService().detect_intent_keywords(decision)

    assert result.has_intent is True
    assert result.matched_keywords == ["求推", "怎么联系"]


def test_content_screening_maps_lead_decision_to_lead_reference_target(db_session):
    RuleProfileService(db_session).ensure_defaults()
    content, snapshot = _content_with_snapshot(db_session, like_count=120)
    decision = CandidateDecision(
        content_id=content.id,
        snapshot_id=snapshot.id,
        business_keyword_hits_json=["论文"],
        lead_keyword_hits_json=["求推"],
        comment_keyword_hits_json=[],
        like_threshold_hit=True,
        comment_threshold_hit=False,
        candidate_bucket=CandidateBucket.LEAD_CANDIDATE.value,
        decision_reason_json={},
        evaluated_at=utcnow(),
    )

    target = ContentScreeningService(db_session).evaluate_reference_target(
        content=content,
        snapshot=snapshot,
        decision=decision,
    )

    assert target is not None
    assert target.library_type == "lead"
    assert target.rating == "good"
    assert target.matched_keywords == ["求推"]


def test_content_screening_maps_business_candidate_to_non_lead_target(db_session):
    RuleProfileService(db_session).ensure_defaults()
    content, snapshot = _content_with_snapshot(db_session, like_count=220)
    decision = CandidateDecision(
        content_id=content.id,
        snapshot_id=snapshot.id,
        business_keyword_hits_json=["论文"],
        lead_keyword_hits_json=[],
        comment_keyword_hits_json=[],
        like_threshold_hit=True,
        comment_threshold_hit=False,
        candidate_bucket=CandidateBucket.CONTENT_CANDIDATE.value,
        decision_reason_json={},
        evaluated_at=utcnow(),
    )

    target = ContentScreeningService(db_session).evaluate_reference_target(
        content=content,
        snapshot=snapshot,
        decision=decision,
    )

    assert target is not None
    assert target.library_type == "non_lead"
    assert target.rating == "medium"
    assert target.matched_keywords == ["论文"]
