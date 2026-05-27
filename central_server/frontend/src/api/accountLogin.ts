import { apiRequest } from './client';
import type { AccountLoginSession, Role } from '../types/api';

export function startAccountLogin(
  role: Role,
  accountId: string,
  userId?: string,
  options?: { force?: boolean; preferred_agent_id?: string | null },
) {
  return apiRequest<{ session: AccountLoginSession; message: string }>(`/api/product/accounts/${accountId}/login-sessions`, {
    method: 'POST',
    role,
    userId,
    body: {
      force: Boolean(options?.force),
      ...(options?.preferred_agent_id ? { preferred_agent_id: options.preferred_agent_id } : {}),
    },
  });
}

export function resetAccountLogin(role: Role, accountId: string, userId?: string) {
  return apiRequest<{ account_id: string; auth_status: string; message: string }>(
    `/api/product/accounts/${accountId}/login-sessions/reset`,
    { method: 'POST', role, userId },
  );
}

export function syncLocalBridgeLogin(
  role: Role,
  accountId: string,
  payload: {
    preferred_agent_id?: string | null;
    login_cdp_port?: number | null;
    platform_nickname?: string | null;
    platform_home_url?: string | null;
    bridge_status?: string;
  },
  userId?: string,
) {
  return apiRequest<{ account_id: string; auth_status: string; message: string }>(
    `/api/product/accounts/${accountId}/sync-local-login`,
    { method: 'POST', role, userId, body: payload },
  );
}

export function prepareBridgeChromeContext(role: Role, accountId: string, userId?: string) {
  return apiRequest<{ account_id: string; profile_key: string; login_cdp_port: number }>(
    `/api/product/accounts/${accountId}/bridge-chrome-context`,
    { method: 'POST', role, userId },
  );
}

export function getActiveAccountLogin(role: Role, accountId: string, userId?: string) {
  return apiRequest<AccountLoginSession | null>(`/api/product/accounts/${accountId}/login-sessions/active`, {
    role,
    userId,
  });
}

export function getLoginSession(role: Role, sessionId: string, userId?: string) {
  return apiRequest<AccountLoginSession>(`/api/product/login-sessions/${sessionId}`, { role, userId });
}
