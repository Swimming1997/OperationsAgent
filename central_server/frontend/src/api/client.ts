import { getStoredToken, isDevAuthEnabled } from '../auth/storage';
import type { ApiError, Role } from '../types/api';

export type RequestConfig = {
  method?: string;
  body?: unknown;
  role?: Role;
  userId?: string;
};

export async function apiRequest<T>(path: string, config: RequestConfig): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };
  const token = getStoredToken();
  if (token && !isDevAuthEnabled()) {
    headers.Authorization = `Bearer ${token}`;
  } else if (config.role) {
    headers['X-Role'] = config.role;
    headers['X-User-Id'] = config.userId || `${config.role}-user`;
  }
  if (config.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(path, {
    method: config.method || 'GET',
    headers,
    body: config.body === undefined ? undefined : JSON.stringify(config.body),
  });

  if (!response.ok) {
    let detail: unknown = null;
    const raw = await response.text();
    if (raw) {
      try {
        detail = JSON.parse(raw);
      } catch {
        detail = raw;
      }
    }
    const message = response.status === 403 ? '无权限访问当前资源' : response.status === 422 ? '请求字段校验失败' : `接口请求失败 (${response.status})`;
    const error = new Error(message) as ApiError;
    error.status = response.status;
    error.detail = detail;
    throw error;
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}
