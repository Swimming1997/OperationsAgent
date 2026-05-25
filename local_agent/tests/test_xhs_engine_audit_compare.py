from local_agent_runtime.audit.compare import compare_count, compare_text, compare_url, field_coverage


def test_compare_count_chinese_wan():
    assert compare_count("1.2万", 12000)


def test_compare_text_similarity():
    assert compare_text("SCI投稿经验", "这是一篇SCI投稿经验分享")


def test_compare_url_note_id_only():
    assert compare_url("https://www.xiaohongshu.com/explore/abc?xsec_token=1", "https://www.xiaohongshu.com/explore/abc?xsec_token=2")


def test_field_coverage():
    assert field_coverage([{"a": 1}, {"a": None}], ["a"]) == {"a": 0.5}
