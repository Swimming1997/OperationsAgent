import { Check, Plus, RotateCcw, Save, Search, Trash2, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { IntelligenceFilters } from '../../api/intelligence';
import type { ProductOptions } from '../../types/api';
import { INTELLIGENCE_SOURCE_OPTIONS, localizeOptionItems } from '../../utils/intelligenceLabels';
import { IntelligenceScenarioTabs } from './IntelligenceScenarioTabs';
import type { CustomIntelligenceScenario, IntelligenceScenario } from './scenarioPresets';
import { isCustomScenario, listCustomScenarios, type ScenarioFilterState } from './scenarioPresets';

const DATA_STATUS_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'card_only', label: '仅卡片' },
  { value: 'detail_ready', label: '详情就绪' },
  { value: 'comments_ready', label: '评论就绪' },
];

const REFERENCE_LIBRARY_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'false', label: '未入库' },
  { value: 'true', label: '已入库' },
];

const SORT_OPTIONS = [
  { value: 'latest_discovered_at', label: '最近发现' },
  { value: 'like_count', label: '点赞数' },
  { value: 'comment_count', label: '评论数' },
  { value: 'collect_count', label: '收藏数' },
  { value: 'discovery_count', label: '发现次数' },
  { value: 'best_search_rank', label: '搜索排名' },
];

type DisplayOptions = {
  platforms: Array<{ value: string; label: string }>;
  workflow_statuses: Array<{ value: string; label: string }>;
  candidate_buckets: Array<{ value: string; label: string }>;
};

type Props = {
  scenario: IntelligenceScenario;
  filters: IntelligenceFilters;
  quickFilters: IntelligenceFilters;
  displayOptions: DisplayOptions | null;
  advancedOpen: boolean;
  filterPreferencesEnabled?: boolean;
  hasCustomizedFilters: boolean;
  savingScenarioFilters: boolean;
  savedScenarioFilters: Partial<Record<IntelligenceScenario, ScenarioFilterState>>;
  onScenarioChange: (scenario: IntelligenceScenario) => void;
  onAdvancedOpenChange: (open: boolean) => void;
  onQuickFilterChange: (key: keyof IntelligenceFilters, value: string) => void;
  onFilterChange: (key: keyof IntelligenceFilters, value: string) => void;
  onSearch: () => void;
  onReset: () => void;
  onSaveScenarioFilters: () => void;
  onRestoreSystemDefault: () => void;
  onAddCustomScenario: (label: string) => void;
  onDeleteCustomScenario: () => void;
};

function splitMultiValue(value?: string) {
  return (value || '').split(',').map((item) => item.trim()).filter(Boolean);
}

function joinMultiValue(values: string[]) {
  return values.length > 0 ? values.join(',') : '';
}

function MultiFilterDropdown({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value?: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const selectedValues = splitMultiValue(value);
  const selectedSet = new Set(selectedValues);
  const selectedOptions = selectedValues
    .map((selected) => options.find((item) => item.value === selected))
    .filter((item): item is { value: string; label: string } => Boolean(item));

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [open]);

  function applyChange(next: string) {
    onChange(next);
    setOpen(false);
  }

  function toggle(nextValue: string) {
    const next = selectedSet.has(nextValue)
      ? selectedValues.filter((item) => item !== nextValue)
      : [...selectedValues, nextValue];
    applyChange(joinMultiValue(next));
  }

  function remove(nextValue: string) {
    onChange(joinMultiValue(selectedValues.filter((item) => item !== nextValue)));
  }

  return (
    <div className="multi-filter-field">
      <label id={`${id}-label`}>{label}</label>
      <div ref={menuRef} className={`multi-filter-menu${open ? ' is-open' : ''}`}>
        <button
          type="button"
          id={id}
          className="multi-filter-trigger"
          aria-labelledby={`${id}-label ${id}`}
          aria-expanded={open}
          aria-haspopup="listbox"
          onClick={() => setOpen((current) => !current)}
        >
          <span>{selectedOptions.length > 0 ? `已选 ${selectedOptions.length} 项` : '全部'}</span>
        </button>
        {open ? (
          <div className="multi-filter-options" role="listbox" aria-labelledby={`${id}-label`}>
            <button type="button" className="multi-filter-option" onClick={() => applyChange('')}>
              <span className="multi-filter-check">{selectedOptions.length === 0 ? <Check size={14} /> : null}</span>
              全部
            </button>
            {options.map((item) => (
              <button key={item.value} type="button" className="multi-filter-option" onClick={() => toggle(item.value)}>
                <span className="multi-filter-check">{selectedSet.has(item.value) ? <Check size={14} /> : null}</span>
                {item.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      {selectedOptions.length > 0 ? (
        <div className="multi-filter-tags" aria-label={`${label}已选条件`}>
          {selectedOptions.map((item) => (
            <span key={item.value} className="filter-token">
              {item.label}
              <button type="button" aria-label={`移除${item.label}`} onClick={() => remove(item.value)}>
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function IntelligenceFilterPanel({
  scenario,
  filters,
  quickFilters,
  displayOptions,
  advancedOpen,
  filterPreferencesEnabled = true,
  hasCustomizedFilters,
  savingScenarioFilters,
  savedScenarioFilters,
  onScenarioChange,
  onAdvancedOpenChange,
  onQuickFilterChange,
  onFilterChange,
  onSearch,
  onReset,
  onSaveScenarioFilters,
  onRestoreSystemDefault,
  onAddCustomScenario,
  onDeleteCustomScenario,
}: Props) {
  const [addingCustomScenario, setAddingCustomScenario] = useState(false);
  const [customScenarioLabel, setCustomScenarioLabel] = useState('');
  const customScenarios = listCustomScenarios(savedScenarioFilters);
  const isCustom = isCustomScenario(scenario);

  function submitCustomScenario() {
    const label = customScenarioLabel.trim();
    if (!label) return;
    onAddCustomScenario(label);
    setCustomScenarioLabel('');
    setAddingCustomScenario(false);
  }

  return (
    <aside className="filter-panel">
      <div className="panel-title">筛选</div>

      <label>采集来源</label>
      <select
        value={quickFilters.source_surface || ''}
        onChange={(event) => onQuickFilterChange('source_surface', event.target.value)}
      >
        {INTELLIGENCE_SOURCE_OPTIONS.map((item) => (
          <option key={item.value || 'all'} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>

      <label>排序</label>
      <select
        value={quickFilters.sort_by || 'latest_discovered_at'}
        onChange={(event) => onQuickFilterChange('sort_by', event.target.value)}
      >
        {SORT_OPTIONS.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>

      <div className="filter-scenario-section">
        <span className="layer-label">场景快捷筛选</span>
        <IntelligenceScenarioTabs
          active={scenario}
          customScenarios={customScenarios}
          onChange={onScenarioChange}
          variant="sidebar"
        />
      </div>

      <button
        type="button"
        className="secondary advanced-filter-toggle"
        onClick={() => onAdvancedOpenChange(!advancedOpen)}
      >
        {advancedOpen ? '收起高级筛选' : '高级筛选'}
      </button>

      {advancedOpen && (
        <div className="advanced-filters" data-testid="intelligence-advanced-filters">
          {hasCustomizedFilters && !isCustom && <p className="filter-hint">当前场景已保存个人筛选规则。</p>}
          {isCustom && <p className="filter-hint">自定义场景快捷筛选，修改后请保存。</p>}

          <label>平台</label>
          <select value={filters.platform || ''} onChange={(event) => onFilterChange('platform', event.target.value)}>
            <option value="">全部</option>
            {displayOptions?.platforms.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <label htmlFor="filter-discovery-search-keyword">发现时搜索词（采集任务）</label>
          <input
            id="filter-discovery-search-keyword"
            value={filters.search_keyword || ''}
            onChange={(event) => onFilterChange('search_keyword', event.target.value)}
            placeholder="如：SCI（发现元数据中的任务关键词）"
          />

          <label>数据状态</label>
          <select value={filters.data_status || ''} onChange={(event) => onFilterChange('data_status', event.target.value)}>
            {DATA_STATUS_OPTIONS.map((item) => (
              <option key={item.value || 'all'} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <label>标签</label>
          <input
            value={filters.tag || ''}
            onChange={(event) => onFilterChange('tag', event.target.value)}
            placeholder="平台/搜索/运营标签"
          />

          <label htmlFor="filter-min-like-count">最低点赞</label>
          <input
            id="filter-min-like-count"
            value={filters.min_like_count || ''}
            onChange={(event) => onFilterChange('min_like_count', event.target.value)}
            placeholder="如：50"
          />

          <label htmlFor="filter-in-reference-library">入库状态</label>
          <select
            id="filter-in-reference-library"
            value={filters.in_reference_library || ''}
            onChange={(event) => onFilterChange('in_reference_library', event.target.value)}
          >
            {REFERENCE_LIBRARY_OPTIONS.map((item) => (
              <option key={item.value || 'all'} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <MultiFilterDropdown
            id="filter-candidate-bucket"
            label="候选分类"
            value={filters.candidate_bucket || ''}
            options={displayOptions?.candidate_buckets || []}
            onChange={(value) => onFilterChange('candidate_bucket', value)}
          />

          <label htmlFor="filter-manual-tag">运营标签</label>
          <input
            id="filter-manual-tag"
            value={filters.manual_tag || ''}
            onChange={(event) => onFilterChange('manual_tag', event.target.value)}
            placeholder="如：稍后看"
          />

          <MultiFilterDropdown
            id="filter-workflow-status"
            label="审核状态"
            value={filters.workflow_status || ''}
            options={displayOptions?.workflow_statuses || []}
            onChange={(value) => onFilterChange('workflow_status', value)}
          />

          <label htmlFor="filter-discovered-after">发现时间不早于</label>
          <input
            id="filter-discovered-after"
            type="datetime-local"
            value={filters.discovered_after ? filters.discovered_after.slice(0, 16) : ''}
            onChange={(event) =>
              onFilterChange(
                'discovered_after',
                event.target.value ? new Date(event.target.value).toISOString() : '',
              )
            }
          />

          {filterPreferencesEnabled ? (
          <div className="filter-persist-actions">
            <button type="button" className="secondary" disabled={savingScenarioFilters} onClick={onSaveScenarioFilters}>
              <Save size={14} />
              {isCustom ? '保存场景' : '保存到当前场景'}
            </button>
            {isCustom ? (
              <button
                type="button"
                className="secondary"
                disabled={savingScenarioFilters}
                onClick={onDeleteCustomScenario}
                data-testid="delete-custom-scenario-btn"
              >
                <Trash2 size={14} />
                删除场景
              </button>
            ) : (
              <button
                type="button"
                className="secondary"
                disabled={!hasCustomizedFilters || savingScenarioFilters}
                onClick={onRestoreSystemDefault}
              >
                恢复系统默认
              </button>
            )}
          </div>
          ) : null}

          {filterPreferencesEnabled ? (
          <div className="filter-custom-scenario-create">
            {addingCustomScenario ? (
              <div className="filter-custom-scenario-form">
                <label htmlFor="custom-scenario-label">场景名称</label>
                <input
                  id="custom-scenario-label"
                  value={customScenarioLabel}
                  onChange={(event) => setCustomScenarioLabel(event.target.value)}
                  onKeyDown={(event) => event.key === 'Enter' && submitCustomScenario()}
                  placeholder="如：近7天高赞线索"
                  maxLength={32}
                  autoFocus
                />
                <div className="filter-custom-scenario-form-actions">
                  <button type="button" disabled={!customScenarioLabel.trim() || savingScenarioFilters} onClick={submitCustomScenario}>
                    创建
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      setAddingCustomScenario(false);
                      setCustomScenarioLabel('');
                    }}
                  >
                    取消
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                className="secondary filter-add-scenario-btn"
                disabled={savingScenarioFilters}
                onClick={() => setAddingCustomScenario(true)}
                data-testid="add-custom-scenario-btn"
              >
                <Plus size={14} />
                添加场景快捷筛选
              </button>
            )}
            <p className="filter-hint">将当前高级筛选条件保存为新的场景快捷筛选项。</p>
          </div>
          ) : null}
        </div>
      )}

      <div className="filter-actions">
        <button type="button" onClick={onSearch}>
          <Search size={14} />
          查询
        </button>
        <button type="button" className="secondary" onClick={onReset}>
          <RotateCcw size={14} />
          重置
        </button>
      </div>
    </aside>
  );
}

export function buildDisplayOptions(options: ProductOptions | null) {
  if (!options) return null;
  return {
    platforms: localizeOptionItems(options.platforms, { xhs: '小红书', douyin: '抖音' }),
    workflow_statuses: localizeOptionItems(options.workflow_statuses, {
      pending_review: '待审核',
      assigned: '已分配',
      selected: '已选中',
      discarded: '已丢弃',
      archived: '已归档',
    }),
    candidate_buckets: localizeOptionItems(options.candidate_buckets, {
      lead_candidate: '线索候选',
      content_candidate: '内容候选',
      pending_enrichment: '待补全',
      discard: '已过滤',
    }),
  };
}
