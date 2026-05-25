from local_agent_runtime.audit.perf import PerfTimer


def test_perf_timer_outputs_total_ms():
    timer = PerfTimer()
    with timer.stage("api"):
        pass
    timer.set_items(2)
    summary = timer.summary()
    assert "total_ms" in summary
    assert "api_ms" in summary
    assert "items_per_second" in summary
