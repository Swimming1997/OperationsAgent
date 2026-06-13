from shared_contracts.capabilities import xhs_local_agent_capabilities
from shared_contracts.enums import ErrorCode, JobStatus, JobType, Platform

from local_agent_runtime import enums as local_enums


def test_shared_contract_enums_align_with_local_runtime_values():
    assert {item.value for item in JobType} == {item.value for item in local_enums.JobType}
    assert {item.value for item in JobStatus} == {item.value for item in local_enums.JobStatus}
    assert {item.value for item in ErrorCode} == {item.value for item in local_enums.ErrorCode}
    assert Platform.XHS.value == local_enums.Platform.XHS.value


def test_shared_capability_helper_matches_local_agent_shape():
    capabilities = xhs_local_agent_capabilities(
        supports_cdp=True,
        supports_account_login=True,
        supported_job_types=[JobType.DETAIL_FETCH.value],
    )

    assert capabilities.platforms == ["xhs"]
    assert capabilities.job_types == ["detail_fetch"]
    assert capabilities.runtime == "local_agent_runtime_v1"
