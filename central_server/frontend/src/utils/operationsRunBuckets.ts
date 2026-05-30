import type { OpsJobItem, OpsTaskRunItem } from '../api/operations';

export const RUN_BUCKET_FILTER_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'needs_action', label: '待处理' },
  { value: 'active', label: '进行中' },
  { value: 'done', label: '已完成' },
] as const;

export const JOB_BUCKET_FILTER_OPTIONS = [
  { value: '', label: '全部执行项' },
  { value: 'waiting', label: '等待执行' },
  { value: 'running', label: '执行中' },
  { value: 'finished', label: '已结束' },
] as const;

export function isRunNeedsAttention(run: OpsTaskRunItem, jobs: OpsJobItem[]): boolean {
  return run.has_stuck_jobs || jobs.some((job) => job.is_stale_running || job.is_stale_claimed);
}

export function sortTaskRunsForBucket(runs: OpsTaskRunItem[], bucket: string): OpsTaskRunItem[] {
  if (bucket !== 'needs_action') return runs;
  return [...runs].sort((left, right) => Number(right.has_stuck_jobs) - Number(left.has_stuck_jobs));
}
