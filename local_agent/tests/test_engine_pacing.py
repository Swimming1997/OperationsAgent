import asyncio
import random

from local_agent_runtime.engine.pacing import BehaviorProfile, PacingController, ScrollStep


class FakeMouse:
    def __init__(self) -> None:
        self.wheel_calls: list[tuple[int, int]] = []

    async def wheel(self, dx: int, dy: int) -> None:
        self.wheel_calls.append((dx, dy))


class FakePage:
    def __init__(self) -> None:
        self.mouse = FakeMouse()
        self.waits: list[float] = []

    async def wait_for_timeout(self, timeout: float) -> None:
        self.waits.append(timeout)


def test_plan_scroll_values_are_within_profile_bounds():
    profile = BehaviorProfile(
        scroll_distance_px=(700, 2100),
        scroll_pause_ms=(650, 2400),
        reading_pause_probability=1.0,
        reading_pause_ms=(1800, 4200),
        backscroll_probability=1.0,
        backscroll_px=(180, 620),
    )
    controller = PacingController(profile, rng=random.Random(42))
    for _ in range(200):
        step = controller.plan_scroll()
        assert 700 <= step.distance_px <= 2100
        assert 650 <= step.pause_ms <= 2400
        # probabilities forced to 1.0 above
        assert 1800 <= step.reading_pause_ms <= 4200
        assert 180 <= step.back_px <= 620


def test_plan_scroll_is_not_constant_across_iterations():
    controller = PacingController(rng=random.Random(7))
    distances = {controller.plan_scroll().distance_px for _ in range(50)}
    pauses = {controller.plan_scroll().pause_ms for _ in range(50)}
    # The whole point of humanization: values must vary, not be fixed.
    assert len(distances) > 5
    assert len(pauses) > 5


def test_same_seed_is_deterministic():
    a = PacingController(rng=random.Random(123))
    b = PacingController(rng=random.Random(123))
    assert [a.plan_scroll() for _ in range(20)] == [b.plan_scroll() for _ in range(20)]


def test_probabilities_zero_disables_reading_and_backscroll():
    profile = BehaviorProfile(reading_pause_probability=0.0, backscroll_probability=0.0)
    controller = PacingController(profile, rng=random.Random(1))
    for _ in range(50):
        step = controller.plan_scroll()
        assert step.reading_pause_ms == 0
        assert step.back_px == 0


def test_human_scroll_drives_page_primitives():
    controller = PacingController(
        BehaviorProfile(backscroll_probability=1.0, reading_pause_probability=0.0),
        rng=random.Random(5),
    )
    page = FakePage()
    step = asyncio.run(controller.human_scroll(page))
    # forward scroll + back scroll
    assert page.mouse.wheel_calls[0][1] == step.distance_px
    assert any(dy < 0 for _, dy in page.mouse.wheel_calls)
    assert page.waits  # at least one dwell happened


def test_initial_dwell_waits_within_bounds():
    controller = PacingController(BehaviorProfile(initial_dwell_ms=(900, 2200)), rng=random.Random(9))
    page = FakePage()
    ms = asyncio.run(controller.initial_dwell(page))
    assert 900 <= ms <= 2200
    assert page.waits == [ms]


def test_from_mapping_hydrates_partial_payload_and_clamps():
    profile = BehaviorProfile.from_mapping(
        {
            "scroll_distance_px": [800, 1500],
            "scroll_pause_ms": 1000,
            "reading_pause_probability": 5.0,  # clamped to 1.0
            "unknown_key": "ignored",
        }
    )
    assert profile.scroll_distance_px == (800, 1500)
    assert profile.scroll_pause_ms == (1000, 1000)
    assert profile.reading_pause_probability == 1.0
    # untouched fields keep defaults
    assert profile.initial_dwell_ms == BehaviorProfile().initial_dwell_ms


def test_from_mapping_none_returns_defaults():
    assert BehaviorProfile.from_mapping(None) == BehaviorProfile()


def test_inter_job_delay_within_bounds():
    controller = PacingController(BehaviorProfile(inter_job_delay_ms=(3000, 12000)), rng=random.Random(3))
    for _ in range(50):
        assert 3000 <= controller.inter_job_delay_ms() <= 12000


def test_scroll_step_total_wait_prefers_reading_pause():
    step = ScrollStep(distance_px=1000, pause_ms=800, reading_pause_ms=3000, back_px=0)
    assert step.total_wait_ms == 3000
