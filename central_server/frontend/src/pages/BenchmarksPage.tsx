import { Plus, RefreshCw, Save, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { addBenchmarkMember, bindBenchmarkGroupBusinessType, createBenchmarkGroup, deleteBenchmarkGroup, deleteBenchmarkMember, listBenchmarkGroupBusinessTypes, listBenchmarkGroups, listBenchmarkMembers, listBusinessAccountTypes, updateBenchmarkGroup, updateBenchmarkMember } from '../api/resources';
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
  const [selectedMember, setSelectedMember] = useState<BenchmarkGroupMember | null>(null);
  const [groupForm, setGroupForm] = useState<Partial<BenchmarkGroup>>({ name: '', enabled: true });
  const [memberForm, setMemberForm] = useState<Partial<BenchmarkGroupMember>>({ platform: 'xhs', enabled: true });
  const [memberDetailForm, setMemberDetailForm] = useState<Partial<BenchmarkGroupMember>>({ platform: 'xhs', enabled: true });
  const [businessTypeId, setBusinessTypeId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const groupReloadTokenRef = useRef(0);
  const isOperator = role === 'operator';
  const canManageAll = role === 'admin' || role === 'supervisor';
  const canCreate = canManageAll || isOperator;
  const canEditGroup = (group: BenchmarkGroup | null) => {
    if (!group) return false;
    if (canManageAll) return true;
    return Boolean(group.submitter_user_id && group.submitter_user_id === userId);
  };
  const detailReadonly = selected ? !canEditGroup(selected) : false;
  const typeOptions = useMemo(() => types.map((item) => ({ value: item.id, label: item.name, description: item.enabled ? '启用' : '停用' })), [types]);

  useEffect(() => { void reload(); }, [role, userId]);

  async function reload() {
    setLoading(true);
    setError('');
    try {
      const [nextGroups, nextTypes] = await Promise.all([listBenchmarkGroups(role, userId), listBusinessAccountTypes(role, userId)]);
      setGroups(nextGroups);
      setTypes(nextTypes);
      const current = (selected ? nextGroups.find((item) => item.id === selected.id) : null) || nextGroups[0] || null;
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
    const token = ++groupReloadTokenRef.current;
    try {
      const [nextMembers, nextBindings] = await Promise.all([
        listBenchmarkMembers(role, groupId, userId),
        listBenchmarkGroupBusinessTypes(role, groupId, userId),
      ]);
      if (token !== groupReloadTokenRef.current) return;
      setMembers(nextMembers);
      setBindings(nextBindings);
      setSelectedMember((current) => {
        if (!current) return null;
        const matched = nextMembers.find((item) => item.id === current.id) || null;
        setMemberDetailForm(matched || { platform: 'xhs', enabled: true });
        return matched;
      });
      setBusinessTypeId((currentId) => {
        if (currentId && nextBindings.some((item) => item.business_account_type_id === currentId)) return currentId;
        return nextBindings[0]?.business_account_type_id || '';
      });
    } catch (err) {
      if (token !== groupReloadTokenRef.current) return;
      setMembers([]);
      setBindings([]);
      setBusinessTypeId('');
      setError(err instanceof Error ? err.message : '对标组详情加载失败');
    }
  }

  function chooseGroup(group: BenchmarkGroup) {
    const isSameGroup = selected?.id === group.id;
    setSelected(group);
    setSelectedMember(null);
    setGroupForm(group);
    if (!isSameGroup) {
      setMembers([]);
      setBindings([]);
      setBusinessTypeId('');
    }
    void reloadGroup(group.id);
  }

  async function saveGroup() {
    if (!canCreate || !groupForm.name) return;
    if (selected && !canEditGroup(selected)) return;
    const payload = { name: groupForm.name, description: groupForm.description || null, owner_employee_id: groupForm.owner_employee_id || null, enabled: groupForm.enabled ?? true };
    const saved = selected ? await updateBenchmarkGroup(role, selected.id, payload, userId) : await createBenchmarkGroup(role, payload, userId);
    setSelected(saved);
    setGroupForm(saved);
    await reload();
  }

  async function removeGroup(group: BenchmarkGroup) {
    if (!canEditGroup(group)) return;
    if (!window.confirm(`确认删除对标账号组「${group.name}」？删除后会同时移除组内成员和业务类型绑定。`)) return;
    await deleteBenchmarkGroup(role, group.id, userId);
    if (selected?.id === group.id) {
      setSelected(null);
      setSelectedMember(null);
      setGroupForm({ name: '', enabled: true });
      setMembers([]);
      setBindings([]);
    }
    await reload();
  }

  async function addMember() {
    if (!selected || !canEditGroup(selected)) return;
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

  async function removeMember(member: BenchmarkGroupMember) {
    if (!selected || !canEditGroup(selected)) return;
    await deleteBenchmarkMember(role, selected.id, member.id, userId);
    if (selectedMember?.id === member.id) {
      setSelectedMember(null);
      setMemberDetailForm({ platform: 'xhs', enabled: true });
    }
    await reloadGroup(selected.id);
  }

  function chooseMember(member: BenchmarkGroupMember) {
    setSelectedMember(member);
    setMemberDetailForm({
      platform: member.platform,
      creator_platform_id: member.creator_platform_id || '',
      creator_profile_url: member.creator_profile_url || '',
      display_name: member.display_name || '',
      enabled: member.enabled,
    });
  }

  async function saveMemberInfo() {
    if (!selected || !selectedMember || !canEditGroup(selected)) return;
    const updated = await updateBenchmarkMember(role, selected.id, selectedMember.id, {
      platform: memberDetailForm.platform || selectedMember.platform,
      creator_platform_id: memberDetailForm.creator_platform_id || null,
      creator_profile_url: memberDetailForm.creator_profile_url || null,
      display_name: memberDetailForm.display_name || null,
      enabled: memberDetailForm.enabled ?? selectedMember.enabled,
    }, userId);
    setSelectedMember(updated);
    setMemberDetailForm({
      platform: updated.platform,
      creator_platform_id: updated.creator_platform_id || '',
      creator_profile_url: updated.creator_profile_url || '',
      display_name: updated.display_name || '',
      enabled: updated.enabled,
    });
    await reloadGroup(selected.id);
  }

  async function bindType() {
    if (!selected || !businessTypeId || !canEditGroup(selected)) return;
    await bindBenchmarkGroupBusinessType(role, selected.id, businessTypeId, userId);
    await reloadGroup(selected.id);
  }

  return (
    <section className="page-grid resource-grid">
      <aside className="filter-panel">
        <div className="panel-title">对标组</div>
        <button onClick={() => { setSelected(null); setSelectedMember(null); setGroupForm({ name: '', enabled: true }); setMembers([]); setBindings([]); }}><Plus size={14} />新建组</button>
        <button className="secondary" onClick={reload}><RefreshCw size={14} />刷新</button>
        <div className="mini-list">
          {groups.map((group) => (
            <div key={group.id} className={`mini-row ${selected?.id === group.id ? 'selected' : ''}`}>
              <button type="button" className="mini-row-main" onClick={() => chooseGroup(group)}>
                <span>{group.name}</span>
                <small>{group.enabled ? '启用' : '停用'} · 提交人：{group.submitter_name || '历史数据'}</small>
              </button>
              <button type="button" className="icon-button danger" title="删除对标账号组" disabled={!canEditGroup(group)} onClick={() => void removeGroup(group)}>
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      </aside>
      <section className="list-panel">
        <div className="section-head"><div><h1>对标账号管理</h1><span>{members.length} 个组内成员</span></div></div>
        {error && <ErrorState text={error} />}
        {loading ? <LoadingState text="对标组加载中" /> : !selected ? <EmptyState text="请选择或新建对标组" /> : (
          <div className="data-table">
            <div className="table-row table-head member-row"><span>平台</span><span>用户ID/主页链接</span><span>昵称</span><span>状态</span><span>操作</span></div>
            {members.map((member) => (
              <div
                key={member.id}
                className={`table-row member-row ${selectedMember?.id === member.id ? 'selected' : ''}`}
                role="button"
                tabIndex={0}
                onClick={() => chooseMember(member)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    chooseMember(member);
                  }
                }}
              >
                <span>{member.platform}</span>
                <span className="strong">{member.creator_platform_id || member.creator_profile_url || '-'}</span>
                <span>{member.display_name || '-'}</span>
                <span>{member.enabled ? '启用' : '停用'}</span>
                <span>
                  <button
                    type="button"
                    className="icon-button danger"
                    title="删除成员账号"
                    disabled={!selected || !canEditGroup(selected)}
                    onClick={(event) => {
                      event.stopPropagation();
                      void removeMember(member);
                    }}
                  >
                    <Trash2 size={14} />
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
      <aside className="detail-panel">
        {selectedMember ? (
          <>
            <div className="panel-title">成员账号信息</div>
            <div className="form-stack">
              <label>平台</label>
              <input
                value={memberDetailForm.platform || ''}
                disabled={!selected || !canEditGroup(selected)}
                onChange={(event) => setMemberDetailForm({ ...memberDetailForm, platform: event.target.value })}
              />
              <label>用户ID</label>
              <input
                value={memberDetailForm.creator_platform_id || ''}
                disabled={!selected || !canEditGroup(selected)}
                onChange={(event) => setMemberDetailForm({ ...memberDetailForm, creator_platform_id: event.target.value })}
              />
              <label>创作者主页链接（选填）</label>
              <input
                value={memberDetailForm.creator_profile_url || ''}
                disabled={!selected || !canEditGroup(selected)}
                onChange={(event) => setMemberDetailForm({ ...memberDetailForm, creator_profile_url: event.target.value })}
              />
              <label>昵称</label>
              <input
                value={memberDetailForm.display_name || ''}
                disabled={!selected || !canEditGroup(selected)}
                onChange={(event) => setMemberDetailForm({ ...memberDetailForm, display_name: event.target.value })}
              />
              <button onClick={saveMemberInfo} disabled={!selected || !canEditGroup(selected)}>
                <Save size={14} />
                保存信息
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="panel-title">组详情与绑定</div>
            <div className="form-stack">
              <label>组名</label><input value={groupForm.name || ''} disabled={detailReadonly} onChange={(event) => setGroupForm({ ...groupForm, name: event.target.value })} />
              <label>描述</label><input value={groupForm.description || ''} disabled={detailReadonly} onChange={(event) => setGroupForm({ ...groupForm, description: event.target.value })} />
              <label className="check-line"><input type="checkbox" checked={groupForm.enabled !== false} disabled={detailReadonly} onChange={(event) => setGroupForm({ ...groupForm, enabled: event.target.checked })} />启用</label>
              {!selected ? <span className="muted-hint">创建后会自动按当前运营账号所属业务类型绑定。</span> : null}
              {selected && !canEditGroup(selected) ? <span className="muted-hint">仅提交人或管理账户可编辑该对标组。</span> : null}
              <button onClick={saveGroup} disabled={!canCreate || (selected ? !canEditGroup(selected) : false)}><Save size={14} />保存组</button>
            </div>
            <div className="detail-section">
              <b>添加成员</b>
              <label>平台</label><input value={memberForm.platform || 'xhs'} disabled={detailReadonly} onChange={(event) => setMemberForm({ ...memberForm, platform: event.target.value })} />
              <label>用户ID</label><input value={memberForm.creator_platform_id || ''} disabled={detailReadonly} onChange={(event) => setMemberForm({ ...memberForm, creator_platform_id: event.target.value })} />
              <label>创作者主页链接（选填）</label><input value={memberForm.creator_profile_url || ''} disabled={detailReadonly} onChange={(event) => setMemberForm({ ...memberForm, creator_profile_url: event.target.value })} />
              <label>昵称</label><input value={memberForm.display_name || ''} disabled={detailReadonly} onChange={(event) => setMemberForm({ ...memberForm, display_name: event.target.value })} />
              <button onClick={addMember} disabled={!selected || !canEditGroup(selected)}><Plus size={14} />添加成员</button>
            </div>
            <div className="detail-section">
              <b>业务账号类型绑定</b>
              {bindings.length === 0 ? <span>暂无绑定</span> : bindings.map((item) => <span key={item.id}>{item.business_account_type_name || item.business_account_type_id}</span>)}
              {isOperator ? (
                <span className="muted-hint">运营账户创建的对标组会自动绑定到所属业务类型。</span>
              ) : (
                <>
                  <ResourceSelect label="绑定业务类型" value={businessTypeId} options={typeOptions} onChange={setBusinessTypeId} />
                  <button onClick={bindType} disabled={!selected || !canEditGroup(selected)}><Plus size={14} />添加绑定</button>
                </>
              )}
            </div>
          </>
        )}
      </aside>
    </section>
  );
}
