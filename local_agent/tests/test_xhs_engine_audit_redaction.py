from local_agent_runtime.audit.redaction import redact_mapping, redact_text, redact_url


def test_redaction_masks_sensitive_headers_and_tokens():
    payload = {
        "Cookie": "a1=secret-cookie",
        "X-S": "signed-value",
        "X-T": "timestamp",
        "x-S-Common": "common",
        "url": "https://www.xiaohongshu.com/explore/abc?xsec_token=abcdefghijklmnop&xsec_source=pc_search",
        "phone": "13800138000",
        "text": "验证码 123456 cookie: raw",
    }
    redacted = redact_mapping(payload)
    blob = str(redacted)
    assert "secret-cookie" not in blob
    assert "signed-value" not in blob
    assert "abcdefghijklmnop" not in blob
    assert "13800138000" not in blob
    assert "验证码" not in blob


def test_redact_url_keeps_token_prefix_suffix_only():
    url = redact_url("https://x.test/path?xsec_token=abcdefghijklmnop")
    assert "abcd***mnop" in url


def test_redact_text_masks_headers():
    assert "raw-cookie" not in redact_text("Cookie: raw-cookie")


def test_redact_text_masks_url_encoded_xsec_token():
    encoded = (
        "https://www.xiaohongshu.com/404?redirectPath=https%3A%2F%2Fwww.xiaohongshu.com"
        "%2Fexplore%2Fabc%3Fxsec_token%3Dabcdefghijklmnop%26xsec_source%3Dpc_search"
    )
    redacted = redact_text(encoded)
    assert "abcdefghijklmnop" not in redacted
    assert "xsec_token%3Dabcd***" in redacted


def test_account_summary_fields_are_not_redacted():
    payload = {
        "account_summary": {
            "nickname": "真实昵称",
            "user_id": "5f58bd990000000001003753",
            "home_url": "https://www.xiaohongshu.com/user/profile/5f58bd990000000001003753",
            "source": "signed_api_selfinfo",
        },
        "payload": {"Cookie": "a1=secret-cookie", "X-S": "signed-value"},
    }
    redacted = redact_mapping(payload)
    assert redacted["account_summary"]["nickname"] == "真实昵称"
    assert redacted["account_summary"]["user_id"] == "5f58bd990000000001003753"
    assert "secret-cookie" not in str(redacted)
    assert "signed-value" not in str(redacted)
