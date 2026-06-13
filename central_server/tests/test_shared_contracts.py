from datetime import datetime, timezone

from shared_contracts.capabilities import xhs_local_agent_capabilities
from shared_contracts.enums import ErrorCode, JobStatus, JobType, Platform
from shared_contracts.errors import ErrorPayload, JobFail
from shared_contracts.ingestion import FeedCandidateInput

from intelligence_engine.domain import enums as central_enums


def test_shared_contract_enums_align_with_central_runtime_values():
    assert {item.value for item in JobType} == {item.value for item in central_enums.JobType}
    assert {item.value for item in JobStatus} == {item.value for item in central_enums.JobStatus}
    assert {item.value for item in ErrorCode} == {item.value for item in central_enums.ErrorCode}
    assert Platform.XHS.value == central_enums.Platform.XHS.value


def test_shared_contract_payloads_serialize_for_http_json():
    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="note-1",
        source_surface="search",
        discovered_at=datetime.now(timezone.utc),
    )
    failure = JobFail(
        agent_id="agent-1",
        error=ErrorPayload(code=ErrorCode.RETRYABLE_NETWORK_ERROR, message="temporary", retryable=True),
    )
    capabilities = xhs_local_agent_capabilities(
        supports_cdp=True,
        supports_account_login=True,
        supported_job_types=[JobType.FEED_COLLECT.value],
    )

    assert candidate.model_dump(mode="json")["platform"] == "xhs"
    assert failure.model_dump(mode="json")["error"]["code"] == "retryable_network_error"
    assert capabilities.model_dump(mode="json")["job_types"] == ["feed_collect"]

