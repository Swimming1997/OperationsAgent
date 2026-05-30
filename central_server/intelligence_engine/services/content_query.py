"""Unified content text search for intelligence pool and reference library lists."""

from __future__ import annotations

from sqlalchemy import Text, cast, func, or_, String

from intelligence_engine.db.models import CandidateDecision, ContentIdentity, ContentSnapshot, ReferenceLibraryItem


def resolve_content_query(*values: str | None) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def build_content_query_condition(
    keyword: str,
    *,
    include_business_keyword_hits: bool = False,
    include_reference_item_fields: bool = False,
):
    pattern = f"%{keyword}%"
    lowered = keyword.lower()
    metadata = ContentIdentity.metadata_json
    parts = [
        ContentSnapshot.title.ilike(pattern),
        ContentSnapshot.author_name.ilike(pattern),
        ContentSnapshot.body_text.ilike(pattern),
        ContentIdentity.platform_content_id.ilike(pattern),
        cast(metadata["feed_title_or_summary"].as_string(), String).ilike(pattern),
        cast(metadata["author_name"].as_string(), String).ilike(pattern),
        func.lower(ContentIdentity.metadata_json.cast(Text)).contains(lowered),
    ]
    if include_business_keyword_hits:
        parts.append(func.lower(CandidateDecision.business_keyword_hits_json.cast(Text)).contains(lowered))
    if include_reference_item_fields:
        parts.append(func.lower(ReferenceLibraryItem.selected_reason).contains(lowered))
        parts.append(func.lower(ReferenceLibraryItem.note).contains(lowered))
    return or_(*parts)
