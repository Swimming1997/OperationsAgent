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
    fresh_profile: bool = False


class AccountLoginStartRequest(ApiModel):
    force: bool = False
    preferred_agent_id: str | None = None


class AccountLoginSessionStartResponse(ApiModel):
    session: AccountLoginSessionRead
    message: str


class AccountLoginResetResponse(ApiModel):
    account_id: str
    auth_status: str
    message: str


class BridgeChromeContextResponse(ApiModel):
    account_id: str
    profile_key: str
    login_cdp_port: int


class SyncLocalBridgeLoginRequest(ApiModel):
    preferred_agent_id: str | None = None
    login_cdp_port: int | None = None
    platform_nickname: str | None = None
    platform_home_url: str | None = None
    bridge_status: str = "ready"


class SyncLocalBridgeLoginResponse(ApiModel):
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
