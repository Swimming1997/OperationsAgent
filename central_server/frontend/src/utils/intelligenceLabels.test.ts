import { describe, expect, it } from 'vitest';
import { formatDiscoverySourcesSummary, labelSourceSurface, labelWorkflowStatus } from './intelligenceLabels';

describe('intelligenceLabels', () => {
  it('labels the three main source surfaces in Chinese', () => {
    expect(labelSourceSurface('xhs_home_feed')).toBe('推荐流');
    expect(labelSourceSurface('search')).toBe('关键词搜索');
    expect(labelSourceSurface('creator_monitor')).toBe('对标监控');
  });

  it('formats discovery summary without raw enum keys', () => {
    const text = formatDiscoverySourcesSummary({
      source_surfaces: { search: 1 },
      search_keywords: ['论文'],
    });
    expect(text).toContain('关键词搜索');
    expect(text).toContain('论文');
    expect(text).not.toContain('xhs_home_feed');
  });

  it('labels workflow status in Chinese', () => {
    expect(labelWorkflowStatus('pending_review')).toBe('待审核');
    expect(labelWorkflowStatus('assigned')).toBe('已分配');
  });
});
