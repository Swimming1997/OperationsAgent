from datetime import datetime
from typing import Any

from pydantic import Field

from shared_contracts.base import ApiModel
from shared_contracts.enums import JobStatus, JobType


class ClaimedJob(ApiModel):
    job_id: str
    job_type: JobType
    account_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    claim_expires_at: datetime


class JobStart(ApiModel):
    agent_id: str


class JobProgress(ApiModel):
    agent_id: str
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    partial_metrics: dict[str, Any] = Field(default_factory=dict)


class JobComplete(ApiModel):
    agent_id: str
    status: JobStatus = JobStatus.SUCCESS
    result_summary: dict[str, Any] = Field(default_factory=dict)

