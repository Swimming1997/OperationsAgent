import type { ApiError } from '../types/api';
import { getStoredToken, setStoredToken } from '../auth/storage';

export type AuthUser = {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  status: string;
  roles: string[];
  employee_id: string | null;
};

export type BootstrapStatus = {
  users_count: number;
  admin_exists: boolean;
  needs_bootstrap: boolean;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

async function authFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(init?.headers as Record<string, string> | undefined),
  };
  const token = getStoredToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (init?.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text();
    }
    const message = response.status === 401 ? '用户名或密码错误' : `请求失败 (${response.status})`;
    const error = new Error(message) as ApiError;
    error.status = response.status;
    error.detail = detail;
    throw error;
  }
  return response.json() as Promise<T>;
}

export function fetchBootstrapStatus() {
  return authFetch<BootstrapStatus>('/api/auth/bootstrap-status');
}

export function bootstrapAdmin(payload: {
  username: string;
  display_name: string;
  email?: string;
  password: string;
}) {
  return authFetch<LoginResponse>('/api/auth/bootstrap-admin', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function login(payload: { username: string; password: string }) {
  return authFetch<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function logoutApi() {
  return authFetch<{ message: string }>('/api/auth/logout', { method: 'POST' });
}

export function fetchMe() {
  return authFetch<AuthUser>('/api/auth/me');
}

export function persistLogin(response: LoginResponse) {
  setStoredToken(response.access_token);
  return response.user;
}

export function clearAuth() {
  setStoredToken(null);
}
