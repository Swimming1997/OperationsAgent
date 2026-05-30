import { describe, expect, it } from 'vitest';
import {
  canArchiveReference,
  canRevokeOwnReferenceLibraryItem,
  formatReferenceRevokeRemaining,
  isIntelligenceReadOnly,
  referenceArchiveActionLabel,
} from './intelligencePermissions';

describe('intelligencePermissions', () => {
  const now = Date.parse('2026-05-30T12:00:00Z');
  const item = {
    created_at: '2026-05-30T11:00:00Z',
    created_by_user_id: 'operator-user',
  };

  it('marks sales as read-only', () => {
    expect(isIntelligenceReadOnly('sales')).toBe(true);
    expect(isIntelligenceReadOnly('operator')).toBe(false);
  });

  it('allows operator to revoke own item within 24h', () => {
    expect(canRevokeOwnReferenceLibraryItem('operator', item, 'operator-user', now)).toBe(true);
    expect(canArchiveReference('operator', item, 'operator-user', now)).toBe(true);
    expect(referenceArchiveActionLabel('operator', item, 'operator-user', now)).toBe('撤回入库');
  });

  it('denies operator revoke for others or after window', () => {
    expect(canRevokeOwnReferenceLibraryItem('operator', item, 'other-user', now)).toBe(false);
    const expired = { ...item, created_at: '2026-05-28T11:00:00Z' };
    expect(canRevokeOwnReferenceLibraryItem('operator', expired, 'operator-user', now)).toBe(false);
    expect(formatReferenceRevokeRemaining(expired, now)).toBeNull();
  });

  it('keeps supervisor archive without item context', () => {
    expect(canArchiveReference('supervisor')).toBe(true);
    expect(referenceArchiveActionLabel('supervisor')).toBe('移出对标库');
  });
});
