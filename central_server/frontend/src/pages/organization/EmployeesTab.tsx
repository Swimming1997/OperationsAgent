import { Plus, Save } from 'lucide-react';
import { useMemo, useState } from 'react';
import {
  createEmployeeWithUser,
  updateEmployee,
  type OrgEmployee,
  type OrgUser,
} from '../../api/organization';
import { ResourceSelect } from '../../components/ResourceSelect';
import { StatusPill } from '../../components/StatusPill';
import { EmptyState } from '../../components/Status';
import type { Role } from '../../types/api';
import { filterEmployees, statusLabel } from './utils';

type Selection = { mode: 'none' } | { mode: 'create' } | { mode: 'edit'; id: string };

type Props = {
  employees: OrgEmployee[];
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
  role: 'operator',
};

export function EmployeesTab({ employees, users, role, userId, onChanged }: Props) {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selection, setSelection] = useState<Selection>({ mode: 'none' });
  const [createForm, setCreateForm] = useState(emptyCreate);
  const [saving, setSaving] = useState(false);

  const filtered = useMemo(() => filterEmployees(employees, search, statusFilter), [employees, search, statusFilter]);
  const selected = selection.mode === 'edit' ? employees.find((item) => item.id === selection.id) ?? null : null;

  const [editForm, setEditForm] = useState({
    display_name: '',
    email: '',
    status: 'active',
    user_id: '',
  });

  function openEdit(employee: OrgEmployee) {
    setSelection({ mode: 'edit', id: employee.id });
    setEditForm({
      display_name: employee.display_name,
      email: employee.email || '',
      status: employee.status,
      user_id: employee.user_id || '',
    });
  }

  function openCreate() {
    setSelection({ mode: 'create' });
    setCreateForm(emptyCreate);
  }

  const userOptions = useMemo(
    () => users.map((user) => ({ value: user.id, label: user.username, description: user.display_name })),
    [users],
  );

  async function submitCreate() {
    setSaving(true);
    try {
      await createEmployeeWithUser(role, userId, createForm);
      setSelection({ mode: 'none' });
      setCreateForm(emptyCreate);
      onChanged('员工账号已创建');
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
      await updateEmployee(role, userId, selected.id, {
        display_name: editForm.display_name,
        email: editForm.email || undefined,
        status: editForm.status,
        user_id: editForm.user_id || undefined,
      });
      onChanged('员工已保存');
    } catch (err) {
      onChanged(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="org-split" data-testid="employees-panel">
      <div className="org-list-pane">
        <div className="org-toolbar">
          <input
            type="search"
            placeholder="搜索姓名、账号、邮箱"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="搜索员工"
          />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="状态筛选">
            <option value="all">全部状态</option>
            <option value="active">启用</option>
            <option value="inactive">停用</option>
          </select>
          <button type="button" className="primary-btn" onClick={openCreate}>
            <Plus size={14} />
            创建员工账号
          </button>
        </div>

        {employees.length === 0 ? (
          <div className="org-empty-card" data-testid="employees-empty">
            <p>暂无员工，点击右上角创建第一个员工账号</p>
            <button type="button" onClick={openCreate}>
              <Plus size={14} />
              创建第一个员工账号
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState text="没有符合筛选条件的员工" />
        ) : (
          <div className="data-table">
            <div className="table-row table-head org-employee-row">
              <span>员工姓名</span>
              <span>登录账号</span>
              <span>邮箱</span>
              <span>状态</span>
              <span>负责账号</span>
              <span>Agent</span>
              <span>操作</span>
            </div>
            {filtered.map((employee) => (
              <button
                key={employee.id}
                type="button"
                className={`table-row org-employee-row ${selected?.id === employee.id ? 'selected' : ''}`}
                onClick={() => openEdit(employee)}
              >
                <span className="strong">{employee.display_name}</span>
                <span>{employee.user_username || '—'}</span>
                <span>{employee.email || '—'}</span>
                <span><StatusPill status={employee.status} /></span>
                <span>{employee.account_count}</span>
                <span>{employee.agent_count}</span>
                <span className="muted-link">详情</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <aside className="org-detail-pane">
        {selection.mode === 'create' ? (
          <>
            <div className="panel-title">创建员工账号</div>
            <div className="form-stack">
              <label>用户名</label>
              <input value={createForm.username} onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })} />
              <label>显示名 / 员工姓名</label>
              <input value={createForm.display_name} onChange={(e) => setCreateForm({ ...createForm, display_name: e.target.value })} />
              <label>邮箱</label>
              <input value={createForm.email} onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })} />
              <label>初始密码</label>
              <input type="password" value={createForm.password} onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })} />
              <label>角色</label>
              <select value={createForm.role} onChange={(e) => setCreateForm({ ...createForm, role: e.target.value })}>
                <option value="operator">运营员工</option>
                <option value="supervisor">主管</option>
                <option value="sales">销售</option>
              </select>
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
            <div className="panel-title">员工详情 / 编辑</div>
            <div className="form-stack">
              <label>员工姓名</label>
              <input value={editForm.display_name} onChange={(e) => setEditForm({ ...editForm, display_name: e.target.value })} />
              <label>邮箱</label>
              <input value={editForm.email} onChange={(e) => setEditForm({ ...editForm, email: e.target.value })} />
              <label>状态</label>
              <select value={editForm.status} onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}>
                <option value="active">启用</option>
                <option value="inactive">停用</option>
              </select>
              <ResourceSelect
                label="关联登录用户"
                value={editForm.user_id}
                options={userOptions}
                onChange={(value) => setEditForm({ ...editForm, user_id: value })}
              />
              <div className="detail-section">
                <b>统计</b>
                <span>负责账号数：{selected.account_count}</span>
                <span>绑定 Agent 数：{selected.agent_count}</span>
                <span>登录账号：{selected.user_username || '—'}</span>
                <span>状态：{statusLabel(selected.status)}</span>
              </div>
              <button type="button" disabled={saving} onClick={() => void submitEdit()}>
                <Save size={14} />
                保存
              </button>
            </div>
          </>
        ) : (
          <div className="org-empty-detail" data-testid="employee-detail-empty">
            <p>从左侧列表选择员工查看详情，或点击「创建员工账号」。</p>
          </div>
        )}
      </aside>
    </div>
  );
}
