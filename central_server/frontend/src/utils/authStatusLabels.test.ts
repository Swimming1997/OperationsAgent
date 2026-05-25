import { describe, expect, it } from 'vitest';
import {
  authPillClassForAccount,
  isWaitingForAgent,
  labelAccountLoginBadge,
} from './authStatusLabels';

describe('labelAccountLoginBadge', () => {
  it('shows waiting helper when session is waiting_agent', () => {
    expect(labelAccountLoginBadge({
      auth_status: 'login_pending',
      active_login_session_status: 'waiting_agent',
    })).toBe('等待本地助手');
  });

  it('shows logging in for browser-phase sessions', () => {
    expect(labelAccountLoginBadge({
      auth_status: 'login_pending',
      active_login_session_status: 'waiting_user_login',
    })).toBe('登录中');
  });

  it('shows logged in for active auth', () => {
    expect(labelAccountLoginBadge({
      auth_status: 'active',
      active_login_session_status: null,
    })).toBe('已登录');
  });
});

describe('authPillClassForAccount', () => {
  it('uses waiting_agent pill class', () => {
    expect(authPillClassForAccount({
      auth_status: 'login_pending',
      active_login_session_status: 'waiting_agent',
    })).toBe('auth-waiting_agent');
  });
});

describe('isWaitingForAgent', () => {
  it('detects waiting_agent session', () => {
    expect(isWaitingForAgent({ auth_status: 'login_pending', active_login_session_status: 'waiting_agent' })).toBe(true);
    expect(isWaitingForAgent({ auth_status: 'login_pending', active_login_session_status: 'waiting_user_login' })).toBe(false);
  });
});
