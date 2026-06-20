import random

from local_agent_runtime.engine.poll_backoff import IdlePollBackoff


def test_idle_poll_backoff_grows_to_cap_and_resets_on_work():
    backoff = IdlePollBackoff(
        minimum_seconds=5,
        maximum_seconds=20,
        multiplier=2,
        jitter_ratio=0,
    )

    assert [backoff.next_delay(handled_count=0) for _ in range(4)] == [5, 10, 20, 20]
    assert backoff.next_delay(handled_count=1) == 5
    assert backoff.next_delay(handled_count=0) == 5


def test_poll_backoff_adds_bounded_jitter():
    backoff = IdlePollBackoff(
        minimum_seconds=10,
        maximum_seconds=30,
        multiplier=2,
        jitter_ratio=0.2,
        rng=random.Random(7),
    )

    delay = backoff.next_delay(handled_count=0)
    assert 8 <= delay <= 12


def test_request_failure_uses_faster_backoff_growth():
    backoff = IdlePollBackoff(
        minimum_seconds=2,
        maximum_seconds=20,
        multiplier=1.5,
        jitter_ratio=0,
    )

    assert backoff.next_delay(handled_count=0, request_failed=True) == 4
    assert backoff.next_delay(handled_count=0, request_failed=True) == 8


def test_jitter_never_exceeds_maximum_delay():
    backoff = IdlePollBackoff(
        minimum_seconds=30,
        maximum_seconds=30,
        multiplier=2,
        jitter_ratio=0.5,
        rng=random.Random(2),
    )
    assert backoff.next_delay(handled_count=0) <= 30
