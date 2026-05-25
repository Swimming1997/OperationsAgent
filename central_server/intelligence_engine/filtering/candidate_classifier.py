from dataclasses import dataclass

from intelligence_engine.domain.enums import CandidateBucket


BUSINESS_KEYWORDS = ["SCI", "论文", "期刊", "投稿", "代投", "刊物", "发表"]
LEAD_KEYWORDS = ["求推", "求推荐", "推一下", "有没有渠道", "怎么联系", "求介绍", "求渠道", "能发吗", "多少钱"]
FILTER_V1_BUSINESS_KEYWORDS = ["论文", "SCI", "期刊", "投稿", "发表"]
FILTER_V1_LEAD_INTENT_KEYWORDS = ["求推", "求推荐", "推一下", "求渠道", "有没有推荐"]
FILTER_V1_VISIBLE_LIKE_THRESHOLD = 50


@dataclass(frozen=True)
class CandidateDecisionResult:
    business_keyword_hits: list[str]
    lead_keyword_hits: list[str]
    comment_keyword_hits: list[str]
    like_threshold_hit: bool
    comment_threshold_hit: bool
    candidate_bucket: CandidateBucket
    reason: dict


@dataclass(frozen=True)
class IntelligenceFilterConfig:
    business_keywords: list[str]
    lead_intent_keywords: list[str]
    visible_like_threshold: int = FILTER_V1_VISIBLE_LIKE_THRESHOLD


DEFAULT_FILTER_V1_CONFIG = IntelligenceFilterConfig(
    business_keywords=FILTER_V1_BUSINESS_KEYWORDS,
    lead_intent_keywords=FILTER_V1_LEAD_INTENT_KEYWORDS,
    visible_like_threshold=FILTER_V1_VISIBLE_LIKE_THRESHOLD,
)


def find_hits(text: str | None, keywords: list[str]) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    return [keyword for keyword in keywords if keyword.lower() in lowered]


def classify_candidate(
    *,
    title: str | None,
    body_text: str | None,
    comments: list[str] | None = None,
    like_count: int | None = None,
    comment_count: int | None = None,
    like_threshold: int = 500,
    comment_threshold: int = 20,
) -> CandidateDecisionResult:
    text = "\n".join(part for part in [title, body_text] if part)
    comment_text = "\n".join(comments or [])
    business_hits = find_hits(text, BUSINESS_KEYWORDS)
    lead_hits = find_hits(text, LEAD_KEYWORDS)
    comment_hits = find_hits(comment_text, LEAD_KEYWORDS)
    like_hit = like_count is not None and like_count >= like_threshold
    comment_hit = comment_count is not None and comment_count >= comment_threshold

    if lead_hits or comment_hits:
        bucket = CandidateBucket.LEAD_CANDIDATE
    elif business_hits and (like_hit or comment_hit):
        bucket = CandidateBucket.CONTENT_CANDIDATE
    elif business_hits:
        bucket = CandidateBucket.PENDING_ENRICHMENT
    else:
        bucket = CandidateBucket.DISCARD

    return CandidateDecisionResult(
        business_keyword_hits=business_hits,
        lead_keyword_hits=lead_hits,
        comment_keyword_hits=comment_hits,
        like_threshold_hit=like_hit,
        comment_threshold_hit=comment_hit,
        candidate_bucket=bucket,
        reason={"like_threshold": like_threshold, "comment_threshold": comment_threshold},
    )


def classify_feed_prelim(
    *,
    title_or_summary: str | None,
    visible_like_count: int | None,
    config: IntelligenceFilterConfig = DEFAULT_FILTER_V1_CONFIG,
) -> CandidateDecisionResult:
    business_hits = find_hits(title_or_summary, config.business_keywords)
    like_hit = visible_like_count is not None and visible_like_count >= config.visible_like_threshold
    title_missing = title_or_summary in (None, "")
    if like_hit and business_hits:
        bucket = CandidateBucket.PENDING_ENRICHMENT
    elif like_hit and title_missing:
        bucket = CandidateBucket.PENDING_ENRICHMENT
    else:
        bucket = CandidateBucket.DISCARD
    return CandidateDecisionResult(
        business_keyword_hits=business_hits,
        lead_keyword_hits=[],
        comment_keyword_hits=[],
        like_threshold_hit=like_hit,
        comment_threshold_hit=False,
        candidate_bucket=bucket,
        reason={
            "stage": "feed_prelim",
            "visible_like_threshold": config.visible_like_threshold,
            "title_missing": title_missing,
        },
    )


def classify_intelligence_v1(
    *,
    title: str | None,
    body_text: str | None,
    comments: list[str] | None = None,
    visible_like_count: int | None = None,
    detail_like_count: int | None = None,
    config: IntelligenceFilterConfig = DEFAULT_FILTER_V1_CONFIG,
) -> CandidateDecisionResult:
    text = "\n".join(part for part in [title, body_text] if part)
    comment_text = "\n".join(comments or [])
    business_hits = find_hits(text, config.business_keywords)
    lead_hits = find_hits(text, config.lead_intent_keywords)
    comment_hits = find_hits(comment_text, config.lead_intent_keywords)
    effective_like_count = detail_like_count if detail_like_count is not None else visible_like_count
    like_hit = effective_like_count is not None and effective_like_count >= config.visible_like_threshold

    if lead_hits and business_hits:
        bucket = CandidateBucket.LEAD_CANDIDATE
    elif lead_hits:
        bucket = CandidateBucket.LEAD_CANDIDATE
    elif business_hits and like_hit:
        bucket = CandidateBucket.CONTENT_CANDIDATE
    elif business_hits:
        bucket = CandidateBucket.PENDING_ENRICHMENT
    else:
        bucket = CandidateBucket.DISCARD

    return CandidateDecisionResult(
        business_keyword_hits=business_hits,
        lead_keyword_hits=lead_hits,
        comment_keyword_hits=comment_hits,
        like_threshold_hit=like_hit,
        comment_threshold_hit=False,
        candidate_bucket=bucket,
        reason={
            "stage": "intelligence_filter_v1",
            "visible_like_threshold": config.visible_like_threshold,
            "comment_hits_are_supplemental": True,
        },
    )
