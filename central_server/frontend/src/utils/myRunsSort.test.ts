import { describe, expect, it } from 'vitest';
import type { OpsTaskRunItem } from '../api/operations';
import { sortMyRuns } from './myRunsSort';

function item(partial: Partial<OpsTaskRunItem> & { id: string; created_at: string }): OpsTaskRunItem {
  return {
    task_template_id: 'tpl-1',
    task_template_name: '测试',
    trigger_type: 'manual',
    status: partial.status ?? 'success',
    requested_by_user_id: null,
    requested_by_display_name: null,
    owner_employee_id: null,
    owner_employee_name: null,
    executor_account_id: null,
    executor_account_name: null,
    task_schedule_id: null,
    jobs_total: 1,
    jobs_pending: 0,
    jobs_running: 0,
    jobs_success: 1,
    jobs_failed: 0,
    result_summary: {},
    error_summary: {},
    updated_at: partial.created_at,
    finished_at: null,
    has_active_jobs: partial.has_active_jobs ?? false,
    has_stuck_jobs: false,
    ...partial,
  };
}

describe('sortMyRuns', () => {
  it('puts active runs before finished runs', () => {
    const sorted = sortMyRuns([
      item({ id: 'done', created_at: '2026-01-03T00:00:00Z', status: 'success' }),
      item({ id: 'active', created_at: '2026-01-01T00:00:00Z', status: 'running', has_active_jobs: true }),
    ]);
    expect(sorted.map((run) => run.id)).toEqual(['active', 'done']);
  });
});
