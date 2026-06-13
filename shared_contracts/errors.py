from typing import Any

from pydantic import Field

from shared_contracts.base import ApiModel
from shared_contracts.enums import ErrorCode


class ErrorPayload(ApiModel):
    code: ErrorCode
    message: str
    retryable: bool = False
    raw_context: dict[str, Any] = Field(default_factory=dict)


class JobFail(ApiModel):
    agent_id: str
    error: ErrorPayload
    checkpoint: dict[str, Any] = Field(default_factory=dict)

