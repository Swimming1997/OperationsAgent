import { describe, expect, it } from 'vitest';
import {
  deriveContentStatusBadge,
  formatDiscoveryPosition,
  formatDiscoverySourcesSummary,
  labelSelectionSource,
  labelSourceSurface,
  labelWorkflowStatus,
} from './intelligenceLabels';

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

  it('labels ai selection source as 规则自动', () => {
    expect(labelSelectionSource('ai')).toBe('规则自动');
  });

  it('formats discovery position for home feed', () => {
    const text = formatDiscoveryPosition({
      best_feed_position: 2,
      discovery_sources_summary: { source_surfaces: { xhs_home_feed: 1 } },
    });
    expect(text).toBe('推荐流第2条');
  });

  it('formats discovery position for search', () => {
    const text = formatDiscoveryPosition({
      search_keyword: '医学sci',
      best_search_rank: 2,
      discovery_sources_summary: { source_surfaces: { search: 1 } },
    });
    expect(text).toContain('搜索第2名');
    expect(text).toContain('医学sci');
  });

  it('formats discovery position for creator monitor', () => {
    const text = formatDiscoveryPosition({
      best_feed_position: 3,
      discovery_sources_summary: { source_surfaces: { creator_monitor: 1 } },
    });
    expect(text).toBe('对标监控第3条');
  });

  it('derives unified status badge', () => {
    expect(deriveContentStatusBadge({ candidate_bucket: 'lead_candidate', in_reference_library: false }).label).toBe('线索');
    expect(
      deriveContentStatusBadge({
        workflow_status: 'selected',
        in_reference_library: false,
        manual_tags: [],
      }).label,
    ).toBe('稍后看');
    expect(
      deriveContentStatusBadge({
        in_reference_library: true,
        reference_library_type: 'lead',
      }).label,
    ).toBe('已入库·获客库');
  });
});
