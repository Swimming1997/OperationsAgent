from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from intelligence_engine.api.account_access import ensure_account_readable, ensure_account_writable, get_principal_employee_id
from intelligence_engine.db.models import AccountLoginSession, PlatformAccount
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.account_login_schemas import (
    AccountLoginClaimResponse,
    AccountLoginCompleteRequest,
    AccountLoginFailRequest,
    AccountLoginProgressRequest,
    AccountLoginResetResponse,
    AccountLoginSessionRead,
    AccountLoginStartRequest,
    AccountLoginSessionStartResponse,
)
from intelligence_engine.domain.enums import LoginSessionStatus, UserRoleName
from intelligence_engine.security.auth import Principal, get_optional_principal, require_any_role
from intelligence_engine.services.account_login_service import AccountLoginService

router = APIRouter(prefix="/api", tags=["account-login"])


def _session_read(session: AccountLoginSession) -> AccountLoginSessionRead:
    return AccountLoginSessionRead(
        id=session.id,
        platform_account_id=session.platform_account_id,
        agent_id=session.agent_id,
        status=session.status,
        error_message=session.error_message,
        profile_key=session.profile_key,
        cdp_port=session.cdp_port,
        claimed_by_agent_id=session.claimed_by_agent_id,
        started_at=session.started_at,
        finished_at=session.finished_at,
        expires_at=session.expires_at,
    )


def _waiting_message(session: AccountLoginSession) -> str:
    if session.status == LoginSessionStatus.WAITING_AGENT.value:
        return "等待本地 Agent 上线后将自动打开浏览器"
    if session.status == LoginSessionStatus.WAITING_USER_LOGIN.value:
        return "浏览器已打开，请在 Chrome 中完成小红书登录"
    if session.status == LoginSessionStatus.CHECKING_AUTH.value:
        return "正在校验登录状态"
    if session.status == LoginSessionStatus.LAUNCHING_BROWSER.value:
        return "正在启动浏览器"
    return "登录会话已创建"


@router.post("/product/accounts/{account_id}/login-sessions/reset", response_model=AccountLoginResetResponse)
def reset_account_login(
    account_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    account = db.get(PlatformAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    ensure_account_writable(db, principal, account)
    AccountLoginService(db).reset_login_state(account)
    db.commit()
    return AccountLoginResetResponse(
        account_id=account.id,
        auth_status=account.auth_status,
        message="登录已取消，可重新发起登录",
    )


@router.post("/product/accounts/{account_id}/login-sessions", response_model=AccountLoginSessionStartResponse)
def start_account_login(
    account_id: str,
    request: AccountLoginStartRequest | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    account = db.get(PlatformAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    ensure_account_writable(db, principal, account)
    service = AccountLoginService(db)
    body = request or AccountLoginStartRequest()
    session = service.start_login(account, force=body.force)
    db.commit()
    return AccountLoginSessionStartResponse(session=_session_read(session), message=_waiting_message(session))


@router.get("/product/accounts/{account_id}/login-sessions/active", response_model=AccountLoginSessionRead | None)
def get_active_account_login(
    account_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    account = db.get(PlatformAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    ensure_account_readable(db, principal, account)
    session = AccountLoginService(db).get_active_session(account_id)
    db.commit()
    return _session_read(session) if session else None


@router.get("/product/login-sessions/{session_id}", response_model=AccountLoginSessionRead)
def get_login_session(
    session_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    session = db.get(AccountLoginSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="login session not found")
    account = db.get(PlatformAccount, session.platform_account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    ensure_account_readable(db, principal, account)
    AccountLoginService(db).expire_stale_sessions()
    db.commit()
    return _session_read(session)


@router.post("/agents/{agent_id}/login-sessions/claim", response_model=AccountLoginClaimResponse)
def claim_login_sessions(agent_id: str, db: Session = Depends(get_db), max_sessions: int = 1):
    sessions = AccountLoginService(db).claim_sessions_for_agent(agent_id, max_sessions=max_sessions)
    db.commit()
    return AccountLoginClaimResponse(sessions=[_session_read(item) for item in sessions])


@router.post("/agents/{agent_id}/login-sessions/{session_id}/progress", response_model=AccountLoginSessionRead)
def report_login_progress(
    agent_id: str,
    session_id: str,
    request: AccountLoginProgressRequest,
    db: Session = Depends(get_db),
):
    session = db.get(AccountLoginSession, session_id)
    if not session or session.claimed_by_agent_id != agent_id:
        raise HTTPException(status_code=404, detail="login session not found")
    try:
        status = LoginSessionStatus(request.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid login session status") from exc
    AccountLoginService(db).update_progress(session, status, error_message=request.error_message)
    db.commit()
    return _session_read(session)


@router.post("/agents/{agent_id}/login-sessions/{session_id}/complete", response_model=AccountLoginSessionRead)
def complete_login_session(
    agent_id: str,
    session_id: str,
    request: AccountLoginCompleteRequest,
    db: Session = Depends(get_db),
):
    session = db.get(AccountLoginSession, session_id)
    if not session or session.claimed_by_agent_id != agent_id:
        raise HTTPException(status_code=404, detail="login session not found")
    AccountLoginService(db).complete_login(
        session,
        platform_nickname=request.platform_nickname,
        platform_home_url=request.platform_home_url,
        external_account_id=request.external_account_id,
    )
    db.commit()
    return _session_read(session)


@router.post("/agents/{agent_id}/login-sessions/{session_id}/fail", response_model=AccountLoginSessionRead)
def fail_login_session(
    agent_id: str,
    session_id: str,
    request: AccountLoginFailRequest,
    db: Session = Depends(get_db),
):
    session = db.get(AccountLoginSession, session_id)
    if not session or session.claimed_by_agent_id != agent_id:
        raise HTTPException(status_code=404, detail="login session not found")
    AccountLoginService(db).fail_login(session, error_message=request.error_message)
    db.commit()
    return _session_read(session)
