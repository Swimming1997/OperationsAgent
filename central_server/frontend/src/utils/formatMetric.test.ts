import { describe, expect, it } from 'vitest';
import { formatMetric } from './formatMetric';

describe('formatMetric', () => {
  it('labels missing metrics as pending', () => {
    expect(formatMetric(null)).toBe('待补全');
    expect(formatMetric(undefined)).toBe('待补全');
  });

  it('formats present metrics as values', () => {
    expect(formatMetric(0)).toBe('0');
    expect(formatMetric(120)).toBe('120');
  });
});
