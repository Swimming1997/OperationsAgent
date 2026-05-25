import { Plus, RefreshCw, Save } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { addBenchmarkMember, bindBenchmarkGroupBusinessType, createBenchmarkGroup, listBenchmarkGroupBusinessTypes, listBenchmarkGroups, listBenchmarkMembers, listBusinessAccountTypes, updateBenchmarkGroup } from '../api/resources';
import { ResourceSelect } from '../components/ResourceSelect';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { BenchmarkGroup, BenchmarkGroupBusinessType, BenchmarkGroupMember, BusinessAccountType, Role } from '../types/api';

type Props = { role: Role; userId: string };

export function BenchmarksPage({ role, userId }: Props) {
  const [groups, setGroups] = useState<BenchmarkGroup[]>([]);
  const [members, setMembers] = useState<BenchmarkGroupMember[]>([]);
  const [types, setTypes] = useState<BusinessAccountType[]>([]);
  const [bindings, setBindings] = useState<BenchmarkGroupBusinessType[]>([]);
  const [selected, setSelected] = useState<BenchmarkGroup | null>(null);
  const [groupForm, setGroupForm] = useState<Partial<BenchmarkGroup>>({ name: '', enabled: true });
  const [memberForm, setMemberForm] = useState<Partial<BenchmarkGroupMember>>({ platform: 'xhs', enabled: true });
  const [businessTypeId, setBusinessTypeId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const readonly = role === 'operator';
  const typeOptions = useMemo(() => types.map((item) => ({ value: item.id, label: item.name, description: item.enabled ? '启用' : '停用' })), [types]);

  useEffect(() => { void reload(); }, [role, userId]);
  useEffect(() => { if (selected) void reloadGroup(selected.id); }, [selected?.id]);

  async function reload() {
    setLoading(true);
    setError('');
    try {
      const [nextGroups, nextTypes] = await Promise.all([listBenchmarkGroups(role, userId), listBusinessAccountTypes(role, userId)]);
      setGroups(nextGroups);
      setTypes(nextTypes);
      const current = selected || nextGroups[0] || null;
      setSelected(current);
      setGroupForm(current || { name: '', enabled: true });
      if (current) await reloadGroup(current.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '对标组加载失败');
    } finally {
      setLoading(false);
    }
  }

  async function reloadGroup(groupId: string) {
    const [nextMembers, nextBindings] = await Promise.all([
      listBenchmarkMembers(role, groupId, userId),
      listBenchmarkGroupBusinessTypes(role, groupId, userId),
    ]);
    setMembers(nextMembers);
    setBindings(nextBindings);
  }

  function chooseGroup(group: BenchmarkGroup) {
    setSelected(group);
    setGroupForm(group);
  }

  async function saveGroup() {
    if (readonly || !groupForm.name) return;
    const payload = { name: groupForm.name, description: groupForm.description || null, owner_employee_id: groupForm.owner_employee_id || null, enabled: groupForm.enabled ?? true };
    const saved = selected ? await updateBenchmarkGroup(role, selected.id, payload, userId) : await createBenchmarkGroup(role, payload, userId);
    setSelected(saved);
    setGroupForm(saved);
    await reload();
  }

  async function addMember() {
    if (readonly || !selected) return;
    await addBenchmarkMember(role, selected.id, {
      platform: memberForm.platform || 'xhs',
      creator_platform_id: memberForm.creator_platform_id || undefined,
      creator_profile_url: memberForm.creator_profile_url || undefined,
      display_name: memberForm.display_name || undefined,
      enabled: memberForm.enabled !== false,
      platform_context: {},
    }, userId);
    setMemberForm({ platform: 'xhs', enabled: true });
    await reloadGroup(selected.id);
  }

  async function bindType() {
    if (readonly || !selected || !businessTypeId) return;
    await bindBenchmarkGroupBusinessType(role, selected.id, businessTypeId, userId);
    await reloadGroup(selected.id);
  }

  return (
    <section className="page-grid resource-grid">
      <aside className="filter-panel">
        <div className="panel-title">对标组</div>
        <button onClick={() => { setSelected(null); setGroupForm({ name: '', enabled: true }); setMembers([]); setBindings([]); }}><Plus size={14} />新建组</button>
        <button className="secondary" onClick={reload}><RefreshCw size={14} />刷新</button>
        <div className="mini-list">
          {groups.map((group) => <button key={group.id} className={`mini-row ${selected?.id === group.id ? 'selected' : ''}`} onClick={() => chooseGroup(group)}>{group.name}<span>{group.enabled ? '启用' : '停用'}</span></button>)}
        </div>
      </aside>
      <section className="list-panel">
        <div className="section-head"><div><h1>对标账号管理</h1><span>{members.length} 个组内成员</span></div></div>
        {error && <ErrorState text={error} />}
        {loading ? <LoadingState text="对标组加载中" /> : !selected ? <EmptyState text="请选择或新建对标组" /> : (
          <div className="data-table">
            <div className="table-row table-head member-row"><span>平台</span><span>creator/profile</span><span>昵称</span><span>creator_monitor</span><span>状态</span></div>
            {members.map((member) => (
              <div key={member.id} className="table-row member-row">
                <span>{member.platform}</span><span className="strong">{member.creator_platform_id || member.creator_profile_url || '-'}</span><span>{member.display_name || '-'}</span><span>{member.creator_monitor_id || '-'}</span><span>{member.enabled ? '启用' : '停用'}</span>
              </div>
            ))}
          </div>
        )}
      </section>
      <aside className="detail-panel">
        <div className="panel-title">组详情与绑定</div>
        <div className="form-stack">
          <label>组名</label><input value={groupForm.name || ''} onChange={(event) => setGroupForm({ ...groupForm, name: event.target.value })} />
          <label>描述</label><input value={groupForm.description || ''} onChange={(event) => setGroupForm({ ...groupForm, description: event.target.value })} />
          <label className="check-line"><input type="checkbox" checked={groupForm.enabled !== false} onChange={(event) => setGroupForm({ ...groupForm, enabled: event.target.checked })} />启用</label>
          <button onClick={saveGroup} disabled={readonly}><Save size={14} />保存组</button>
        </div>
        <div className="detail-section">
          <b>添加成员</b>
          <label>平台</label><input value={memberForm.platform || 'xhs'} onChange={(event) => setMemberForm({ ...memberForm, platform: event.target.value })} />
          <label>creator_platform_id</label><input value={memberForm.creator_platform_id || ''} onChange={(event) => setMemberForm({ ...memberForm, creator_platform_id: event.target.value })} />
          <label>creator profile URL</label><input value={memberForm.creator_profile_url || ''} onChange={(event) => setMemberForm({ ...memberForm, creator_profile_url: event.target.value })} />
          <label>昵称</label><input value={memberForm.display_name || ''} onChange={(event) => setMemberForm({ ...memberForm, display_name: event.target.value })} />
          <button onClick={addMember} disabled={readonly || !selected}><Plus size={14} />添加成员</button>
        </div>
        <div className="detail-section">
          <b>业务账号类型绑定</b>
          {bindings.length === 0 ? <span>暂无绑定</span> : bindings.map((item) => <span key={item.id}>{item.business_account_type_name || item.business_account_type_id}</span>)}
          <ResourceSelect label="绑定业务类型" value={businessTypeId} options={typeOptions} onChange={setBusinessTypeId} />
          <button onClick={bindType} disabled={readonly || !selected}><Plus size={14} />添加绑定</button>
        </div>
      </aside>
    </section>
  );
}
