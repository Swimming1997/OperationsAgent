export function formatMetric(value: number | null | undefined, pendingLabel = '待补全'): string {
  if (value === null || value === undefined) {
    return pendingLabel;
  }
  return String(value);
}
