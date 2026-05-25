import { apiRequest } from './client';
import type { AccountLoginSession, Role } from '../types/api';

export function startAccountLogin(role: Role, accountId: string, userId?: string, options?: { force?: boolean }) {
  return apiRequest<{ session: AccountLoginSession; message: string }>(`/api/product/accounts/${accountId}/login-sessions`, {
    method: 'POST',
    role,
    userId,
    body: { force: Boolean(options?.force) },
  });
}

export function resetAccountLogin(role: Role, accountId: string, userId?: string) {
  return apiRequest<{ account_id: string; auth_status: string; message: string }>(
    `/api/product/accounts/${accountId}/login-sessions/reset`,
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
