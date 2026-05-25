import { apiRequest } from './client';
import type { Role } from '../types/api';

export type OrgUser = {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  status: string;
  roles: string[];
  created_at?: string | null;
  employee_id?: string | null;
};

export type OrgEmployee = {
  id: string;
  user_id: string | null;
  display_name: string;
  email: string | null;
  status: string;
  user_username?: string | null;
  user_display_name?: string | null;
  account_count: number;
  agent_count: number;
};

export function listUsers(role: Role, userId: string) {
  return apiRequest<OrgUser[]>('/api/users', { role, userId });
}

export function createUser(
  role: Role,
  userId: string,
  payload: {
    username: string;
    display_name: string;
    email?: string;
    password: string;
    role_names: string[];
  },
) {
  return apiRequest<OrgUser>('/api/users', { method: 'POST', role, userId, body: payload });
}

export function updateUser(
  role: Role,
  userId: string,
  targetUserId: string,
  payload: { display_name?: string; email?: string; status?: string; role_names?: string[] },
) {
  return apiRequest<OrgUser>(`/api/users/${targetUserId}`, { method: 'PATCH', role, userId, body: payload });
}

export function resetUserPassword(role: Role, userId: string, targetUserId: string, password: string) {
  return apiRequest<OrgUser>(`/api/users/${targetUserId}/reset-password`, {
    method: 'POST',
    role,
    userId,
    body: { password },
  });
}

export function listEmployees(role: Role, userId: string) {
  return apiRequest<OrgEmployee[]>('/api/employees', { role, userId });
}

export function createEmployeeWithUser(
  role: Role,
  userId: string,
  payload: {
    username: string;
    display_name: string;
    email?: string;
    password: string;
    role?: string;
  },
) {
  return apiRequest<OrgEmployee>('/api/employees/with-user', { method: 'POST', role, userId, body: payload });
}

export function createEmployee(
  role: Role,
  userId: string,
  payload: { user_id?: string; display_name: string; email?: string; status?: string },
) {
  return apiRequest<OrgEmployee>('/api/employees', { method: 'POST', role, userId, body: payload });
}

export function updateEmployee(
  role: Role,
  userId: string,
  employeeId: string,
  payload: { display_name?: string; email?: string; status?: string; user_id?: string },
) {
  return apiRequest<OrgEmployee>(`/api/employees/${employeeId}`, { method: 'PATCH', role, userId, body: payload });
}
