from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="INTEL_ENGINE_")

    database_url: str = "sqlite:///./data/intelligence_engine.db"
    app_name: str = "Intelligence Engine"
    app_version: str = "0.1.0"
    claim_ttl_seconds: int = 300
    job_running_timeout_seconds: int = 1800
    detail_lease_ttl_seconds: int = 300
    comment_lease_ttl_seconds: int = 600
    creator_lease_ttl_seconds: int = 600
    default_comment_limit: int = 20
    enqueue_detail_policy: str = "candidate_only"
    enqueue_comment_policy: str = "high_comment_only"
    detail_auto_like_threshold: int = 50
    detail_auto_search_rank_threshold: int = 20
    detail_auto_feed_position_threshold: int = 30
    comment_auto_count_threshold: int = 10
    xhs_homefeed_url: str = "https://www.xiaohongshu.com/explore"
    xhs_probe_scroll_pause_ms: int = 1200
    auth_secret_key: str = "dev-change-me-in-production"
    auth_token_ttl_hours: int = 24
    allow_header_auth: bool = False
    media_root: str = "./data/media"
    media_signing_secret: str | None = None
    media_url_ttl_seconds: int = 86400
    media_allowed_hosts: str = "xhscdn.com,xiaohongshu.com,sns-webpic-qc.xhscdn.com,sns-img-qc.xhscdn.com"
    media_fetch_timeout_seconds: float = 15.0
    media_referer: str = "https://www.xiaohongshu.com/"

    @property
    def media_signing_key(self) -> str:
        return self.media_signing_secret or self.auth_secret_key

    @property
    def media_allowed_host_set(self) -> frozenset[str]:
        return frozenset(host.strip().lower() for host in self.media_allowed_hosts.split(",") if host.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
