from __future__ import annotations

from pathlib import Path

from local_agent_runtime.profile_manager import clear_chromium_login_state, prepare_profile_for_login


def test_clear_chromium_login_state_removes_cookies(tmp_path: Path):
    profile_dir = tmp_path / "accounts" / "demo"
    default = profile_dir / "Default"
    default.mkdir(parents=True)
    (default / "Cookies").write_text("dummy", encoding="utf-8")
    (default / "Local Storage").mkdir()

    clear_chromium_login_state(profile_dir)

    assert not (default / "Cookies").exists()
    assert not (default / "Local Storage").exists()


def test_prepare_profile_for_login_clears_when_fresh(tmp_path: Path):
    profile_key = "accounts/acct-1"
    profile_dir = tmp_path / "profiles" / "accounts" / profile_key
    default = profile_dir / "Default"
    default.mkdir(parents=True)
    (default / "Cookies").write_text("cookie", encoding="utf-8")

    prepare_profile_for_login(
        project_root=tmp_path,
        profile_key=profile_key,
        cdp_port=19999,
        fresh_profile=True,
    )

    assert not (default / "Cookies").exists()
