from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import OperationRule, utcnow


class OperationRuleRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_rules(
        self,
        *,
        rule_type: str | None = None,
        platform: str | None = None,
        enabled: bool | None = None,
        keyword: str | None = None,
    ) -> list[OperationRule]:
        stmt = select(OperationRule).order_by(OperationRule.updated_at.desc())
        if rule_type:
            stmt = stmt.where(OperationRule.rule_type == rule_type)
        if platform:
            stmt = stmt.where((OperationRule.platform == platform) | (OperationRule.platform.is_(None)))
        if enabled is not None:
            stmt = stmt.where(OperationRule.enabled == enabled)
        if keyword:
            lowered = keyword.lower()
            stmt = stmt.where(
                or_(
                    func.lower(OperationRule.title).contains(lowered),
                    func.lower(OperationRule.content).contains(lowered),
                )
            )
        return list(self.db.scalars(stmt))

    def get(self, rule_id: str) -> OperationRule | None:
        return self.db.get(OperationRule, rule_id)

    def create(
        self,
        *,
        rule_type: str,
        title: str,
        content: str,
        platform: str | None,
        enabled: bool,
        created_by_user_id: str | None,
    ) -> OperationRule:
        row = OperationRule(
            rule_type=rule_type,
            title=title,
            content=content,
            platform=platform,
            enabled=enabled,
            version=1,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def update(
        self,
        rule: OperationRule,
        *,
        title: str | None = None,
        content: str | None = None,
        platform: str | None = None,
        enabled: bool | None = None,
        bump_version: bool = False,
    ) -> OperationRule:
        if title is not None:
            rule.title = title
        if content is not None:
            rule.content = content
        if platform is not None:
            rule.platform = platform or None
        if enabled is not None:
            rule.enabled = enabled
        if bump_version and (title is not None or content is not None):
            rule.version += 1
        rule.updated_at = utcnow()
        self.db.flush()
        return rule
