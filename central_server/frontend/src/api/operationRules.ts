import { apiRequest } from './client';
import type { OperationRule, Role } from '../types/api';

export type OperationRuleFilters = {
  rule_type?: string;
  platform?: string;
  enabled?: boolean;
  keyword?: string;
};

export function listOperationRules(role: Role, filters: OperationRuleFilters = {}, userId?: string) {
  const params = new URLSearchParams();
  if (filters.rule_type) params.set('rule_type', filters.rule_type);
  if (filters.platform) params.set('platform', filters.platform);
  if (filters.enabled !== undefined) params.set('enabled', String(filters.enabled));
  if (filters.keyword) params.set('keyword', filters.keyword);
  const query = params.toString();
  return apiRequest<OperationRule[]>(`/api/operation-rules${query ? `?${query}` : ''}`, { role, userId });
}

export function createOperationRule(
  role: Role,
  body: Pick<OperationRule, 'rule_type' | 'title' | 'content'> & { platform?: string | null; enabled?: boolean },
  userId?: string,
) {
  return apiRequest<OperationRule>('/api/operation-rules', { method: 'POST', body, role, userId });
}

export function updateOperationRule(
  role: Role,
  ruleId: string,
  body: Partial<Pick<OperationRule, 'title' | 'content' | 'platform' | 'enabled'>> & { bump_version?: boolean },
  userId?: string,
) {
  return apiRequest<OperationRule>(`/api/operation-rules/${ruleId}`, { method: 'PATCH', body, role, userId });
}

export function deleteOperationRule(role: Role, ruleId: string, userId?: string) {
  return apiRequest<void>(`/api/operation-rules/${ruleId}`, { method: 'DELETE', role, userId });
}
