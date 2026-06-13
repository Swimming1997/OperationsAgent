from dataclasses import dataclass

from intelligence_engine.db.models import CandidateDecision


@dataclass(frozen=True)
class LeadDetectionResult:
    matched_keywords: list[str]

    @property
    def has_intent(self) -> bool:
        return bool(self.matched_keywords)


class LeadDetectionService:
    """Detect lead intent from candidate decisions.

    P0 stores keyword hits on CandidateDecision, so this service is intentionally
    thin. Keeping the boundary here makes the later Lead domain easier to grow.
    """

    def detect_intent_keywords(self, decision: CandidateDecision) -> LeadDetectionResult:
        lead_keywords = list((decision.lead_keyword_hits_json or []) + (decision.comment_keyword_hits_json or []))
        return LeadDetectionResult(matched_keywords=lead_keywords)
