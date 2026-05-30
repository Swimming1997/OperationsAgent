import { describe, expect, it } from 'vitest';
import type { OpsJobItem, OpsTaskRunItem } from '../api/operations';
import { isRunNeedsAttention, sortTaskRunsForBucket } from './operationsRunBuckets';

const baseRun: OpsTaskRunItem = {
  id: 'run-1',
  task_template_id: 'task-1',
  task_template_name: '推荐页巡检',
  trigger_type: 'manual',
  status: 'running',
  requested_by_user_id: null,
  requested_by_display_name: null,
  owner_employee_id: null,
  owner_employee_name: null,
  executor_account_id: null,
  executor_account_name: null,
  task_schedule_id: null,
  jobs_total: 1,
  jobs_pending: 0,
  jobs_running: 1,
  jobs_success: 0,
  jobs_failed: 0,
  result_summary: {},
  error_summary: {},
  created_at: '2026-05-19T01:00:00Z',
  updated_at: '2026-05-19T01:00:00Z',
  finished_at: null,
  has_active_jobs: true,
  has_stuck_jobs: false,
};

const baseJob: OpsJobItem = {
  id: 'job-1',
  task_run_id: 'run-1',
  task_template_name: '推荐页巡检',
  job_type: 'comment_fetch',
  status: 'running',
  priority: 80,
  account_id: null,
  local_agent_id: null,
  claimed_by_agent_id: null,
  claimed_by_agent_name: null,
  retry_count: 0,
  last_error_code: null,
  last_error_message: null,
  created_at: '2026-05-19T02:00:00Z',
  started_at: '2026-05-19T02:00:10Z',
  finished_at: null,
  is_legacy: false,
  is_stale_running: false,
  is_stale_claimed: false,
  payload_json: {},
  result_summary_json: {},
};

describe('operationsRunBuckets', () => {
  it('does not mark healthy running task runs as needs attention', () => {
    expect(isRunNeedsAttention(baseRun, [baseJob])).toBe(false);
  });

  it('marks stuck jobs as needs attention', () => {
    expect(isRunNeedsAttention(baseRun, [{ ...baseJob, is_stale_running: true }])).toBe(true);
    expect(isRunNeedsAttention({ ...baseRun, has_stuck_jobs: true }, [])).toBe(true);
    expect(isRunNeedsAttention(baseRun, [{ ...baseJob, status: 'claimed', is_stale_claimed: true }])).toBe(true);
  });

  it('sorts stuck task runs first in needs_action bucket', () => {
    const stuck = { ...baseRun, id: 'run-stuck', has_stuck_jobs: true };
    const healthy = { ...baseRun, id: 'run-healthy', has_stuck_jobs: false };
    const sorted = sortTaskRunsForBucket([healthy, stuck], 'needs_action');
    expect(sorted.map((item) => item.id)).toEqual(['run-stuck', 'run-healthy']);
  });
});
