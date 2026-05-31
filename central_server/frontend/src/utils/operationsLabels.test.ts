import { describe, expect, it } from 'vitest';
import { getTaskRunDisplayName, labelJobType, labelOverviewStatus, labelPriority, labelStatus } from './operationsLabels';

describe('operationsLabels', () => {
  it('maps job types and statuses to Chinese', () => {
    expect(labelJobType('comment_fetch')).toBe('评论补采');
    expect(labelStatus('running')).toBe('执行中');
    expect(labelOverviewStatus('failed')).toBe('执行失败');
    expect(labelPriority(80)).toBe('补采任务');
  });

  it('derives manual fetch run names from jobs when template name is missing', () => {
    expect(getTaskRunDisplayName(
      { task_template_id: null, task_template_name: null },
      [{ job_type: 'detail_fetch', payload_json: { manual_enqueue: true } }],
    )).toBe('内容详情补采');
    expect(getTaskRunDisplayName(
      { task_template_id: 'task-1', task_template_name: '推荐页巡检' },
    )).toBe('推荐页巡检');
  });
});
