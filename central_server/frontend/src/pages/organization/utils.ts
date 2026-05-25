import type { OrgEmployee, OrgUser } from '../../api/organization';

export function formatOrgDate(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('zh-CN', { hour12: false });
}

export function statusLabel(status: string) {
  return status === 'active' ? '启用' : status === 'inactive' ? '停用' : status;
}

export function filterEmployees(items: OrgEmployee[], query: string, status: string) {
  const q = query.trim().toLowerCase();
  return items.filter((item) => {
    if (status !== 'all' && item.status !== status) return false;
    if (!q) return true;
    const haystack = [item.display_name, item.user_username, item.email].filter(Boolean).join(' ').toLowerCase();
    return haystack.includes(q);
  });
}

export function filterUsers(items: OrgUser[], query: string, role: string, status: string) {
  const q = query.trim().toLowerCase();
  return items.filter((item) => {
    if (status !== 'all' && item.status !== status) return false;
    if (role !== 'all' && !item.roles.includes(role)) return false;
    if (!q) return true;
    const haystack = [item.username, item.display_name, item.email].filter(Boolean).join(' ').toLowerCase();
    return haystack.includes(q);
  });
}
