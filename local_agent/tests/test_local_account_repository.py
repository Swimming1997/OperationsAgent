import pytest

from local_agent_runtime.storage import LocalAccountRepository
from local_agent_runtime.storage.account_repository import (
    CDP_PORT_RANGE_END,
    CDP_PORT_RANGE_START,
)


def test_create_account_allocates_profile_and_port(tmp_path):
    repo = LocalAccountRepository(tmp_path / "local.db")

    account = repo.create_account(platform="xhs", display_name="主号")

    assert account["platform"] == "xhs"
    assert account["display_name"] == "主号"
    assert account["auth_status"] == "not_logged_in"
    assert account["profile_key"] == f"accounts/{account['id']}"
    assert CDP_PORT_RANGE_START <= account["cdp_port"] <= CDP_PORT_RANGE_END
    assert account["metadata"] == {}


def test_distinct_accounts_get_distinct_ports(tmp_path):
    repo = LocalAccountRepository(tmp_path / "local.db")

    a = repo.create_account(platform="xhs")
    b = repo.create_account(platform="douyin")

    assert a["cdp_port"] != b["cdp_port"]
    assert a["profile_key"] != b["profile_key"]


def test_list_and_filter_by_platform(tmp_path):
    repo = LocalAccountRepository(tmp_path / "local.db")
    repo.create_account(platform="xhs", display_name="x1")
    repo.create_account(platform="xhs", display_name="x2")
    repo.create_account(platform="douyin", display_name="d1")

    assert len(repo.list_accounts()) == 3
    assert len(repo.list_accounts(platform="xhs")) == 2
    assert len(repo.list_accounts(platform="douyin")) == 1


def test_login_lifecycle_updates_status(tmp_path):
    repo = LocalAccountRepository(tmp_path / "local.db")
    account = repo.create_account(platform="xhs")
    account_id = account["id"]

    pending = repo.mark_login_pending(account_id)
    assert pending["auth_status"] == "login_pending"

    logged_in = repo.mark_logged_in(
        account_id,
        platform_nickname="昵称",
        platform_home_url="https://www.xiaohongshu.com/user/profile/abc",
        external_account_id="abc",
    )
    assert logged_in["auth_status"] == "active"
    assert logged_in["health_status"] == "healthy"
    assert logged_in["platform_nickname"] == "昵称"
    assert logged_in["external_account_id"] == "abc"
    assert logged_in["last_verified_at"] is not None


def test_login_failure_records_error_and_increments(tmp_path):
    repo = LocalAccountRepository(tmp_path / "local.db")
    account_id = repo.create_account(platform="xhs")["id"]

    failed = repo.mark_login_failed(account_id, error="login timed out")
    assert failed["auth_status"] == "error"
    assert failed["consecutive_failures"] == 1
    assert failed["metadata"].get("last_login_error") == "login timed out"

    failed_again = repo.mark_login_failed(account_id, error="blocked")
    assert failed_again["consecutive_failures"] == 2


def test_update_and_delete_account(tmp_path):
    repo = LocalAccountRepository(tmp_path / "local.db")
    account_id = repo.create_account(platform="xhs", display_name="old")["id"]

    updated = repo.update_account(account_id, display_name="new", status="inactive")
    assert updated["display_name"] == "new"
    assert updated["status"] == "inactive"

    assert repo.delete_account(account_id) is True
    assert repo.get_account(account_id) is None


def test_missing_account_raises(tmp_path):
    repo = LocalAccountRepository(tmp_path / "local.db")
    with pytest.raises(ValueError):
        repo.mark_login_pending("does-not-exist")
    with pytest.raises(ValueError):
        repo.set_auth_status("does-not-exist", "active")
