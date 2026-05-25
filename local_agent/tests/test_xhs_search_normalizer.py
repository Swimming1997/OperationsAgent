from datetime import datetime, timezone

from local_agent_runtime.connectors.xhs.normalizer import normalize_xhs_search_card
from local_agent_runtime.enums import SourceSurface


def test_normalize_xhs_search_card_sets_surface_and_keyword():
    raw = {
        "platform_content_id": "note-1",
        "canonical_url": "https://www.xiaohongshu.com/explore/note-1",
        "title_or_summary": "SCI 投稿经验",
        "author_name": "科研小白",
        "cover_url": "https://example.com/cover.jpg",
        "visible_like_count": "12",
        "xsec_token": "token-abc",
        "xsec_source": "pc_search",
    }
    candidate = normalize_xhs_search_card(raw, search_keyword="论文", rank_position=3, discovered_at=datetime.now(timezone.utc))
    assert candidate is not None
    assert candidate.source_surface == SourceSurface.SEARCH
    assert candidate.raw_payload["search_keyword"] == "论文"
    assert candidate.platform_context.get("xsec_token") == "token-abc"
    assert candidate.platform_context.get("xsec_source") == "pc_search"
