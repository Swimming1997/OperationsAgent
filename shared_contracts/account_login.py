from shared_contracts.base import ApiModel


class ClaimedLoginSession(ApiModel):
    session_id: str
    platform_account_id: str
    profile_key: str
    cdp_port: int
    fresh_profile: bool = False

