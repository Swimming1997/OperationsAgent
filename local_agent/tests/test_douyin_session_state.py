from local_agent_runtime.enums import SessionStatus
from local_agent_runtime.sessions.douyin_browser_session import evaluate_douyin_login_state


def test_ready_when_local_storage_flag_set():
    status, _ = evaluate_douyin_login_state(
        url="https://www.douyin.com/",
        visible_text="首页 推荐 关注",
        has_user_login="1",
        login_status_cookie=None,
    )
    assert status == SessionStatus.READY


def test_ready_when_login_status_cookie_set():
    status, _ = evaluate_douyin_login_state(
        url="https://www.douyin.com/",
        visible_text="推荐",
        has_user_login=None,
        login_status_cookie="1",
    )
    assert status == SessionStatus.READY


def test_manual_verify_on_captcha_page():
    status, _ = evaluate_douyin_login_state(
        url="https://www.douyin.com/",
        visible_text="请完成验证",
        has_user_login="1",
        login_status_cookie="1",
        page_title="验证码中间页",
    )
    assert status == SessionStatus.MANUAL_VERIFY_REQUIRED


def test_expired_when_login_dialog_visible():
    status, _ = evaluate_douyin_login_state(
        url="https://www.douyin.com/",
        visible_text="登录 验证码登录 扫码登录",
        has_user_login="0",
        login_status_cookie="0",
    )
    assert status == SessionStatus.EXPIRED


def test_expired_when_no_signal():
    status, _ = evaluate_douyin_login_state(
        url="https://www.douyin.com/",
        visible_text="推荐",
        has_user_login=None,
        login_status_cookie=None,
    )
    assert status == SessionStatus.EXPIRED
