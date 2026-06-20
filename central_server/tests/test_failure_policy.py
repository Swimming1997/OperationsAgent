from shared_contracts.failure_policy import classify_failure


def test_failure_policy_classifies_retry_and_account_health():
    rate_limited = classify_failure("rate_limited")
    assert rate_limited.category == "risk_control"
    assert rate_limited.retryable is True
    assert rate_limited.account_health == "cooling_down"

    timeout = classify_failure("job_execution_timeout")
    assert timeout.category == "timeout"
    assert timeout.retryable is True

    unknown = classify_failure("__unknown__")
    assert unknown.category == "unknown"
    assert unknown.retryable is False
