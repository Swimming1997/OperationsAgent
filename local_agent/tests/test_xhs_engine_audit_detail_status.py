from local_agent_runtime.audit.xhs_engine_audit import should_flag_note_unavailable


def test_empty_detail_title_with_body_and_api_success_is_available():
    assert should_flag_note_unavailable(title="", body_text="正文内容", api_success=True) is False


def test_empty_detail_title_without_body_or_api_success_is_unavailable():
    assert should_flag_note_unavailable(title="", body_text=None, api_success=False) is True
