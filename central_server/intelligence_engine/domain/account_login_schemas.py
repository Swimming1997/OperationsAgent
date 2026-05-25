from datetime import datetime

from intelligence_engine.domain.schemas import ApiModel


class AccountLoginSessionRead(ApiModel):
    id: str
    platform_account_id: str
    agent_id: str | None = None
    status: str
    error_message: str | None = None
    profile_key: str
    cdp_port: int | None = None
    claimed_by_agent_id: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    expires_at: datetime | None = None


class AccountLoginStartRequest(ApiModel):
    force: bool = False


class AccountLoginSessionStartResponse(ApiModel):
    session: AccountLoginSessionRead
    message: str


class AccountLoginResetResponse(ApiModel):
    account_id: str
    auth_status: str
    message: str


class AccountLoginProgressRequest(ApiModel):
    status: str
    error_message: str | None = None


class AccountLoginCompleteRequest(ApiModel):
    platform_nickname: str | None = None
    platform_home_url: str | None = None
    external_account_id: str | None = None


class AccountLoginFailRequest(ApiModel):
    error_message: str


class AccountLoginClaimResponse(ApiModel):
    sessions: list[AccountLoginSessionRead]
