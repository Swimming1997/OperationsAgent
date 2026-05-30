import { describe, expect, it } from 'vitest';
import type { OpsTaskRunItem } from '../api/operations';
import {
  buildTrackedActiveRunIds,
  filterRelevantTaskRuns,
  findNewlyCompletedRunIds,
  isRelevantTaskRun,
} from './taskRunRefresh';

function run(partial: Partial<OpsTaskRunItem>): OpsTaskRunItem {
  return {
    id: partial.id || 'run-1',
    task_template_id: 'tpl-1',
    task_template_name: '测试',
    trigger_type: 'manual',
    status: 'running',
    requested_by_user_id: partial.requested_by_user_id ?? null,
    requested_by_display_name: null,
    owner_employee_id: partial.owner_employee_id ?? null,
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
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    finished_at: null,
    has_active_jobs: true,
    ...partial,
  };
}

describe('taskRunRefresh', () => {
  it('scopes operator visibility to executor account owner employee only', () => {
    const viewer = { role: 'operator' as const, userId: 'user-op', employeeId: 'emp-op' };
    expect(isRelevantTaskRun(run({ owner_employee_id: 'emp-op' }), viewer)).toBe(true);
    expect(isRelevantTaskRun(run({ requested_by_user_id: 'user-op' }), viewer)).toBe(false);
    expect(isRelevantTaskRun(run({ owner_employee_id: 'emp-other' }), viewer)).toBe(false);
    expect(filterRelevantTaskRuns([run({ id: 'a', owner_employee_id: 'emp-op' }), run({ id: 'b', owner_employee_id: 'emp-x' })], viewer).map((item) => item.id)).toEqual(['a']);
  });

  it('lets managers see all active runs', () => {
    const viewer = { role: 'supervisor' as const, userId: 'sup', employeeId: null };
    expect(filterRelevantTaskRuns([run({ id: 'a' }), run({ id: 'b' })], viewer)).toHaveLength(2);
  });

  it('detects runs that left the active set', () => {
    const previously = new Set(['run-1', 'run-2']);
    const active = [run({ id: 'run-2' })];
    expect(findNewlyCompletedRunIds(previously, active)).toEqual(['run-1']);
  });

  it('merges manual tracking with active relevant runs', () => {
    const tracked = buildTrackedActiveRunIds([run({ id: 'run-a' })], new Set(['run-manual']));
    expect([...tracked].sort()).toEqual(['run-a', 'run-manual']);
  });
});
