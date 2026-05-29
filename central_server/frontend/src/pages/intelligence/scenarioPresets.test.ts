import { describe, expect, it } from 'vitest';
import {
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

  it('merges url overlay and clears rolling when discovered_after provided', () => {
    const merged = mergeScenarioStateWithUrlOverlay(systemDefaultScenarioFilters('pending'), {
      discovered_after: '2026-02-01T00:00:00.000Z',
    });
    expect(merged.filters.discovered_after).toBe('2026-02-01T00:00:00.000Z');
    expect(merged.rolling.discovered_after_days).toBeUndefined();
  });
});
