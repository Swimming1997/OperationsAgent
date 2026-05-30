import type { OpsTaskRunItem } from '../api/operations';

const ACTIVE_RUN_STATUSES = new Set(['queued', 'running', 'materialized']);

export function sortMyRuns(runs: OpsTaskRunItem[]): OpsTaskRunItem[] {
  return [...runs].sort((left, right) => {
    const leftActive = left.has_active_jobs || ACTIVE_RUN_STATUSES.has(left.status);
    const rightActive = right.has_active_jobs || ACTIVE_RUN_STATUSES.has(right.status);
    if (leftActive !== rightActive) return leftActive ? -1 : 1;
    return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
  });
}

export function myRunsCreatedAfterIso(days = 7): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString();
}
