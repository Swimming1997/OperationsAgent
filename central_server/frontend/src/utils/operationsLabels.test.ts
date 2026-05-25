import { describe, expect, it } from 'vitest';
import { labelJobType, labelOverviewStatus, labelPriority, labelStatus } from './operationsLabels';

describe('operationsLabels', () => {
  it('maps job types and statuses to Chinese', () => {
    expect(labelJobType('comment_fetch')).toBe('评论补采');
    expect(labelStatus('running')).toBe('执行中');
    expect(labelOverviewStatus('failed')).toBe('执行失败');
    expect(labelPriority(80)).toBe('补采任务');
  });
});
