import { KeyRound, Plus, Save } from 'lucide-react';
import { useMemo, useState } from 'react';
import {
  createUser,
  resetUserPassword,
  updateUser,
  type OrgUser,
} from '../../api/organization';
import { StatusPill } from '../../components/StatusPill';
import { EmptyState } from '../../components/Status';
import type { Role } from '../../types/api';
import { labelRole } from '../../utils/roleLabels';
import { filterUsers, formatOrgDate } from './utils';

type Selection = { mode: 'none' } | { mode: 'create' } | { mode: 'edit'; id: string };

const ROLE_OPTIONS = ['admin', 'supervisor', 'operator', 'sales'] as const;

type Props = {
  users: OrgUser[];
  role: Role;
  userId: string;
  onChanged: (message: string) => void;
};

const emptyCreate = {
  username: '',
  display_name: '',
  email: '',
  password: '',
  role_names: ['supervisor'] as string[],
};

export function UsersTab({ users, role, userId, onChanged }: Props) {
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selection, setSelection] = useState<Selection>({ mode: 'none' });
  const [createForm, setCreateForm] = useState(emptyCreate);
  const [saving, setSaving] = useState(false);

  const filtered = useMemo(
    () => filterUsers(users, search, roleFilter, statusFilter),
    [users, search, roleFilter, statusFilter],
  );
  const selected = selection.mode === 'edit' ? users.find((item) => item.id === selection.id) ?? null : null;

  const [editForm, setEditForm] = useState({
    display_name: '',
    email: '',
    status: 'active',
    role_names: [] as string[],
    newPassword: '',
  });

  function openEdit(user: OrgUser) {
    setSelection({ mode: 'edit', id: user.id });
    setEditForm({
      display_name: user.display_name,
      email: user.email || '',
      status: user.status,
      role_names: [...user.roles],
      newPassword: '',
    });
  }

  function openCreate() {
    setSelection({ mode: 'create' });
    setCreateForm(emptyCreate);
  }

  function toggleRole(list: string[], roleName: string) {
    return list.includes(roleName) ? list.filter((item) => item !== roleName) : [...list, roleName];
  }

  async function submitCreate() {
    setSaving(true);
    try {
      await createUser(role, userId, createForm);
      setSelection({ mode: 'none' });
      setCreateForm(emptyCreate);
      onChanged('用户已创建');
    } catch (err) {
      onChanged(err instanceof Error ? err.message : '创建失败');
    } finally {
      setSaving(false);
    }
  }

  async function submitEdit() {
    if (!selected) return;
    setSaving(true);
    try {
      await updateUser(role, userId, selected.id, {
        display_name: editForm.display_name,
        email: editForm.email || undefined,
        status: editForm.status,
        role_names: editForm.role_names,
      });
      onChanged('用户已保存');
    } catch (err) {
      onChanged(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  async function submitResetPassword() {
    if (!selected || !editForm.newPassword) return;
    setSaving(true);
    try {
      await resetUserPassword(role, userId, selected.id, editForm.newPassword);
      setEditForm((current) => ({ ...current, newPassword: '' }));
      onChanged('密码已重置');
    } catch (err) {
      onChanged(err instanceof Error ? err.message : '重置失败');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="org-split" data-testid="users-panel">
      <div className="org-list-pane">
        <div className="org-toolbar">
          <input
            type="search"
            placeholder="搜索用户名、显示名、邮箱"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="搜索用户"
          />
          <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} aria-label="角色筛选">
            <option value="all">全部角色</option>
            {ROLE_OPTIONS.map((item) => (
              <option key={item} value={item}>{labelRole(item)}</option>
            ))}
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="状态筛选">
            <option value="all">全部状态</option>
            <option value="active">启用</option>
            <option value="inactive">停用</option>
          </select>
          <button type="button" className="primary-btn" onClick={openCreate}>
            <Plus size={14} />
            新建用户
          </button>
        </div>

        {users.length === 0 ? (
          <EmptyState text="暂无用户" />
        ) : filtered.length === 0 ? (
          <EmptyState text="没有符合筛选条件的用户" />
        ) : (
          <div className="data-table">
            <div className="table-row table-head org-user-row">
              <span>用户名</span>
              <span>显示名</span>
              <span>邮箱</span>
              <span>角色</span>
              <span>状态</span>
              <span>员工档案</span>
              <span>操作</span>
            </div>
            {filtered.map((user) => (
              <button
                key={user.id}
                type="button"
                className={`table-row org-user-row ${selected?.id === user.id ? 'selected' : ''}`}
                onClick={() => openEdit(user)}
              >
                <span className="strong">{user.username}</span>
                <span>{user.display_name}</span>
                <span>{user.email || '—'}</span>
                <span>{user.roles.map(labelRole).join('、') || '—'}</span>
                <span><StatusPill status={user.status} /></span>
                <span>{user.employee_id ? '已绑定' : '未绑定'}</span>
                <span className="muted-link">详情</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <aside className="org-detail-pane">
        {selection.mode === 'create' ? (
          <>
            <div className="panel-title">新建用户</div>
            <div className="form-stack">
              <label>用户名</label>
              <input value={createForm.username} onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })} />
              <label>显示名</label>
              <input value={createForm.display_name} onChange={(e) => setCreateForm({ ...createForm, display_name: e.target.value })} />
              <label>邮箱</label>
              <input value={createForm.email} onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })} />
              <label>初始密码</label>
              <input type="password" value={createForm.password} onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })} />
              <span className="field-hint">角色</span>
              <div className="role-checkboxes">
                {ROLE_OPTIONS.map((item) => (
                  <label key={item} className="check-line">
                    <input
                      type="checkbox"
                      checked={createForm.role_names.includes(item)}
                      onChange={() => setCreateForm({ ...createForm, role_names: toggleRole(createForm.role_names, item) })}
                    />
                    {labelRole(item)}
                  </label>
                ))}
              </div>
              <div className="detail-actions">
                <button type="button" className="secondary" onClick={() => setSelection({ mode: 'none' })}>取消</button>
                <button type="button" disabled={saving} onClick={() => void submitCreate()}>
                  <Save size={14} />
                  创建
                </button>
              </div>
            </div>
          </>
        ) : selected ? (
          <>
            <div className="panel-title">用户详情 / 编辑</div>
            <div className="form-stack">
              <label>用户名</label>
              <input value={selected.username} readOnly />
              <label>显示名</label>
              <input value={editForm.display_name} onChange={(e) => setEditForm({ ...editForm, display_name: e.target.value })} />
              <label>邮箱</label>
              <input value={editForm.email} onChange={(e) => setEditForm({ ...editForm, email: e.target.value })} />
              <label>状态</label>
              <select value={editForm.status} onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}>
                <option value="active">启用</option>
                <option value="inactive">停用</option>
              </select>
              <span className="field-hint">角色</span>
              <div className="role-checkboxes">
                {ROLE_OPTIONS.map((item) => (
                  <label key={item} className="check-line">
                    <input
                      type="checkbox"
                      checked={editForm.role_names.includes(item)}
                      onChange={() => setEditForm({ ...editForm, role_names: toggleRole(editForm.role_names, item) })}
                    />
                    {labelRole(item)}
                  </label>
                ))}
              </div>
              <div className="detail-section">
                <b>关联</b>
                <span>员工档案：{selected.employee_id ? '已绑定' : '未绑定'}</span>
                <span>创建时间：{formatOrgDate(selected.created_at)}</span>
              </div>
              <label>重置密码</label>
              <input
                type="password"
                placeholder="输入新密码"
                value={editForm.newPassword}
                onChange={(e) => setEditForm({ ...editForm, newPassword: e.target.value })}
              />
              <div className="detail-actions">
                <button type="button" disabled={saving} onClick={() => void submitEdit()}>
                  <Save size={14} />
                  保存
                </button>
                <button type="button" className="secondary" disabled={saving || !editForm.newPassword} onClick={() => void submitResetPassword()}>
                  <KeyRound size={14} />
                  重置密码
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="org-empty-detail" data-testid="user-detail-empty">
            <p>从左侧列表选择用户查看详情，或点击「新建用户」。</p>
          </div>
        )}
      </aside>
    </div>
  );
}
