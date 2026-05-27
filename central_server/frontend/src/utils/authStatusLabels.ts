/** Session statuses where the user is actively going through browser login. */
const LOGIN_IN_PROGRESS_SESSIONS = new Set([
  'launching_browser',
  'waiting_user_login',
  'checking_auth',
]);

const WAITING_AGENT_SESSIONS = new Set(['waiting_agent']);

export function labelAuthStatus(status: string) {
  switch (status) {
    case 'not_logged_in':
      return '未登录';
    case 'login_pending':
      return '登录中';
    case 'active':
      return '已登录';
    case 'expired':
      return '已过期';
    case 'error':
      return '登录异常';
    default:
      return status;
  }
}

export function labelLoginSessionStatus(status: string) {
  switch (status) {
    case 'created':
      return '准备中';
    case 'waiting_agent':
      return '等待 Agent 上线';
    case 'launching_browser':
      return '正在启动浏览器';
    case 'waiting_user_login':
      return '等待浏览器内登录';
    case 'checking_auth':
      return '校验登录态';
    case 'logged_in':
      return '已登录';
    case 'failed':
      return '登录失败';
    case 'expired':
      return '会话超时';
    default:
      return status;
  }
}

export type AccountLoginBadgeSource = {
  auth_status: string;
  active_login_session_status?: string | null;
};

/** User-facing login badge on list/detail (prefers active session over coarse auth_status). */
export function labelAccountLoginBadge(account: AccountLoginBadgeSource): string {
  const session = account.active_login_session_status;
  if (account.auth_status === 'active' && (!session || session === 'logged_in')) {
    return '已登录';
  }
  if (session && WAITING_AGENT_SESSIONS.has(session)) {
    return '等待本地助手';
  }
  if (session === 'created') {
    return '准备中';
  }
  if (session && LOGIN_IN_PROGRESS_SESSIONS.has(session)) {
    return '登录中';
  }
  if (session === 'logged_in') {
    return '已登录';
  }
  if (session === 'failed') {
    return '登录失败';
  }
  if (session === 'expired') {
    return '会话超时';
  }
  if (account.auth_status === 'not_logged_in') {
    return '未登录';
  }
  if (account.auth_status === 'login_pending') {
    return '登录中';
  }
  if (account.auth_status === 'expired') {
    return '已过期';
  }
  if (account.auth_status === 'error') {
    return '登录异常';
  }
  return labelAuthStatus(account.auth_status);
}

export function authPillClassForAccount(account: AccountLoginBadgeSource): string {
  const session = account.active_login_session_status;
  if (account.auth_status === 'active' && (!session || session === 'logged_in')) {
    return 'auth-active';
  }
  if (session && WAITING_AGENT_SESSIONS.has(session)) {
    return 'auth-waiting_agent';
  }
  if (session === 'created') {
    return 'auth-login_pending';
  }
  if (session && LOGIN_IN_PROGRESS_SESSIONS.has(session)) {
    return 'auth-login_pending';
  }
  if (session === 'failed' || account.auth_status === 'error') {
    return 'auth-error';
  }
  if (session === 'expired' || account.auth_status === 'expired') {
    return 'auth-expired';
  }
  return `auth-${account.auth_status}`;
}

export function isWaitingForAgent(account: AccountLoginBadgeSource, sessionStatus?: string | null): boolean {
  const session = sessionStatus ?? account.active_login_session_status;
  return Boolean(session && WAITING_AGENT_SESSIONS.has(session));
}

export function isLoginSessionInProgress(sessionStatus?: string | null): boolean {
  if (!sessionStatus) return false;
  return LOGIN_IN_PROGRESS_SESSIONS.has(sessionStatus) || sessionStatus === 'created';
}

export function labelAccountOperationalStatus(status: string): string {
  switch (status) {
    case 'active':
      return '启用';
    case 'inactive':
      return '暂停';
    case 'suspended':
      return '已停用';
    default:
      return status;
  }
}

export function labelUsageStatus(status: string): string {
  switch (status) {
    case 'ready':
      return '可用';
    case 'need_login':
      return '需登录';
    case 'need_verify':
      return '需验证';
    case 'unavailable':
      return '不可用';
    default:
      return status;
  }
}
