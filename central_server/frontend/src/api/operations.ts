import { apiRequest } from './client';
import type { Role } from '../types/api';

export type JobQueueSummary = {
  generated_at: string;
  /** 执行项状态统计（与 status_counts 相同，保留兼容） */
  status_counts: Record<string, number>;
  job_status_counts: Record<string, number>;
  /** 运行批次状态统计 */
  task_run_status_counts: Record<string, number>;
  /** 无运行批次的活跃执行项数量 */
  orphan_active_job_count: number;
  job_type_status_counts: Record<string, Record<string, number>>;
  stale_running_count: number;
  stale_claimed_count: number;
  legacy_pending_count: number;
  by_agent: Array<{ agent_id: string; device_name: string | null; status_counts: Record<string, number> }>;
};

export type OpsTaskRunItem = {
  id: string;
  task_template_id: string;
  task_template_name: string | null;
  trigger_type: string;
  status: string;
  requested_by_user_id: string | null;
  task_schedule_id: string | null;
  jobs_total: number;
  jobs_pending: number;
  jobs_running: number;
  jobs_success: number;
  jobs_failed: number;
  result_summary: Record<string, unknown>;
  error_summary: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  has_active_jobs: boolean;
};

export type OpsJobItem = {
  id: string;
  task_run_id: string | null;
  task_template_name: string | null;
  job_type: string;
  status: string;
  priority: number;
  account_id: string | null;
  local_agent_id: string | null;
  claimed_by_agent_id: string | null;
  claimed_by_agent_name: string | null;
  retry_count: number;
  last_error_code: string | null;
  last_error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  is_legacy: boolean;
  is_stale_running: boolean;
  payload_json: Record<string, unknown>;
  result_summary_json: Record<string, unknown>;
};

export type OpsTaskRunDetail = OpsTaskRunItem & {
  jobs: OpsJobItem[];
  queue_context: Record<string, unknown> | null;
};

export type OpsJobDetail = OpsJobItem & {
  events: Array<{ event_type: string; payload: Record<string, unknown>; created_at: string }>;
};

export type BulkOperationResult = {
  affected_count: number;
  job_ids: string[];
  message: string;
};

function qs(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

export function fetchQueueSummary(role: Role, userId?: string) {
  return apiRequest<JobQueueSummary>('/api/operations/queue-summary', { role, userId });
}

export function listOpsTaskRuns(role: Role, filters: Record<string, string | number | boolean | undefined>, userId?: string) {
  return apiRequest<{ items: OpsTaskRunItem[]; total: number; page: number; page_size: number }>(
    `/api/operations/task-runs${qs(filters)}`,
    { role, userId },
  );
}

export function getOpsTaskRun(role: Role, taskRunId: string, userId?: string) {
  return apiRequest<OpsTaskRunDetail>(`/api/operations/task-runs/${taskRunId}`, { role, userId });
}

export function listOpsJobs(role: Role, filters: Record<string, string | number | boolean | undefined>, userId?: string) {
  return apiRequest<{ items: OpsJobItem[]; total: number; page: number; page_size: number }>(
    `/api/operations/jobs${qs(filters)}`,
    { role, userId },
  );
}

export function getOpsJob(role: Role, jobId: string, userId?: string) {
  return apiRequest<OpsJobDetail>(`/api/operations/jobs/${jobId}`, { role, userId });
}

export function cancelOpsJob(role: Role, jobId: string, reason: string, userId?: string) {
  return apiRequest<BulkOperationResult>(`/api/operations/jobs/${jobId}/cancel`, { method: 'POST', role, userId, body: { reason } });
}

export function retryOpsJob(role: Role, jobId: string, reason: string, userId?: string) {
  return apiRequest<BulkOperationResult>(`/api/operations/jobs/${jobId}/retry`, { method: 'POST', role, userId, body: { reason } });
}

export function cancelTaskRunPending(role: Role, taskRunId: string, reason: string, userId?: string) {
  return apiRequest<BulkOperationResult>(`/api/operations/task-runs/${taskRunId}/cancel-pending`, { method: 'POST', role, userId, body: { reason } });
}

export function retryTaskRun(role: Role, taskRunId: string, reason: string, userId?: string) {
  return apiRequest<BulkOperationResult>(`/api/operations/task-runs/${taskRunId}/retry`, { method: 'POST', role, userId, body: { reason } });
}

export function failStaleRunningJobs(role: Role, reason: string, userId?: string) {
  return apiRequest<BulkOperationResult>('/api/operations/jobs/fail-stale-running', { method: 'POST', role, userId, body: { reason } });
}

export function cleanupLegacyPending(
  role: Role,
  payload: { reason: string; dry_run?: boolean; agent_id?: string; created_before_hours?: number },
  userId?: string,
) {
  return apiRequest<BulkOperationResult>('/api/operations/jobs/cleanup-legacy-pending', { method: 'POST', role, userId, body: payload });
}
