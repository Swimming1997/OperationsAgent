export const REFERENCE_REVOKE_WINDOW_MS = 24 * 60 * 60 * 1000;

export function isIntelligenceReadOnly(role: string): boolean {
  return role === 'sales';
}

export function canEditIntelligence(role: string): boolean {
  return role === 'admin' || role === 'supervisor' || role === 'operator';
}

export function canReevaluateReference(role: string): boolean {
  return role === 'admin' || role === 'supervisor';
}

export function canEditReferenceLibrary(role: string): boolean {
  return canEditIntelligence(role);
}

export type ReferenceRevokeTarget = {
  created_at: string;
  created_by_user_id: string | null;
};

export function referenceRevokeRemainingMs(
  item: ReferenceRevokeTarget,
  now = Date.now(),
): number | null {
  const created = new Date(item.created_at).getTime();
  if (Number.isNaN(created)) return null;
  return Math.max(0, REFERENCE_REVOKE_WINDOW_MS - (now - created));
}

export function canRevokeOwnReferenceLibraryItem(
  role: string,
  item: ReferenceRevokeTarget,
  userId: string,
  now = Date.now(),
): boolean {
  if (role !== 'operator') return false;
  if (!userId || item.created_by_user_id !== userId) return false;
  const remaining = referenceRevokeRemainingMs(item, now);
  return remaining !== null && remaining > 0;
}

export function canArchiveReference(
  role: string,
  item?: ReferenceRevokeTarget,
  userId?: string,
  now = Date.now(),
): boolean {
  if (role === 'admin' || role === 'supervisor') return true;
  if (item && userId) return canRevokeOwnReferenceLibraryItem(role, item, userId, now);
  return false;
}

export function formatReferenceRevokeRemaining(item: ReferenceRevokeTarget, now = Date.now()): string | null {
  const remaining = referenceRevokeRemainingMs(item, now);
  if (remaining === null) return null;
  if (remaining <= 0) return null;
  const hours = Math.floor(remaining / (60 * 60 * 1000));
  const minutes = Math.floor((remaining % (60 * 60 * 1000)) / (60 * 1000));
  if (hours > 0) return `${hours} 小时 ${minutes} 分钟`;
  return `${Math.max(minutes, 1)} 分钟`;
}

export function shouldUseReferenceRevokeEndpoint(
  role: string,
  item: ReferenceRevokeTarget,
  userId: string,
  now = Date.now(),
): boolean {
  return canRevokeOwnReferenceLibraryItem(role, item, userId, now);
}

export function referenceArchiveActionLabel(
  role: string,
  item?: ReferenceRevokeTarget,
  userId?: string,
  now = Date.now(),
): string {
  if (canRevokeOwnReferenceLibraryItem(role, item || { created_at: '', created_by_user_id: null }, userId || '', now)) {
    return '撤回入库';
  }
  return '移出对标库';
}
