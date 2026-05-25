# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
from intelligence_engine.local_agent.xhs_main_chain_smoke_runner import context_loss_layers, has_xhs_xsec_context


def test_has_xhs_xsec_context_checks_token_and_source():
    assert has_xhs_xsec_context({"platform_context": {"xsec_token": "TOKEN", "xsec_source": "pc_feed"}})
    assert not has_xhs_xsec_context({"platform_context": {"xsec_token": "TOKEN"}})
    assert not has_xhs_xsec_context({"platform_context": {}})


def test_context_loss_layers_pinpoints_missing_stage():
    assert context_loss_layers(
        homefeed_sample_count=10,
        homefeed_with_xsec_context_count=8,
        detail_selected_count=5,
        detail_with_xsec_context_count=5,
        comment_selected_count=5,
        comment_with_xsec_context_count=4,
    ) == ["homefeed_candidate", "comment_job_payload"]
