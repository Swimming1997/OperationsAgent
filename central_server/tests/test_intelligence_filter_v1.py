from intelligence_engine.domain.enums import CandidateBucket
from intelligence_engine.filtering.candidate_classifier import classify_feed_prelim, classify_intelligence_v1


def test_feed_prelim_keeps_business_keyword_with_like_threshold():
    result = classify_feed_prelim(title_or_summary="SCI 论文投稿经验", visible_like_count=50)

    assert result.candidate_bucket == CandidateBucket.PENDING_ENRICHMENT
    assert result.business_keyword_hits == ["论文", "SCI", "投稿"]
    assert result.like_threshold_hit is True


def test_feed_prelim_keeps_empty_title_for_detail_judgement():
    result = classify_feed_prelim(title_or_summary=None, visible_like_count=80)

    assert result.candidate_bucket == CandidateBucket.PENDING_ENRICHMENT


def test_detail_filter_outputs_lead_and_content_buckets():
    lead = classify_intelligence_v1(title="求推荐 SCI 期刊", body_text="有没有推荐")
    content = classify_intelligence_v1(title="论文投稿经验", body_text="期刊选择", detail_like_count=60)
    discard = classify_intelligence_v1(title="今天吃什么", body_text="普通生活内容", detail_like_count=500)

    assert lead.candidate_bucket == CandidateBucket.LEAD_CANDIDATE
    assert content.candidate_bucket == CandidateBucket.CONTENT_CANDIDATE
    assert discard.candidate_bucket == CandidateBucket.DISCARD


def test_comment_hits_are_recorded_as_supplemental_signal():
    result = classify_intelligence_v1(
        title="论文投稿经验",
        body_text="期刊选择",
        comments=["求推荐", "还有没有推荐"],
        detail_like_count=60,
    )

    assert result.candidate_bucket == CandidateBucket.CONTENT_CANDIDATE
    assert "求推荐" in result.comment_keyword_hits
    assert "有没有推荐" in result.comment_keyword_hits
