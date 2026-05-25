from local_agent_runtime.connectors.xhs.capabilities import XhsCapabilityLayer, get_xhs_capability, list_xhs_capabilities


def test_xhs_capability_keys_are_unique():
    capabilities = list_xhs_capabilities()
    keys = [item.key for item in capabilities]
    assert len(keys) == len(set(keys))


def test_read_only_audit_supported_flags():
    by_key = {item.key: item for item in list_xhs_capabilities(XhsCapabilityLayer.READ_ONLY_ENGINE.value)}
    assert by_key["xhs.feed.home_recommend"].audit_supported is True
    assert by_key["xhs.search.notes"].audit_supported is True
    assert by_key["xhs.note.detail"].audit_supported is True
    assert by_key["xhs.note.comments"].audit_supported is True
    assert by_key["xhs.note.sub_comments"].audit_supported is False


def test_get_xhs_capability():
    assert get_xhs_capability("xhs.account.self_info").key == "xhs.account.self_info"
