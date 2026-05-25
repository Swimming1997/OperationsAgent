import type { Role } from '../types/api';

export const ROLE_LABELS: Record<string, string> = {
  admin: '系统管理员',
  supervisor: '主管',
  operator: '运营员工',
  sales: '销售',
};

export function labelRole(role: string): string {
  return ROLE_LABELS[role] || role;
}

export function primaryRole(roles: string[] | undefined): Role {
  const order: Role[] = ['admin', 'supervisor', 'operator', 'sales'];
  for (const item of order) {
    if ((roles || []).includes(item)) return item;
  }
  return 'operator';
}

export function canManageOrganization(roles: string[]): boolean {
  return roles.includes('admin') || roles.includes('supervisor');
}

export function canAccessRoute(route: string, roles: string[]): boolean {
  const set = new Set(roles);
  if (set.has('admin') || set.has('supervisor')) return true;
  if (route === 'organization') return false;
  if (route === 'benchmarks' || route === 'rules' || route === 'agents' || route === 'operations') return false;
  if (route === 'tasks') return set.has('operator');
  if (route === 'accounts') return set.has('operator');
  if (route === 'intelligence') return set.has('operator') || set.has('sales');
  return false;
}
