import { apiRequest } from './client';
import type { Role, TaskRun, TaskRunListResponse, TaskRunResponse, TaskTemplateDetail, TaskTemplateListItem, TaskTemplateReadiness } from '../types/api';

export type TaskTemplateType = 'recommendation_feed_task' | 'creator_monitor_task' | 'keyword_search_task';

export type TaskFormData = {
  name: string;
  enabled: boolean;
  executor_account_id: string;
  feed_type?: string;
  target_count?: number;
  refresh_rounds?: number;
  per_round_scroll_target?: number;
  benchmark_group_id?: string;
  auto_detail_fetch?: boolean;
  platform?: string;
  keywords?: string[];
  max_items?: number;
  rule_set_id?: string;
  behavior_profile_id?: string;
  network_egress_profile_id?: string;
  risk_policy_id?: string;
};

export function listTaskTemplates(role: Role, userId?: string) {
  return apiRequest<TaskTemplateListItem[]>('/api/task-templates/list', { role, userId });
}

export function getTaskTemplate(role: Role, templateId: string, userId?: string) {
  return apiRequest<TaskTemplateDetail>(`/api/task-templates/${templateId}`, { role, userId });
}

function endpoint(type: TaskTemplateType, templateId?: string) {
  const segment = type === 'recommendation_feed_task' ? 'recommendation-feed' : type === 'creator_monitor_task' ? 'creator-monitor' : 'keyword-search';
  return `/api/task-templates/${segment}${templateId ? `/${templateId}` : ''}`;
}

export function createTaskTemplate(role: Role, type: TaskTemplateType, payload: TaskFormData, userId?: string) {
  return apiRequest<TaskTemplateDetail>(endpoint(type), { method: 'POST', role, userId, body: payload });
}

export function updateTaskTemplate(role: Role, type: TaskTemplateType, templateId: string, payload: Partial<TaskFormData>, userId?: string) {
  return apiRequest<TaskTemplateDetail>(endpoint(type, templateId), { method: 'PATCH', role, userId, body: payload });
}

export function runTaskTemplate(role: Role, templateId: string, userId?: string) {
  return apiRequest<TaskRunResponse>(`/api/task-templates/${templateId}/run`, { method: 'POST', role, userId });
}

export function getTaskTemplateReadiness(role: Role, templateId: string, userId?: string) {
  return apiRequest<TaskTemplateReadiness>(`/api/task-templates/${templateId}/readiness`, { role, userId });
}

export function getTaskRun(role: Role, taskRunId: string, userId?: string) {
  return apiRequest<TaskRun>(`/api/task-runs/${taskRunId}`, { role, userId });
}

export function listTaskTemplateRuns(role: Role, templateId: string, userId?: string) {
  return apiRequest<TaskRunListResponse>(`/api/task-templates/${templateId}/runs`, { role, userId });
}
