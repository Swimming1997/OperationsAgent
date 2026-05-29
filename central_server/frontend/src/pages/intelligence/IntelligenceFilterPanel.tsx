import { RotateCcw, Save, Search } from 'lucide-react';
import type { IntelligenceFilters } from '../../api/intelligence';
import type { ProductOptions } from '../../types/api';
import { INTELLIGENCE_SOURCE_OPTIONS, localizeOptionItems } from '../../utils/intelligenceLabels';

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
  filters: IntelligenceFilters;
  quickFilters: IntelligenceFilters;
  displayOptions: DisplayOptions | null;
  advancedOpen: boolean;
  hasCustomizedFilters: boolean;
  savingScenarioFilters: boolean;
  onAdvancedOpenChange: (open: boolean) => void;
  onQuickFilterChange: (key: keyof IntelligenceFilters, value: string) => void;
  onFilterChange: (key: keyof IntelligenceFilters, value: string) => void;
  onSearch: () => void;
  onReset: () => void;
  onSaveScenarioFilters: () => void;
  onRestoreSystemDefault: () => void;
};

export function IntelligenceFilterPanel({
  filters,
  quickFilters,
  displayOptions,
  advancedOpen,
  hasCustomizedFilters,
  savingScenarioFilters,
  onAdvancedOpenChange,
  onQuickFilterChange,
  onFilterChange,
  onSearch,
  onReset,
  onSaveScenarioFilters,
  onRestoreSystemDefault,
}: Props) {
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

      <label>搜索关键词</label>
      <input
        value={quickFilters.search_keyword || ''}
        onChange={(event) => onQuickFilterChange('search_keyword', event.target.value)}
        placeholder="如：论文、SCI"
      />

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

      <button
        type="button"
        className="secondary advanced-filter-toggle"
        onClick={() => onAdvancedOpenChange(!advancedOpen)}
      >
        {advancedOpen ? '收起高级筛选' : '高级筛选'}
      </button>

      {advancedOpen && (
        <div className="advanced-filters" data-testid="intelligence-advanced-filters">
          {hasCustomizedFilters && <p className="filter-hint">当前 Tab 已保存个人筛选规则。</p>}

          <label>平台</label>
          <select value={filters.platform || ''} onChange={(event) => onFilterChange('platform', event.target.value)}>
            <option value="">全部</option>
            {displayOptions?.platforms.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

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

          <label htmlFor="filter-candidate-bucket">候选分类</label>
          <select
            id="filter-candidate-bucket"
            value={filters.candidate_bucket || ''}
            onChange={(event) => onFilterChange('candidate_bucket', event.target.value)}
          >
            <option value="">全部</option>
            {displayOptions?.candidate_buckets.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <label htmlFor="filter-manual-tag">运营标签</label>
          <input
            id="filter-manual-tag"
            value={filters.manual_tag || ''}
            onChange={(event) => onFilterChange('manual_tag', event.target.value)}
            placeholder="如：稍后看"
          />

          <label htmlFor="filter-workflow-status">审核状态</label>
          <select
            id="filter-workflow-status"
            value={filters.workflow_status || ''}
            onChange={(event) => onFilterChange('workflow_status', event.target.value)}
          >
            <option value="">全部</option>
            {displayOptions?.workflow_statuses.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <label>业务关键词</label>
          <input
            value={filters.business_keyword || ''}
            onChange={(event) => onFilterChange('business_keyword', event.target.value)}
            placeholder="正文/标题命中"
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

          <div className="filter-persist-actions">
            <button type="button" className="secondary" disabled={savingScenarioFilters} onClick={onSaveScenarioFilters}>
              <Save size={14} />
              保存筛选
            </button>
            <button
              type="button"
              className="secondary"
              disabled={!hasCustomizedFilters || savingScenarioFilters}
              onClick={onRestoreSystemDefault}
            >
              恢复系统默认
            </button>
          </div>
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
