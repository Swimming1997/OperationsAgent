from local_agent_runtime.connectors.douyin import field as dy_field


def test_default_search_url_is_clean():
    url = dy_field.build_search_url("SCI论文")
    assert url.endswith("?type=general")
    assert "sort_type" not in url


def test_sort_most_liked_maps_to_param():
    url = dy_field.build_search_url("SCI论文", sort="most_liked")
    assert "sort_type=1" in url


def test_latest_and_publish_time_and_duration():
    url = dy_field.build_search_url("考研", sort="latest", publish_time="one_week", duration="1m_to_5m")
    assert "sort_type=2" in url
    assert "publish_time=7" in url
    assert "filter_duration=1-5" in url


def test_unknown_filters_omitted():
    url = dy_field.build_search_url("考研", sort="bogus", publish_time="bogus", duration="bogus")
    assert url.endswith("?type=general")
