from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import UserIntelligenceScenarioFilter, new_uuid


class UserIntelligenceScenarioFilterRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_user(self, user_id: str) -> list[UserIntelligenceScenarioFilter]:
        stmt = (
            select(UserIntelligenceScenarioFilter)
            .where(UserIntelligenceScenarioFilter.user_id == user_id)
            .order_by(UserIntelligenceScenarioFilter.scenario.asc())
        )
        return list(self.db.scalars(stmt).all())

    def get(self, user_id: str, scenario: str) -> UserIntelligenceScenarioFilter | None:
        stmt = select(UserIntelligenceScenarioFilter).where(
            UserIntelligenceScenarioFilter.user_id == user_id,
            UserIntelligenceScenarioFilter.scenario == scenario,
        )
        return self.db.scalars(stmt).first()

    def upsert(
        self,
        user_id: str,
        scenario: str,
        filters_json: dict,
        rolling_json: dict,
    ) -> UserIntelligenceScenarioFilter:
        row = self.get(user_id, scenario)
        if row is None:
            row = UserIntelligenceScenarioFilter(
                id=new_uuid(),
                user_id=user_id,
                scenario=scenario,
                filters_json=filters_json,
                rolling_json=rolling_json,
            )
            self.db.add(row)
        else:
            row.filters_json = filters_json
            row.rolling_json = rolling_json
        self.db.flush()
        return row

    def delete(self, user_id: str, scenario: str) -> bool:
        row = self.get(user_id, scenario)
        if row is None:
            return False
        self.db.delete(row)
        self.db.flush()
        return True
