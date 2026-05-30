import type { IntelligenceFilters } from '../../api/intelligence';

export type SystemIntelligenceScenario = 'pending' | 'leads' | 'hot' | 'watchlater' | 'all';
export type CustomIntelligenceScenario = `custom-${string}`;
export type IntelligenceScenario = SystemIntelligenceScenario | CustomIntelligenceScenario;

export type ScenarioRollingConfig = {
  discovered_after_days?: number;
  label?: string;
};

export type ScenarioFilterState = {
  filters: Partial<IntelligenceFilters>;
  rolling: ScenarioRollingConfig;
};

export type SavedScenarioFilter = ScenarioFilterState & {
  scenario: IntelligenceScenario;
  updated_at?: string | null;
  is_user_customized?: boolean;
};

export const HOT_ENGAGEMENT_MIN_LIKES = '100';

export const SYSTEM_SCENARIO_TABS: Array<{ id: SystemIntelligenceScenario; label: string }> = [
  { id: 'pending', label: '待处理' },
  { id: 'leads', label: '线索' },
  { id: 'hot', label: '高互动' },
  { id: 'watchlater', label: '稍后看' },
  { id: 'all', label: '全部' },
];

const VALID_SYSTEM_SCENARIOS = new Set<string>(SYSTEM_SCENARIO_TABS.map((tab) => tab.id));
const CUSTOM_SCENARIO_PATTERN = /^custom-[a-z0-9]{4,24}$/;

export function isCustomScenario(scenario: string): scenario is CustomIntelligenceScenario {
  return CUSTOM_SCENARIO_PATTERN.test(scenario);
}

export function isSystemScenario(scenario: string): scenario is SystemIntelligenceScenario {
  return VALID_SYSTEM_SCENARIOS.has(scenario);
}

export function createCustomScenarioId(): CustomIntelligenceScenario {
  const suffix =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID().replace(/-/g, '').slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `custom-${suffix}`;
}

export function parseScenarioFromSearch(search: string): IntelligenceScenario {
  const value = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search).get('scenario');
  if (value === 'in_library') return 'pending';
  if (value && (VALID_SYSTEM_SCENARIOS.has(value) || isCustomScenario(value))) {
    return value as IntelligenceScenario;
  }
  return 'pending';
}

function discoveredAfterDays(days: number): string {
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
}

export function systemDefaultScenarioFilters(scenario: IntelligenceScenario): ScenarioFilterState {
  if (isCustomScenario(scenario)) {
    return { filters: {}, rolling: {} };
  }
  switch (scenario) {
    case 'pending':
      return {
        filters: { in_reference_library: 'false', workflow_status: 'pending_review,assigned,selected' },
        rolling: { discovered_after_days: 7 },
      };
    case 'leads':
      return { filters: { candidate_bucket: 'lead_candidate' }, rolling: {} };
    case 'hot':
      return { filters: { min_like_count: HOT_ENGAGEMENT_MIN_LIKES }, rolling: {} };
    case 'watchlater':
      return {
        filters: {
          workflow_status: 'selected',
          in_reference_library: 'false',
          manual_tag: '稍后看',
        },
        rolling: {},
      };
    case 'all':
    default:
      return { filters: {}, rolling: {} };
  }
}

export function resolveScenarioFilters(state: ScenarioFilterState): IntelligenceFilters {
  const resolved: IntelligenceFilters = { ...state.filters };
  if (!resolved.discovered_after && state.rolling.discovered_after_days) {
    resolved.discovered_after = discoveredAfterDays(state.rolling.discovered_after_days);
  }
  return resolved;
}

/** 将滚动规则（如近 N 天）展开为面板可见的显式条件，保证查询与左侧配置一致。 */
export function materializeScenarioFilterState(state: ScenarioFilterState): ScenarioFilterState {
  const resolved = resolveScenarioFilters(state);
  const next = cloneScenarioFilterState(state);
  if (resolved.discovered_after && !next.filters.discovered_after) {
    next.filters.discovered_after = resolved.discovered_after;
    delete next.rolling.discovered_after_days;
  }
  return next;
}

export function buildActiveListFilters(
  advancedState: ScenarioFilterState,
  quickFilters: IntelligenceFilters,
  options: { contentQuery?: string; page: string; pageSize: string },
): IntelligenceFilters {
  const resolved = resolveScenarioFilters(materializeScenarioFilterState(advancedState));
  return {
    sort_by: 'latest_discovered_at',
    sort_order: 'desc',
    ...resolved,
    ...quickFilters,
    ...(options.contentQuery ? { content_query: options.contentQuery } : {}),
    page: options.page,
    page_size: options.pageSize,
  };
}

export function splitAdvancedFiltersForSave(state: ScenarioFilterState): ScenarioFilterState {
  const filters = { ...state.filters };
  const rolling = { ...state.rolling };
  if (filters.discovered_after) {
    delete rolling.discovered_after_days;
  } else if (rolling.discovered_after_days) {
    delete filters.discovered_after;
  }
  return { filters, rolling };
}

export function scenarioStateFromApi(item: SavedScenarioFilter): ScenarioFilterState {
  return {
    filters: { ...(item.filters || {}) },
    rolling: { ...(item.rolling || {}) },
  };
}

export const ADVANCED_INTELLIGENCE_FILTER_KEYS: Array<keyof IntelligenceFilters> = [
  'platform',
  'candidate_bucket',
  'workflow_status',
  'assigned_to_user_id',
  'business_keyword',
  'discovered_after',
  'discovered_before',
  'data_status',
  'tag',
  'platform_tag',
  'manual_tag',
  'search_sort',
  'note_type_filter',
  'publish_time_filter',
  'min_like_count',
  'min_comment_count',
  'min_collect_count',
  'in_reference_library',
  'reference_library_type',
  'selection_source',
  'reference_rating',
];

export function pickAdvancedFiltersFromParsed(parsed: IntelligenceFilters): Partial<IntelligenceFilters> {
  const picked: Partial<IntelligenceFilters> = {};
  ADVANCED_INTELLIGENCE_FILTER_KEYS.forEach((key) => {
    const value = parsed[key];
    if (value) picked[key] = value;
  });
  return picked;
}

export function mergeScenarioStateWithUrlOverlay(
  base: ScenarioFilterState,
  urlAdvanced: Partial<IntelligenceFilters>,
): ScenarioFilterState {
  if (Object.keys(urlAdvanced).length === 0) return base;
  const next: ScenarioFilterState = {
    filters: { ...base.filters, ...urlAdvanced },
    rolling: { ...base.rolling },
  };
  if (urlAdvanced.discovered_after) {
    delete next.rolling.discovered_after_days;
  }
  return next;
}

export function cloneScenarioFilterState(state: ScenarioFilterState): ScenarioFilterState {
  return {
    filters: { ...state.filters },
    rolling: { ...state.rolling },
  };
}

export function applyAdvancedFilterChange(
  state: ScenarioFilterState,
  key: keyof IntelligenceFilters,
  value: string,
): ScenarioFilterState {
  const next: ScenarioFilterState = {
    filters: { ...state.filters, [key]: value || undefined },
    rolling: { ...state.rolling },
  };
  if (key === 'discovered_after') {
    delete next.rolling.discovered_after_days;
  }
  return next;
}

export function listCustomScenarios(
  savedScenarioFilters: Partial<Record<IntelligenceScenario, ScenarioFilterState>>,
): Array<{ id: CustomIntelligenceScenario; label: string }> {
  return Object.entries(savedScenarioFilters)
    .filter(([id]) => isCustomScenario(id))
    .map(([id, state]) => ({
      id: id as CustomIntelligenceScenario,
      label: state?.rolling.label?.trim() || id,
    }))
    .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
}
