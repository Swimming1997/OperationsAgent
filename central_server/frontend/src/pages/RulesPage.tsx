import { Plus, Save, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { createOperationRule, deleteOperationRule, listOperationRules, updateOperationRule } from '../api/operationRules';
import { bindBusinessTypeRuleSet, createKeywordRule, createKeywordRuleSet, deleteKeywordRule, deleteKeywordRuleSet, listBusinessAccountTypes, listBusinessTypeRuleSets, listKeywordRules, listKeywordRuleSets, updateKeywordRule, updateKeywordRuleSet } from '../api/resources';
import { ResourceSelect } from '../components/ResourceSelect';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { BusinessAccountType, BusinessAccountTypeRuleSet, KeywordRule, KeywordRuleSet, OperationRule, Role } from '../types/api';
import { labelOperationRuleType, OPERATION_RULE_PLATFORM_OPTIONS, OPERATION_RULE_TYPE_OPTIONS } from '../utils/operationRuleLabels';

type Props = { role: Role; userId: string };
type Tab = 'sets' | 'operation';

const TAB_LABELS: Record<Tab, string> = {
  sets: '业务规则',
  operation: '运营规则',
};

const RULE_SCOPE_OPTIONS = [
  { value: 'xhs', label: '小红书 (xhs)' },
  { value: 'douyin', label: '抖音 (douyin)' },
  { value: 'all', label: '全平台 (all)' },
];

const EMPTY_OPERATION_FORM: Partial<OperationRule> = {
  rule_type: 'title',
  title: '',
  content: '',
  platform: null,
  enabled: true,
};

export function RulesPage({ role, userId }: Props) {
  const [tab, setTab] = useState<Tab>('sets');
  const [sets, setSets] = useState<KeywordRuleSet[]>([]);
  const [rules, setRules] = useState<KeywordRule[]>([]);
  const [types, setTypes] = useState<BusinessAccountType[]>([]);
  const [ruleSetBindings, setRuleSetBindings] = useState<BusinessAccountTypeRuleSet[]>([]);
  const [ruleSetBindingLabels, setRuleSetBindingLabels] = useState<Record<string, string[]>>({});
  const [operationRules, setOperationRules] = useState<OperationRule[]>([]);
  const [operationFilterType, setOperationFilterType] = useState('');
  const [operationFilterPlatform, setOperationFilterPlatform] = useState('');
  const [selectedSet, setSelectedSet] = useState<KeywordRuleSet | null>(null);
  const [selectedOperationRule, setSelectedOperationRule] = useState<OperationRule | null>(null);
  const [setForm, setSetForm] = useState<Partial<KeywordRuleSet>>({ name: '', rule_scope: 'xhs', enabled: true });
  const [ruleForm, setRuleForm] = useState<Partial<KeywordRule>>({ keyword: '', match_mode: 'contains', weight: 1, enabled: true });
  const [operationForm, setOperationForm] = useState<Partial<OperationRule>>(EMPTY_OPERATION_FORM);
  const [bumpVersion, setBumpVersion] = useState(false);
  const [bindRuleSetId, setBindRuleSetId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const isOperator = role === 'operator';
  const canManageAll = role === 'admin' || role === 'supervisor';
  const canEditSet = (set: KeywordRuleSet | null) => {
    if (!set) return false;
    if (canManageAll) return true;
    return Boolean(set.created_by_user_id && set.created_by_user_id === userId);
  };
  const canCreateSet = canManageAll || isOperator;
  const canManageOperationRules = role === 'admin' || role === 'supervisor';
  const setDetailReadonly = selectedSet ? !canEditSet(selectedSet) : false;
  const typeOptions = useMemo(() => types.map((item) => ({ value: item.id, label: item.name, description: item.description || undefined })), [types]);

  function ruleSetSummary(form: Partial<KeywordRuleSet>) {
    const config = form.config;
    if (!config || typeof config !== 'object') return '';
    const summary = (config as Record<string, unknown>).summary;
    return typeof summary === 'string' ? summary : '';
  }

  function setRuleSetSummary(nextSummary: string) {
    setRuleSetConfigValue('summary', nextSummary);
  }

  function ruleSetConfigValue(key: string, fallback: unknown = '') {
    const config = setForm.config;
    if (!config || typeof config !== 'object') return fallback;
    const value = (config as Record<string, unknown>)[key];
    return value ?? fallback;
  }

  function setRuleSetConfigValue(key: string, value: unknown) {
    const currentConfig = (setForm.config && typeof setForm.config === 'object' ? setForm.config : {}) as Record<string, unknown>;
    setSetForm({
      ...setForm,
      config: {
        ...currentConfig,
        [key]: value,
      },
    });
  }

  function leadIntentText() {
    const value = ruleSetConfigValue('lead_intent_keywords', []);
    return Array.isArray(value) ? value.join('，') : '';
  }

  function setLeadIntentText(value: string) {
    setRuleSetConfigValue('lead_intent_keywords', value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean));
  }

  useEffect(() => { void reload(); }, [role, userId]);
  useEffect(() => {
    if (selectedSet) {
      void reloadRules(selectedSet.id);
      void reloadRuleSetBindings(selectedSet.id);
    }
  }, [selectedSet?.id, types.length]);
  useEffect(() => {
    if (tab === 'operation') void reloadOperationRules();
  }, [tab, role, userId, operationFilterType, operationFilterPlatform]);

  async function reload() {
    setLoading(true);
    try {
      const [nextSets, nextTypes] = await Promise.all([listKeywordRuleSets(role, userId), listBusinessAccountTypes(role, userId)]);
      setSets(nextSets);
      setTypes(nextTypes);
      await reloadAllRuleSetBindingLabels(nextSets, nextTypes);
      setSelectedSet((current) => current || nextSets[0] || null);
      setSetForm((current) => current.name ? current : nextSets[0] || { name: '', rule_scope: 'xhs', enabled: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : '规则加载失败');
    } finally {
      setLoading(false);
    }
  }

  async function reloadRules(ruleSetId: string) {
    setRules(await listKeywordRules(role, ruleSetId, userId));
  }

  async function reloadRuleSetBindings(ruleSetId: string) {
    if (!types.length) {
      setRuleSetBindings([]);
      return;
    }
    const rows = await Promise.all(types.map((type) => listBusinessTypeRuleSets(role, type.id, userId)));
    setRuleSetBindings(rows.flat().filter((item) => item.rule_set_id === ruleSetId));
  }

  async function reloadAllRuleSetBindingLabels(nextSets: KeywordRuleSet[], nextTypes: BusinessAccountType[]) {
    if (!nextSets.length || !nextTypes.length) {
      setRuleSetBindingLabels({});
      return;
    }
    const rows = await Promise.all(nextTypes.map((type) => listBusinessTypeRuleSets(role, type.id, userId)));
    const labels: Record<string, string[]> = {};
    for (const binding of rows.flat()) {
      const ruleSetExists = nextSets.some((item) => item.id === binding.rule_set_id);
      if (!ruleSetExists) continue;
      const typeName = nextTypes.find((type) => type.id === binding.business_account_type_id)?.name || binding.business_account_type_id;
      labels[binding.rule_set_id] = [...(labels[binding.rule_set_id] || []), typeName];
    }
    setRuleSetBindingLabels(labels);
  }

  async function reloadOperationRules() {
    setLoading(true);
    try {
      const rows = await listOperationRules(
        role,
        {
          rule_type: operationFilterType || undefined,
          platform: operationFilterPlatform || undefined,
        },
        userId,
      );
      setOperationRules(rows);
      setSelectedOperationRule((current) => current && rows.some((item) => item.id === current.id) ? current : rows[0] || null);
      setOperationForm((current) => {
        if (current.id) return current;
        return rows[0] || EMPTY_OPERATION_FORM;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '运营规则加载失败');
    } finally {
      setLoading(false);
    }
  }

  async function saveSet() {
    if (!canCreateSet || !setForm.name || !setForm.rule_scope) return;
    if (selectedSet && !canEditSet(selectedSet)) return;
    const saved = selectedSet
      ? await updateKeywordRuleSet(role, selectedSet.id, setForm, userId)
      : await createKeywordRuleSet(role, { name: setForm.name, rule_scope: setForm.rule_scope, enabled: setForm.enabled ?? true, config: setForm.config || {} }, userId);
    setSelectedSet(saved);
    setSetForm(saved);
    await reload();
  }

  async function saveRule() {
    if (!selectedSet || !ruleForm.keyword || !canEditSet(selectedSet)) return;
    const payload = {
      keyword: ruleForm.keyword,
      match_mode: ruleForm.match_mode || 'contains',
      weight: ruleForm.weight || 1,
      enabled: ruleForm.enabled ?? true,
      normalized_keyword: ruleForm.normalized_keyword || null,
    };
    if (ruleForm.id) {
      await updateKeywordRule(role, ruleForm.id, payload, userId);
    } else {
      await createKeywordRule(role, selectedSet.id, payload, userId);
    }
    setRuleForm({ keyword: '', match_mode: 'contains', weight: 1, enabled: true });
    await reloadRules(selectedSet.id);
  }

  async function removeRule(rule: KeywordRule) {
    if (!selectedSet || !canEditSet(selectedSet)) return;
    await deleteKeywordRule(role, rule.id, userId);
    if (ruleForm.id === rule.id) {
      setRuleForm({ keyword: '', match_mode: 'contains', weight: 1, enabled: true });
    }
    await reloadRules(selectedSet.id);
  }

  async function removeSet(set: KeywordRuleSet) {
    if (!canEditSet(set)) return;
    if (!window.confirm(`确认删除业务规则「${set.name}」？删除后会同时移除它的关键词规则和业务类型绑定。`)) return;
    await deleteKeywordRuleSet(role, set.id, userId);
    if (selectedSet?.id === set.id) {
      setSelectedSet(null);
      setSetForm({ name: '', rule_scope: 'xhs', enabled: true });
      setRules([]);
      setRuleSetBindings([]);
    }
    await reload();
  }

  function selectSet(set: KeywordRuleSet) {
    setSelectedSet(set);
    setSetForm(set);
    setRuleForm({ keyword: '', match_mode: 'contains', weight: 1, enabled: true });
    setBindRuleSetId('');
    setTab('sets');
  }

  async function bindRuleSet() {
    if (!selectedSet || !bindRuleSetId || !canEditSet(selectedSet)) return;
    await bindBusinessTypeRuleSet(role, bindRuleSetId, selectedSet.id, false, userId);
    setBindRuleSetId('');
    await reloadRuleSetBindings(selectedSet.id);
    await reloadAllRuleSetBindingLabels(sets, types);
  }

  async function saveOperationRule() {
    if (!canManageOperationRules || !operationForm.rule_type || !operationForm.title || !operationForm.content) return;
    if (operationForm.id) {
      const saved = await updateOperationRule(
        role,
        operationForm.id,
        {
          title: operationForm.title,
          content: operationForm.content,
          platform: operationForm.platform ?? null,
          enabled: operationForm.enabled,
          bump_version: bumpVersion,
        },
        userId,
      );
      setSelectedOperationRule(saved);
      setOperationForm(saved);
      setBumpVersion(false);
    } else {
      const saved = await createOperationRule(
        role,
        {
          rule_type: operationForm.rule_type,
          title: operationForm.title,
          content: operationForm.content,
          platform: operationForm.platform || undefined,
          enabled: operationForm.enabled ?? true,
        },
        userId,
      );
      setSelectedOperationRule(saved);
      setOperationForm(saved);
    }
    await reloadOperationRules();
  }

  function selectOperationRule(rule: OperationRule) {
    setSelectedOperationRule(rule);
    setOperationForm(rule);
    setBumpVersion(false);
  }

  async function removeOperationRule(rule: OperationRule) {
    if (!canManageOperationRules) return;
    if (!window.confirm(`确认删除运营规则「${rule.title}」？`)) return;
    await deleteOperationRule(role, rule.id, userId);
    if (selectedOperationRule?.id === rule.id) {
      setSelectedOperationRule(null);
      setOperationForm({ ...EMPTY_OPERATION_FORM });
      setBumpVersion(false);
    }
    await reloadOperationRules();
  }

  function startNewOperationRule() {
    setSelectedOperationRule(null);
    setOperationForm({ ...EMPTY_OPERATION_FORM });
    setBumpVersion(false);
    setTab('operation');
  }

  return (
    <section className="page-grid resource-grid">
      <aside className="filter-panel">
        <div className="panel-title">规则管理</div>
        {(['sets', 'operation'] as Tab[]).map((item) => (
          <button key={item} className={`type-tab ${tab === item ? 'active' : ''}`} onClick={() => setTab(item)}>
            {TAB_LABELS[item]}
          </button>
        ))}
        {tab === 'sets' && (
          <button onClick={() => { setSelectedSet(null); setSetForm({ name: '', rule_scope: 'xhs', enabled: true }); }}>
            <Plus size={14} />新建业务规则
          </button>
        )}
        {tab === 'operation' && canManageOperationRules && (
          <button onClick={startNewOperationRule}>
            <Plus size={14} />新建运营规则
          </button>
        )}
      </aside>
      <section className="list-panel">
        <div className="section-head">
          <div>
            <h1>规则管理</h1>
            <span>
              {tab === 'operation' ? `${operationRules.length} 条运营规则` : `${sets.length} 个业务规则`}
            </span>
          </div>
        </div>
        {error && <ErrorState text={error} />}
        {tab === 'operation' ? (
          <>
            <div className="filter-row compact-filters">
              <select value={operationFilterType} onChange={(event) => setOperationFilterType(event.target.value)}>
                {OPERATION_RULE_TYPE_OPTIONS.map((item) => (
                  <option key={item.value || 'all'} value={item.value}>{item.label}</option>
                ))}
              </select>
              <select value={operationFilterPlatform} onChange={(event) => setOperationFilterPlatform(event.target.value)}>
                {OPERATION_RULE_PLATFORM_OPTIONS.map((item) => (
                  <option key={item.value || 'all'} value={item.value}>{item.label}</option>
                ))}
              </select>
            </div>
            {loading ? <LoadingState text="运营规则加载中" /> : operationRules.length === 0 ? (
              <EmptyState text="暂无运营规则" />
            ) : (
              <div className="data-table">
                <div className="table-row table-head operation-rule-row">
                  <span>标题</span><span>类型</span><span>平台</span><span>版本</span><span>操作</span>
                </div>
                {operationRules.map((rule) => (
                  <div
                    key={rule.id}
                    className={`table-row operation-rule-row ${selectedOperationRule?.id === rule.id ? 'selected' : ''}`}
                    onClick={() => selectOperationRule(rule)}
                  >
                    <span className="strong">{rule.title}</span>
                    <span>{labelOperationRuleType(rule.rule_type)}</span>
                    <span>{rule.platform || '全平台'}</span>
                    <span>v{rule.version}</span>
                    <button type="button" className="icon-button danger" title="删除运营规则" disabled={!canManageOperationRules} onClick={(event) => { event.stopPropagation(); void removeOperationRule(rule); }}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : loading ? (
          <LoadingState text="规则加载中" />
        ) : sets.length === 0 ? (
          <EmptyState text="暂无业务规则" />
        ) : (
          <div className="data-table">
            <div className="table-row table-head rule-set-row"><span>名称</span><span>scope</span><span>启用</span><span>提交人</span><span>绑定业务类型</span><span>摘要</span><span>操作</span></div>
            {sets.map((set) => (
              <div
                key={set.id}
                className={`table-row rule-set-row ${selectedSet?.id === set.id ? 'selected' : ''}`}
                onClick={() => selectSet(set)}
              >
                <span className="strong">{set.name}</span><span>{set.rule_scope}</span><span>{set.enabled ? '启用' : '停用'}</span><span>{set.submitter_name || '历史数据'}</span><span>{(ruleSetBindingLabels[set.id] || []).join('、') || '未绑定'}</span><span>{ruleSetSummary(set) || '—'}</span>
              <button type="button" className="icon-button danger" title="删除业务规则" disabled={!canEditSet(set)} onClick={(event) => { event.stopPropagation(); void removeSet(set); }}>
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
      <aside className="detail-panel">
        {tab === 'sets' && (
          <div className="form-stack">
            <div className="panel-title">{selectedSet ? '业务规则详情' : '新建业务规则'}</div>
            <label>名称</label><input value={setForm.name || ''} disabled={setDetailReadonly} onChange={(event) => setSetForm({ ...setForm, name: event.target.value })} />
            <label>scope</label>
            <select value={setForm.rule_scope || 'xhs'} disabled={setDetailReadonly} onChange={(event) => setSetForm({ ...setForm, rule_scope: event.target.value })}>
              {RULE_SCOPE_OPTIONS.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
            <label>摘要</label>
            <input
              value={ruleSetSummary(setForm)}
              disabled={setDetailReadonly}
              onChange={(event) => setRuleSetSummary(event.target.value)}
              placeholder="例如：用于论文服务号的核心关键词筛选"
            />
            <label>入池点赞阈值</label>
            <input
              type="number"
              min="0"
              value={Number(ruleSetConfigValue('visible_like_threshold', 50))}
              disabled={setDetailReadonly}
              onChange={(event) => setRuleSetConfigValue('visible_like_threshold', Number(event.target.value))}
            />
            <label>线索意图词</label>
            <textarea
              value={leadIntentText()}
              disabled={setDetailReadonly}
              onChange={(event) => setLeadIntentText(event.target.value)}
              placeholder="例如：求推荐，求渠道，怎么联系"
            />
            <span className="muted-hint">关键词规则用于业务命中；线索意图词和点赞阈值会用于情报中心入池过滤。</span>
            <label className="check-line"><input type="checkbox" checked={setForm.enabled !== false} disabled={setDetailReadonly} onChange={(event) => setSetForm({ ...setForm, enabled: event.target.checked })} />启用</label>
            {!selectedSet ? <span className="muted-hint">创建后会自动按当前运营账号所属业务类型绑定。</span> : null}
            {selectedSet && !canEditSet(selectedSet) ? <span className="muted-hint">仅提交人或管理账户可编辑该业务规则。</span> : null}
            <button onClick={saveSet} disabled={!canCreateSet || (selectedSet ? !canEditSet(selectedSet) : false)}><Save size={14} />保存业务规则</button>

            {selectedSet && (
              <div className="detail-section">
                <b>关键词规则</b>
                <div className="mini-list">
                  {rules.length === 0 ? <span className="muted-hint">当前业务规则还没有关键词规则</span> : rules.map((rule) => (
                    <div key={rule.id} className={`mini-row ${ruleForm.id === rule.id ? 'selected' : ''}`}>
                      <button type="button" className="mini-row-main" onClick={() => setRuleForm(rule)}>
                        <span>{rule.keyword}</span>
                        <small>{rule.match_mode} / 权重 {rule.weight}{rule.enabled ? '' : ' / 停用'}</small>
                      </button>
                      <button type="button" className="icon-button danger" title="删除关键词规则" disabled={!canEditSet(selectedSet)} onClick={() => void removeRule(rule)}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>

                <button type="button" onClick={() => setRuleForm({ keyword: '', match_mode: 'contains', weight: 1, enabled: true })} disabled={!canEditSet(selectedSet)}>
                  <Plus size={14} />新增关键词规则
                </button>
                <label>关键词</label>
                <input value={ruleForm.keyword || ''} disabled={setDetailReadonly} onChange={(event) => setRuleForm({ ...ruleForm, keyword: event.target.value })} placeholder="例如：SCI 论文" />
                <label>匹配方式</label>
                <select value={ruleForm.match_mode || 'contains'} disabled={setDetailReadonly} onChange={(event) => setRuleForm({ ...ruleForm, match_mode: event.target.value })}>
                  <option value="contains">包含</option>
                  <option value="equals">等于</option>
                  <option value="regex">正则</option>
                </select>
                <label>权重</label>
                <input type="number" value={ruleForm.weight || 1} disabled={setDetailReadonly} onChange={(event) => setRuleForm({ ...ruleForm, weight: Number(event.target.value) })} />
                <label className="check-line"><input type="checkbox" checked={ruleForm.enabled !== false} disabled={setDetailReadonly} onChange={(event) => setRuleForm({ ...ruleForm, enabled: event.target.checked })} />启用</label>
                {ruleForm.normalized_keyword ? <span className="muted-hint">系统匹配值：{ruleForm.normalized_keyword}</span> : null}
                <button onClick={saveRule} disabled={!selectedSet || !ruleForm.keyword || !canEditSet(selectedSet)}><Save size={14} />{ruleForm.id ? '更新关键词规则' : '添加关键词规则'}</button>
              </div>
            )}
            {selectedSet && (
              <div className="detail-section">
                <b>适用业务类型</b>
                <div className="mini-list">
                  {ruleSetBindings.length === 0 ? <span className="muted-hint">当前业务规则还没有绑定业务类型</span> : ruleSetBindings.map((item) => (
                    <span key={item.id} className="mini-row passive">
                      {types.find((type) => type.id === item.business_account_type_id)?.name || item.business_account_type_id}
                      <span>{item.is_default ? '默认' : '已绑定'}</span>
                    </span>
                  ))}
                </div>
                {isOperator ? (
                  <span className="muted-hint">运营账户创建的业务规则会自动绑定到所属业务类型。</span>
                ) : (
                  <>
                    <ResourceSelect label="绑定业务类型" value={bindRuleSetId} options={typeOptions} onChange={setBindRuleSetId} />
                    <button onClick={bindRuleSet} disabled={!bindRuleSetId || !canEditSet(selectedSet)}><Plus size={14} />绑定到当前业务规则</button>
                  </>
                )}
              </div>
            )}
          </div>
        )}
        {tab === 'operation' && (
          <div className="form-stack">
            <div className="panel-title">运营规则</div>
            <p className="muted-hint">供仿写/运营经验引用；对标库「规则自动」仍走 RuleProfile + 关键词，非本表。</p>
            <label>规则类型</label>
            <select
              value={operationForm.rule_type || 'title'}
              disabled={!!operationForm.id || !canManageOperationRules}
              onChange={(event) => setOperationForm({ ...operationForm, rule_type: event.target.value })}
            >
              {OPERATION_RULE_TYPE_OPTIONS.filter((item) => item.value).map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
            <label>标题</label>
            <input value={operationForm.title || ''} disabled={!canManageOperationRules} onChange={(event) => setOperationForm({ ...operationForm, title: event.target.value })} />
            <label>平台（空=全平台）</label>
            <select
              value={operationForm.platform || ''}
              disabled={!canManageOperationRules}
              onChange={(event) => setOperationForm({ ...operationForm, platform: event.target.value || null })}
            >
              {OPERATION_RULE_PLATFORM_OPTIONS.map((item) => (
                <option key={item.value || 'all'} value={item.value}>{item.label}</option>
              ))}
            </select>
            <label>正文</label>
            <textarea rows={8} value={operationForm.content || ''} disabled={!canManageOperationRules} onChange={(event) => setOperationForm({ ...operationForm, content: event.target.value })} />
            <label className="check-line">
              <input type="checkbox" checked={operationForm.enabled !== false} disabled={!canManageOperationRules} onChange={(event) => setOperationForm({ ...operationForm, enabled: event.target.checked })} />
              启用
            </label>
            {operationForm.id && (
              <label className="check-line">
                <input type="checkbox" checked={bumpVersion} disabled={!canManageOperationRules} onChange={(event) => setBumpVersion(event.target.checked)} />
                保存时递增版本（当前 v{operationForm.version ?? 1}）
              </label>
            )}
            <button onClick={saveOperationRule} disabled={!canManageOperationRules}>
              <Save size={14} />{operationForm.id ? '更新运营规则' : '创建运营规则'}
            </button>
          </div>
        )}
      </aside>
    </section>
  );
}
