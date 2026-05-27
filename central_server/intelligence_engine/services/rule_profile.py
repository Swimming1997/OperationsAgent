from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import RuleProfile
from intelligence_engine.domain.enums import Platform


DEFAULT_RULE_PROFILE_CONFIGS: list[dict[str, Any]] = [
    {
        "name": "小红书获客库默认规则",
        "platform": Platform.XHS.value,
        "library_type": "lead",
        "config": {
            "lead_intent_required": True,
            "rating_thresholds": {"medium": 10, "good": 100},
        },
    },
    {
        "name": "小红书非获客库默认规则",
        "platform": Platform.XHS.value,
        "library_type": "non_lead",
        "config": {
            "lead_intent_required": False,
            "rating_thresholds": {"poor": 50, "medium": 200, "good": 500},
        },
    },
    {
        "name": "抖音获客库默认规则",
        "platform": Platform.DOUYIN.value,
        "library_type": "lead",
        "config": {
            "lead_intent_required": True,
            "rating_thresholds": {"medium": 100, "good": 500},
        },
    },
    {
        "name": "抖音非获客库默认规则",
        "platform": Platform.DOUYIN.value,
        "library_type": "non_lead",
        "config": {
            "lead_intent_required": False,
            "rating_thresholds": {"poor": 100, "medium": 500, "good": 1000},
        },
    },
]


class RuleProfileService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_defaults(self, *, created_by_user_id: str | None = None) -> list[RuleProfile]:
        profiles: list[RuleProfile] = []
        for spec in DEFAULT_RULE_PROFILE_CONFIGS:
            existing = self.get_enabled(platform=spec["platform"], library_type=spec["library_type"])
            if existing:
                profiles.append(existing)
                continue
            profile = RuleProfile(
                name=spec["name"],
                platform=spec["platform"],
                library_type=spec["library_type"],
                version=1,
                enabled=True,
                config_json=spec["config"],
                created_by_user_id=created_by_user_id,
            )
            self.db.add(profile)
            self.db.flush()
            profiles.append(profile)
        return profiles

    def list_profiles(self, *, include_disabled: bool = False) -> list[RuleProfile]:
        self.ensure_defaults()
        stmt = select(RuleProfile).order_by(RuleProfile.platform.asc(), RuleProfile.library_type.asc(), RuleProfile.version.desc())
        if not include_disabled:
            stmt = stmt.where(RuleProfile.enabled.is_(True))
        return list(self.db.scalars(stmt))

    def get_enabled(self, *, platform: str, library_type: str) -> RuleProfile | None:
        return self.db.scalar(
            select(RuleProfile).where(
                RuleProfile.platform == platform,
                RuleProfile.library_type == library_type,
                RuleProfile.enabled.is_(True),
            )
        )

    def update_profile(
        self,
        profile: RuleProfile,
        *,
        name: str | None = None,
        enabled: bool | None = None,
        config: dict[str, Any] | None = None,
    ) -> RuleProfile:
        if name is not None:
            profile.name = name
        if enabled is not None:
            profile.enabled = enabled
        if config is not None:
            profile.config_json = config
            profile.version += 1
        self.db.flush()
        return profile
