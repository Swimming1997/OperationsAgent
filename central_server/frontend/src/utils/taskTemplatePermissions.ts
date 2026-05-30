import type { PlatformAccount, Role, TaskTemplateListItem } from '../types/api';

type TemplateLike = Pick<TaskTemplateListItem, 'created_by_user_id' | 'permissions'>;

export function canCreateTaskTemplate(role: Role): boolean {
  return role === 'admin' || role === 'supervisor' || role === 'operator';
}

export function canEditTemplate(role: Role, template: TemplateLike | null, userId: string): boolean {
  if (!template) return false;
  if (role === 'admin' || role === 'supervisor') return true;
  if (template.permissions) return template.permissions.can_edit;
  return Boolean(template.created_by_user_id && template.created_by_user_id === userId);
}

export function canScheduleTemplate(role: Role, template: TemplateLike | null, userId: string): boolean {
  if (!template) return false;
  if (role === 'admin' || role === 'supervisor') return true;
  if (template.permissions) return template.permissions.can_schedule;
  return canEditTemplate(role, template, userId);
}

export function canDeleteTemplate(role: Role, template: TemplateLike | null, userId: string): boolean {
  if (!template) return false;
  if (role === 'admin' || role === 'supervisor') return true;
  if (template.permissions) return template.permissions.can_delete;
  return Boolean(template.created_by_user_id && template.created_by_user_id === userId);
}

export function accountOptionsForRun(
  _role: Role,
  accounts: PlatformAccount[],
  businessAccountTypeId: string | null | undefined,
): PlatformAccount[] {
  if (!businessAccountTypeId) return [];
  return accounts.filter((account) => account.business_account_type_id === businessAccountTypeId);
}
