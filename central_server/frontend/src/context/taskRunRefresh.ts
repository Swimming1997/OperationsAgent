import type { JobQueueSummary, OpsTaskRunItem } from '../api/operations';
import type { Role } from '../types/api';

const ACTIVE_JOB_STATUSES = ['pending', 'claimed', 'running'] as const;
const ACTIVE_RUN_STATUSES = ['queued', 'running', 'materialized'] as const;

export type TaskRunViewer = {
  role: Role;
  userId: string;
  employeeId: string | null;
};

export function countActiveJobs(summary: JobQueueSummary): number {
  const counts = summary.job_status_counts || summary.status_counts || {};
  return ACTIVE_JOB_STATUSES.reduce((total, status) => total + (counts[status] || 0), 0);
}

export function countActiveTaskRuns(summary: JobQueueSummary): number {
  const counts = summary.task_run_status_counts || {};
  return ACTIVE_RUN_STATUSES.reduce((total, status) => total + (counts[status] || 0), 0);
}

export function hasGlobalActiveWork(summary: JobQueueSummary): number {
  return countActiveJobs(summary) + countActiveTaskRuns(summary);
}

export function isManagerRole(role: Role): boolean {
  return role === 'admin' || role === 'supervisor';
}

export function isTaskRunWatcherRole(role: Role): boolean {
  return role === 'admin' || role === 'supervisor' || role === 'operator';
}

/** 管理账户看全部；运营员工只看执行账号归属自己的运行批次。 */
export function isRelevantTaskRun(run: OpsTaskRunItem, viewer: TaskRunViewer): boolean {
  if (isManagerRole(viewer.role)) return true;
  if (viewer.role !== 'operator') return false;
  return Boolean(viewer.employeeId && run.owner_employee_id === viewer.employeeId);
}

export function filterRelevantTaskRuns(runs: OpsTaskRunItem[], viewer: TaskRunViewer): OpsTaskRunItem[] {
  return runs.filter((run) => isRelevantTaskRun(run, viewer));
}

/** 此前在跟踪、且已从活跃列表消失的 run id（视为刚结束）。 */
export function findNewlyCompletedRunIds(
  previouslyTracked: ReadonlySet<string>,
  currentlyActiveRelevant: OpsTaskRunItem[],
): string[] {
  const activeIds = new Set(currentlyActiveRelevant.map((run) => run.id));
  const completed: string[] = [];
  for (const runId of previouslyTracked) {
    if (!activeIds.has(runId)) completed.push(runId);
  }
  return completed;
}

export function buildTrackedActiveRunIds(
  currentlyActiveRelevant: OpsTaskRunItem[],
  manuallyTracked: ReadonlySet<string>,
): Set<string> {
  const next = new Set<string>(manuallyTracked);
  for (const run of currentlyActiveRelevant) {
    next.add(run.id);
  }
  return next;
}
