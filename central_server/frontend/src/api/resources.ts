import { apiRequest } from './client';
import type {
  BehaviorProfile,
  BenchmarkGroup,
  BenchmarkGroupBusinessType,
  BenchmarkGroupMember,
  BusinessAccountType,
  BusinessAccountTypeRuleSet,
  Employee,
  KeywordRule,
  KeywordRuleSet,
  LocalAgent,
  NetworkEgressProfile,
  PlatformAccount,
  RiskPolicy,
  Role,
} from '../types/api';

export function listEmployees(role: Role, userId?: string) {
  return apiRequest<Employee[]>('/api/employees', { role, userId });
}

export function listAccounts(role: Role, userId?: string) {
  return apiRequest<PlatformAccount[]>('/api/product/accounts', { role, userId });
}

export function createAccount(role: Role, payload: Partial<PlatformAccount> & { platform: string; display_name: string }, userId?: string) {
  return apiRequest<PlatformAccount>('/api/product/accounts', { method: 'POST', role, userId, body: payload });
}

export function getAccount(role: Role, accountId: string, userId?: string) {
  return apiRequest<PlatformAccount>(`/api/product/accounts/${accountId}`, { role, userId });
}

export function updateAccount(role: Role, accountId: string, payload: Partial<PlatformAccount>, userId?: string) {
  return apiRequest<PlatformAccount>(`/api/product/accounts/${accountId}`, { method: 'PATCH', role, userId, body: payload });
}

export function listBusinessAccountTypes(role: Role, userId?: string) {
  return apiRequest<BusinessAccountType[]>('/api/business-account-types', { role, userId });
}

export function createBusinessAccountType(role: Role, payload: Pick<BusinessAccountType, 'name' | 'description' | 'enabled'>, userId?: string) {
  return apiRequest<BusinessAccountType>('/api/business-account-types', { method: 'POST', role, userId, body: payload });
}

export function updateBusinessAccountType(role: Role, id: string, payload: Partial<BusinessAccountType>, userId?: string) {
  return apiRequest<BusinessAccountType>(`/api/business-account-types/${id}`, { method: 'PATCH', role, userId, body: payload });
}

export function listAgents(role: Role, userId?: string) {
  return apiRequest<LocalAgent[]>('/api/local-agents', { role, userId });
}

export function getAgent(role: Role, agentId: string, userId?: string) {
  return apiRequest<LocalAgent>(`/api/local-agents/${agentId}`, { role, userId });
}

export function updateAgent(role: Role, agentId: string, payload: Partial<Pick<LocalAgent, 'employee_id' | 'status'>>, userId?: string) {
  return apiRequest<LocalAgent>(`/api/local-agents/${agentId}`, { method: 'PATCH', role, userId, body: payload });
}

export function listBenchmarkGroups(role: Role, userId?: string) {
  return apiRequest<BenchmarkGroup[]>('/api/benchmark-groups', { role, userId });
}

export function createBenchmarkGroup(role: Role, payload: Pick<BenchmarkGroup, 'name' | 'description' | 'owner_employee_id' | 'enabled'>, userId?: string) {
  return apiRequest<BenchmarkGroup>('/api/benchmark-groups', { method: 'POST', role, userId, body: { ...payload, metadata: {} } });
}

export function updateBenchmarkGroup(role: Role, groupId: string, payload: Partial<BenchmarkGroup>, userId?: string) {
  return apiRequest<BenchmarkGroup>(`/api/benchmark-groups/${groupId}`, { method: 'PATCH', role, userId, body: payload });
}

export function listBenchmarkMembers(role: Role, groupId: string, userId?: string) {
  return apiRequest<BenchmarkGroupMember[]>(`/api/benchmark-groups/${groupId}/members`, { role, userId });
}

export function addBenchmarkMember(role: Role, groupId: string, payload: Partial<BenchmarkGroupMember>, userId?: string) {
  return apiRequest<BenchmarkGroupMember>(`/api/benchmark-groups/${groupId}/members`, { method: 'POST', role, userId, body: payload });
}

export function listBenchmarkGroupBusinessTypes(role: Role, groupId: string, userId?: string) {
  return apiRequest<BenchmarkGroupBusinessType[]>(`/api/benchmark-groups/${groupId}/business-account-types`, { role, userId });
}

export function bindBenchmarkGroupBusinessType(role: Role, groupId: string, businessAccountTypeId: string, userId?: string) {
  return apiRequest<{ binding_id: string }>(`/api/benchmark-groups/${groupId}/business-account-types`, {
    method: 'POST',
    role,
    userId,
    body: { business_account_type_id: businessAccountTypeId },
  });
}

export function listKeywordRuleSets(role: Role, userId?: string) {
  return apiRequest<KeywordRuleSet[]>('/api/keyword-rule-sets', { role, userId });
}

export function createKeywordRuleSet(role: Role, payload: Pick<KeywordRuleSet, 'name' | 'rule_scope' | 'enabled'> & { config?: Record<string, unknown> }, userId?: string) {
  return apiRequest<KeywordRuleSet>('/api/keyword-rule-sets', { method: 'POST', role, userId, body: { config: {}, ...payload } });
}

export function updateKeywordRuleSet(role: Role, id: string, payload: Partial<KeywordRuleSet>, userId?: string) {
  return apiRequest<KeywordRuleSet>(`/api/keyword-rule-sets/${id}`, { method: 'PATCH', role, userId, body: payload });
}

export function listKeywordRules(role: Role, ruleSetId: string, userId?: string) {
  return apiRequest<KeywordRule[]>(`/api/keyword-rule-sets/${ruleSetId}/rules`, { role, userId });
}

export function createKeywordRule(role: Role, ruleSetId: string, payload: Partial<KeywordRule>, userId?: string) {
  return apiRequest<KeywordRule>(`/api/keyword-rule-sets/${ruleSetId}/rules`, { method: 'POST', role, userId, body: payload });
}

export function updateKeywordRule(role: Role, ruleId: string, payload: Partial<KeywordRule>, userId?: string) {
  return apiRequest<KeywordRule>(`/api/keyword-rules/${ruleId}`, { method: 'PATCH', role, userId, body: payload });
}

export function listBusinessTypeRuleSets(role: Role, businessTypeId: string, userId?: string) {
  return apiRequest<BusinessAccountTypeRuleSet[]>(`/api/business-account-types/${businessTypeId}/rule-sets`, { role, userId });
}

export function bindBusinessTypeRuleSet(role: Role, businessTypeId: string, ruleSetId: string, isDefault = false, userId?: string) {
  return apiRequest<BusinessAccountTypeRuleSet>(`/api/business-account-types/${businessTypeId}/rule-sets`, {
    method: 'POST',
    role,
    userId,
    body: { rule_set_id: ruleSetId, is_default: isDefault },
  });
}

export function listBehaviorProfiles(role: Role, userId?: string) {
  return apiRequest<BehaviorProfile[]>('/api/behavior-profiles', { role, userId });
}

export function listNetworkEgressProfiles(role: Role, userId?: string) {
  return apiRequest<NetworkEgressProfile[]>('/api/network-egress-profiles', { role, userId });
}

export function listRiskPolicies(role: Role, userId?: string) {
  return apiRequest<RiskPolicy[]>('/api/risk-policies', { role, userId });
}
