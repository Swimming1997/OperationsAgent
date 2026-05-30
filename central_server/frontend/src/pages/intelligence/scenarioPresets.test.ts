import { describe, expect, it } from 'vitest';
import {
  buildActiveListFilters,
  materializeScenarioFilterState,
  mergeScenarioStateWithUrlOverlay,
  resolveScenarioFilters,
  splitAdvancedFiltersForSave,
  systemDefaultScenarioFilters,
} from './scenarioPresets';

describe('scenarioPresets', () => {
  it('resolves rolling discovered_after_days for pending default', () => {
    const resolved = resolveScenarioFilters(systemDefaultScenarioFilters('pending'));
    expect(resolved.in_reference_library).toBe('false');
    expect(resolved.discovered_after).toBeTruthy();
  });

  it('prefers absolute discovered_after over rolling when both exist in save split', () => {
    const split = splitAdvancedFiltersForSave({
      filters: { discovered_after: '2026-01-01T00:00:00.000Z' },
      rolling: { discovered_after_days: 7 },
    });
    expect(split.filters.discovered_after).toBe('2026-01-01T00:00:00.000Z');
    expect(split.rolling.discovered_after_days).toBeUndefined();
  });

  it('materializes rolling discovered_after into explicit filter state', () => {
    const materialized = materializeScenarioFilterState(systemDefaultScenarioFilters('pending'));
    expect(materialized.filters.discovered_after).toBeTruthy();
    expect(materialized.rolling.discovered_after_days).toBeUndefined();
    expect(materialized.filters.in_reference_library).toBe('false');
  });

  it('buildActiveListFilters uses current panel state and optional content query', () => {
    const filters = buildActiveListFilters(
      materializeScenarioFilterState(systemDefaultScenarioFilters('pending')),
      { source_surface: 'search', sort_by: 'like_count', sort_order: 'desc' },
      { contentQuery: 'SCI', page: '1', pageSize: '20' },
    );
    expect(filters.content_query).toBe('SCI');
    expect(filters.source_surface).toBe('search');
    expect(filters.in_reference_library).toBe('false');
    expect(filters.discovered_after).toBeTruthy();
  });

  it('merges url overlay and clears rolling when discovered_after provided', () => {
    const merged = mergeScenarioStateWithUrlOverlay(systemDefaultScenarioFilters('pending'), {
      discovered_after: '2026-02-01T00:00:00.000Z',
    });
    expect(merged.filters.discovered_after).toBe('2026-02-01T00:00:00.000Z');
    expect(merged.rolling.discovered_after_days).toBeUndefined();
  });
});
