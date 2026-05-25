import { Plus, Save } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { bindBusinessTypeRuleSet, createKeywordRule, createKeywordRuleSet, listBusinessAccountTypes, listBusinessTypeRuleSets, listKeywordRules, listKeywordRuleSets, updateKeywordRule, updateKeywordRuleSet } from '../api/resources';
import { ResourceSelect } from '../components/ResourceSelect';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { BusinessAccountType, BusinessAccountTypeRuleSet, KeywordRule, KeywordRuleSet, Role } from '../types/api';

type Props = { role: Role; userId: string };
type Tab = 'sets' | 'rules' | 'bindings';

export function RulesPage({ role, userId }: Props) {
  const [tab, setTab] = useState<Tab>('sets');
  const [sets, setSets] = useState<KeywordRuleSet[]>([]);
  const [rules, setRules] = useState<KeywordRule[]>([]);
  const [types, setTypes] = useState<BusinessAccountType[]>([]);
  const [bindings, setBindings] = useState<BusinessAccountTypeRuleSet[]>([]);
  const [selectedSet, setSelectedSet] = useState<KeywordRuleSet | null>(null);
  const [selectedTypeId, setSelectedTypeId] = useState('');
  const [setForm, setSetForm] = useState<Partial<KeywordRuleSet>>({ name: '', rule_scope: 'xhs', enabled: true });
  const [ruleForm, setRuleForm] = useState<Partial<KeywordRule>>({ keyword: '', match_mode: 'contains', weight: 1, enabled: true });
  const [bindRuleSetId, setBindRuleSetId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const readonly = role === 'operator';
  const setOptions = useMemo(() => sets.map((item) => ({ value: item.id, label: item.name, description: item.rule_scope })), [sets]);
  const typeOptions = useMemo(() => types.map((item) => ({ value: item.id, label: item.name, description: item.enabled ? '启用' : '停用' })), [types]);

  useEffect(() => { void reload(); }, [role, userId]);
  useEffect(() => { if (selectedSet) void reloadRules(selectedSet.id); }, [selectedSet?.id]);
  useEffect(() => { if (selectedTypeId) void reloadBindings(selectedTypeId); }, [selectedTypeId]);

  async function reload() {
    setLoading(true);
    try {
      const [nextSets, nextTypes] = await Promise.all([listKeywordRuleSets(role, userId), listBusinessAccountTypes(role, userId)]);
      setSets(nextSets);
      setTypes(nextTypes);
      setSelectedSet((current) => current || nextSets[0] || null);
      setSetForm((current) => current.name ? current : nextSets[0] || { name: '', rule_scope: 'xhs', enabled: true });
      setSelectedTypeId((current) => current || nextTypes[0]?.id || '');
    } catch (err) {
      setError(err instanceof Error ? err.message : '规则加载失败');
    } finally {
      setLoading(false);
    }
  }

  async function reloadRules(ruleSetId: string) {
    setRules(await listKeywordRules(role, ruleSetId, userId));
  }

  async function reloadBindings(typeId: string) {
    setBindings(await listBusinessTypeRuleSets(role, typeId, userId));
  }

  async function saveSet() {
    if (readonly || !setForm.name || !setForm.rule_scope) return;
    const saved = selectedSet
      ? await updateKeywordRuleSet(role, selectedSet.id, setForm, userId)
      : await createKeywordRuleSet(role, { name: setForm.name, rule_scope: setForm.rule_scope, enabled: setForm.enabled ?? true, config: setForm.config || {} }, userId);
    setSelectedSet(saved);
    setSetForm(saved);
    await reload();
  }

  async function saveRule() {
    if (readonly || !selectedSet || !ruleForm.keyword) return;
    if (ruleForm.id) {
      await updateKeywordRule(role, ruleForm.id, ruleForm, userId);
    } else {
      await createKeywordRule(role, selectedSet.id, ruleForm, userId);
    }
    setRuleForm({ keyword: '', match_mode: 'contains', weight: 1, enabled: true });
    await reloadRules(selectedSet.id);
  }

  async function bindRuleSet() {
    if (readonly || !selectedTypeId || !bindRuleSetId) return;
    await bindBusinessTypeRuleSet(role, selectedTypeId, bindRuleSetId, false, userId);
    await reloadBindings(selectedTypeId);
  }

  return (
    <section className="page-grid resource-grid">
      <aside className="filter-panel">
        <div className="panel-title">规则管理</div>
        {(['sets', 'rules', 'bindings'] as Tab[]).map((item) => <button key={item} className={`type-tab ${tab === item ? 'active' : ''}`} onClick={() => setTab(item)}>{item === 'sets' ? '规则集' : item === 'rules' ? '关键词规则' : '业务类型绑定'}</button>)}
        <button onClick={() => { setSelectedSet(null); setSetForm({ name: '', rule_scope: 'xhs', enabled: true }); }}><Plus size={14} />新建规则集</button>
      </aside>
      <section className="list-panel">
        <div className="section-head"><div><h1>规则管理</h1><span>{sets.length} 个规则集</span></div></div>
        {error && <ErrorState text={error} />}
        {loading ? <LoadingState text="规则加载中" /> : sets.length === 0 ? <EmptyState text="暂无规则集" /> : (
          <div className="data-table">
            <div className="table-row table-head rule-set-row"><span>名称</span><span>scope</span><span>启用</span><span>摘要</span></div>
            {sets.map((set) => <button key={set.id} className={`table-row rule-set-row ${selectedSet?.id === set.id ? 'selected' : ''}`} onClick={() => { setSelectedSet(set); setSetForm(set); setTab('rules'); }}><span className="strong">{set.name}</span><span>{set.rule_scope}</span><span>{set.enabled ? '启用' : '停用'}</span><span>{JSON.stringify(set.config)}</span></button>)}
          </div>
        )}
      </section>
      <aside className="detail-panel">
        {tab === 'sets' && (
          <div className="form-stack">
            <div className="panel-title">规则集</div>
            <label>名称</label><input value={setForm.name || ''} onChange={(event) => setSetForm({ ...setForm, name: event.target.value })} />
            <label>scope</label><input value={setForm.rule_scope || ''} onChange={(event) => setSetForm({ ...setForm, rule_scope: event.target.value })} />
            <label className="check-line"><input type="checkbox" checked={setForm.enabled !== false} onChange={(event) => setSetForm({ ...setForm, enabled: event.target.checked })} />启用</label>
            <button onClick={saveSet} disabled={readonly}><Save size={14} />保存规则集</button>
          </div>
        )}
        {tab === 'rules' && (
          <div className="detail-section">
            <b>关键词规则：{selectedSet?.name || '-'}</b>
            <div className="mini-list">{rules.map((rule) => <button key={rule.id} className="mini-row" onClick={() => setRuleForm(rule)}>{rule.keyword}<span>{rule.match_mode} / {rule.weight}</span></button>)}</div>
            <label>关键词</label><input value={ruleForm.keyword || ''} onChange={(event) => setRuleForm({ ...ruleForm, keyword: event.target.value })} />
            <label>normalized_keyword</label><input value={ruleForm.normalized_keyword || ''} onChange={(event) => setRuleForm({ ...ruleForm, normalized_keyword: event.target.value })} />
            <label>match_mode</label><input value={ruleForm.match_mode || 'contains'} onChange={(event) => setRuleForm({ ...ruleForm, match_mode: event.target.value })} />
            <label>weight</label><input type="number" value={ruleForm.weight || 1} onChange={(event) => setRuleForm({ ...ruleForm, weight: Number(event.target.value) })} />
            <label className="check-line"><input type="checkbox" checked={ruleForm.enabled !== false} onChange={(event) => setRuleForm({ ...ruleForm, enabled: event.target.checked })} />启用</label>
            <button onClick={saveRule} disabled={readonly || !selectedSet}><Save size={14} />保存规则</button>
          </div>
        )}
        {tab === 'bindings' && (
          <div className="detail-section">
            <b>业务账号类型绑定</b>
            <ResourceSelect label="业务账号类型" value={selectedTypeId} options={typeOptions} onChange={setSelectedTypeId} />
            {bindings.length === 0 ? <span>暂无绑定规则集</span> : bindings.map((item) => <span key={item.id}>{item.rule_set_name || item.rule_set_id}{item.is_default ? ' · 默认' : ''}</span>)}
            <ResourceSelect label="添加规则集" value={bindRuleSetId} options={setOptions} onChange={setBindRuleSetId} />
            <button onClick={bindRuleSet} disabled={readonly}><Plus size={14} />添加绑定</button>
          </div>
        )}
      </aside>
    </section>
  );
}
