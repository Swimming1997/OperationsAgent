from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from intelligence_engine.services.agent_selection import agent_sort_key
from sqlalchemy.orm import Session

from intelligence_engine.db.models import AccountLoginSession, AccountSession, LocalAgent, PlatformAccount, utcnow
from intelligence_engine.domain.enums import AuthStatus, LoginSessionStatus, SessionStatus
from intelligence_engine.services.agent_presence import is_agent_live
from intelligence_engine.services.agent_selection import agent_supports_account_login


LOGIN_SESSION_TTL_MINUTES = 15
CDP_PORT_BASE = 9300
CDP_PORT_MAX = 9499
ACTIVE_LOGIN_STATUSES = {
    LoginSessionStatus.CREATED.value,
    LoginSessionStatus.WAITING_AGENT.value,
    LoginSessionStatus.LAUNCHING_BROWSER.value,
    LoginSessionStatus.WAITING_USER_LOGIN.value,
    LoginSessionStatus.CHECKING_AUTH.value,
}


def profile_key_for_account(account_id: str) -> str:
    return f"accounts/{account_id}"


def is_agent_online(agent: LocalAgent | None, *, max_age_seconds: int = 90) -> bool:
    if not agent:
        return False
    return is_agent_live(agent, max_age_seconds=max_age_seconds)


class AccountLoginService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_account_profile_key(self, account: PlatformAccount) -> str:
        if not account.profile_key:
            account.profile_key = profile_key_for_account(account.id)
            self.db.flush()
        return account.profile_key

    def allocate_cdp_port(self, account: PlatformAccount) -> int:
        if account.login_cdp_port:
            return account.login_cdp_port
        used = {
            row
            for row in self.db.scalars(
                select(PlatformAccount.login_cdp_port).where(PlatformAccount.login_cdp_port.is_not(None))
            ).all()
            if row is not None
        }
        used |= {
            row
            for row in self.db.scalars(
                select(AccountLoginSession.cdp_port).where(AccountLoginSession.cdp_port.is_not(None))
            ).all()
            if row is not None
        }
        seed = sum(ord(char) for char in account.id) % 200
        for offset in range(200):
            port = CDP_PORT_BASE + ((seed + offset) % (CDP_PORT_MAX - CDP_PORT_BASE + 1))
            if port not in used:
                account.login_cdp_port = port
                self.db.flush()
                return port
        raise RuntimeError("no free CDP port in range")

    def expire_stale_sessions(self) -> int:
        now = utcnow()
        sessions = list(
            self.db.scalars(
                select(AccountLoginSession).where(AccountLoginSession.status.in_(ACTIVE_LOGIN_STATUSES))
            )
        )
        count = 0
        for session in sessions:
            expires_at = session.expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at and expires_at < now:
                session.status = LoginSessionStatus.EXPIRED.value
                session.finished_at = now
                session.error_message = session.error_message or "login session expired"
                account = self.db.get(PlatformAccount, session.platform_account_id)
                if account and account.auth_status == AuthStatus.LOGIN_PENDING.value:
                    account.auth_status = AuthStatus.ERROR.value
                count += 1
        self.db.flush()
        return count

    def get_active_session(self, account_id: str) -> AccountLoginSession | None:
        self.expire_stale_sessions()
        return self.db.scalar(
            select(AccountLoginSession)
            .where(AccountLoginSession.platform_account_id == account_id)
            .where(AccountLoginSession.status.in_(ACTIVE_LOGIN_STATUSES))
            .order_by(AccountLoginSession.created_at.desc())
            .limit(1)
        )

    def resolve_login_agent(self, account: PlatformAccount, *, preferred_agent_id: str | None = None) -> LocalAgent | None:
        candidate_ids: list[str] = []
        if preferred_agent_id:
            candidate_ids.append(preferred_agent_id)
        if account.default_agent_id and account.default_agent_id not in candidate_ids:
            candidate_ids.append(account.default_agent_id)
        agents: list[LocalAgent] = []
        for agent_id in candidate_ids:
            agent = self.db.get(LocalAgent, agent_id)
            if agent and agent.status != "retired":
                agents.append(agent)
        if account.employee_id:
            owned = list(
                self.db.scalars(
                    select(LocalAgent).where(
                        LocalAgent.employee_id == account.employee_id,
                        LocalAgent.status != "retired",
                    )
                )
            )
            for agent in owned:
                if agent.id not in {item.id for item in agents}:
                    agents.append(agent)
        agents.sort(key=agent_sort_key)
        for agent in agents:
            if is_agent_online(agent) and agent_supports_account_login(agent):
                return agent
        return agents[0] if agents else None

    def reset_login_state(self, account: PlatformAccount, *, reason: str | None = None) -> PlatformAccount:
        """Clear false-positive or stale login state so the operator can log in again."""
        self.expire_stale_sessions()
        now = utcnow()
        sessions = list(
            self.db.scalars(
                select(AccountLoginSession).where(
                    AccountLoginSession.platform_account_id == account.id,
                    AccountLoginSession.status.in_(ACTIVE_LOGIN_STATUSES),
                )
            )
        )
        for session in sessions:
            session.status = LoginSessionStatus.FAILED.value
            session.finished_at = now
            session.error_message = reason or "login reset by operator"
        account.auth_status = AuthStatus.NOT_LOGGED_IN.value
        account.last_verified_at = None
        self.db.flush()
        return account

    def start_login(
        self,
        account: PlatformAccount,
        *,
        preferred_agent_id: str | None = None,
        force: bool = False,
    ) -> AccountLoginSession:
        if force:
            self.reset_login_state(account, reason="re-login requested")
        self.expire_stale_sessions()
        active = self.get_active_session(account.id)
        if active:
            if active.status == LoginSessionStatus.WAITING_AGENT.value and not active.claimed_by_agent_id:
                replacement = self.resolve_login_agent(account)
                if replacement and active.agent_id != replacement.id and is_agent_online(replacement):
                    active.agent_id = replacement.id
                    self.db.flush()
            return active

        profile_key = self.ensure_account_profile_key(account)
        agent_id = preferred_agent_id or account.default_agent_id
        agent = self.db.get(LocalAgent, agent_id) if agent_id else None
        if not agent or agent.status == "retired":
            agent = self.resolve_login_agent(account, preferred_agent_id=preferred_agent_id)
            agent_id = agent.id if agent else None
        cdp_port = self.allocate_cdp_port(account)
        now = utcnow()
        initial_status = (
            LoginSessionStatus.CREATED.value
            if is_agent_online(agent)
            else LoginSessionStatus.WAITING_AGENT.value
        )
        session = AccountLoginSession(
            platform_account_id=account.id,
            agent_id=agent_id,
            status=initial_status,
            profile_key=profile_key,
            cdp_port=cdp_port,
            started_at=now,
            expires_at=now + timedelta(minutes=LOGIN_SESSION_TTL_MINUTES),
        )
        account.auth_status = AuthStatus.LOGIN_PENDING.value
        self.db.add(session)
        self.db.flush()
        return session

    def reroute_waiting_sessions_for_account(self, account: PlatformAccount, *, agent_id: str | None) -> int:
        """Point unclaimed waiting sessions at the account's current default agent."""
        if not agent_id:
            return 0
        target = self.db.get(LocalAgent, agent_id)
        if not target or not is_agent_online(target):
            return 0
        sessions = list(
            self.db.scalars(
                select(AccountLoginSession)
                .where(AccountLoginSession.platform_account_id == account.id)
                .where(AccountLoginSession.status == LoginSessionStatus.WAITING_AGENT.value)
                .where(AccountLoginSession.claimed_by_agent_id.is_(None))
            )
        )
        count = 0
        for session in sessions:
            if session.agent_id != agent_id:
                session.agent_id = agent_id
                count += 1
        if count:
            self.db.flush()
        return count

    def _session_claimable_by_agent(
        self,
        session: AccountLoginSession,
        account: PlatformAccount,
        agent: LocalAgent,
    ) -> bool:
        if session.claimed_by_agent_id:
            return False
        if session.status not in (LoginSessionStatus.CREATED.value, LoginSessionStatus.WAITING_AGENT.value):
            return False
        if session.agent_id == agent.id or account.default_agent_id == agent.id:
            return True
        if session.agent_id is None and account.employee_id and account.employee_id == agent.employee_id:
            return is_agent_online(agent) and agent_supports_account_login(agent)
        if session.status != LoginSessionStatus.WAITING_AGENT.value:
            return False
        if not account.employee_id or account.employee_id != agent.employee_id:
            return False
        if not is_agent_online(agent) or not agent_supports_account_login(agent):
            return False
        bound_agent = self.db.get(LocalAgent, session.agent_id) if session.agent_id else None
        if bound_agent and is_agent_online(bound_agent) and bound_agent.id != agent.id:
            return False
        return True

    def claim_sessions_for_agent(self, agent_id: str, *, max_sessions: int = 1) -> list[AccountLoginSession]:
        self.expire_stale_sessions()
        agent = self.db.get(LocalAgent, agent_id)
        if not agent or agent.status == "retired":
            return []
        if not is_agent_online(agent) or not agent_supports_account_login(agent):
            return []
        stmt = (
            select(AccountLoginSession)
            .join(PlatformAccount, PlatformAccount.id == AccountLoginSession.platform_account_id)
            .where(AccountLoginSession.status.in_([LoginSessionStatus.CREATED.value, LoginSessionStatus.WAITING_AGENT.value]))
            .where(AccountLoginSession.claimed_by_agent_id.is_(None))
            .order_by(AccountLoginSession.created_at.asc())
        )
        candidates = list(self.db.scalars(stmt))
        claimed: list[AccountLoginSession] = []
        now = utcnow()
        for session in candidates:
            if len(claimed) >= max_sessions:
                break
            account = self.db.get(PlatformAccount, session.platform_account_id)
            if not account or not self._session_claimable_by_agent(session, account, agent):
                continue
            session.claimed_by_agent_id = agent_id
            session.claimed_at = now
            session.agent_id = agent_id
            session.status = LoginSessionStatus.LAUNCHING_BROWSER.value
            claimed.append(session)
        if claimed:
            self.db.flush()
        return claimed

    def update_progress(self, session: AccountLoginSession, status: LoginSessionStatus, *, error_message: str | None = None) -> AccountLoginSession:
        session.status = status.value
        if error_message:
            session.error_message = error_message
        self.db.flush()
        return session

    def complete_login(
        self,
        session: AccountLoginSession,
        *,
        platform_nickname: str | None = None,
        platform_home_url: str | None = None,
        external_account_id: str | None = None,
    ) -> PlatformAccount:
        account = self.db.get(PlatformAccount, session.platform_account_id)
        if not account:
            raise KeyError(session.platform_account_id)
        now = utcnow()
        session.status = LoginSessionStatus.LOGGED_IN.value
        session.finished_at = now
        account.auth_status = AuthStatus.ACTIVE.value
        account.last_verified_at = now
        if platform_nickname:
            account.platform_nickname = platform_nickname
        if platform_home_url:
            account.platform_home_url = platform_home_url
        if external_account_id and not account.external_account_id:
            account.external_account_id = external_account_id
        profile_key = session.profile_key
        agent_id = session.agent_id or session.claimed_by_agent_id
        if agent_id:
            existing = self.db.scalar(
                select(AccountSession)
                .where(AccountSession.account_id == account.id)
                .where(AccountSession.local_agent_id == agent_id)
                .where(AccountSession.session_type == "managed_chrome")
            )
            session_meta = {
                "cdp_url": f"http://127.0.0.1:{session.cdp_port}" if session.cdp_port else None,
                "profile_key": profile_key,
            }
            if existing:
                existing.profile_ref = profile_key
                existing.status = SessionStatus.READY.value
                existing.session_meta_json = {**(existing.session_meta_json or {}), **{k: v for k, v in session_meta.items() if v}}
                existing.last_validated_at = now
            else:
                self.db.add(
                    AccountSession(
                        account_id=account.id,
                        local_agent_id=agent_id,
                        platform=account.platform,
                        session_type="managed_chrome",
                        profile_ref=profile_key,
                        status=SessionStatus.READY.value,
                        session_meta_json=session_meta,
                        last_validated_at=now,
                    )
                )
        self.db.flush()
        return account

    def fail_login(self, session: AccountLoginSession, *, error_message: str) -> PlatformAccount:
        account = self.db.get(PlatformAccount, session.platform_account_id)
        now = utcnow()
        session.status = LoginSessionStatus.FAILED.value
        session.finished_at = now
        session.error_message = error_message
        if account:
            account.auth_status = AuthStatus.ERROR.value
        self.db.flush()
        return account  # type: ignore[return-value]
