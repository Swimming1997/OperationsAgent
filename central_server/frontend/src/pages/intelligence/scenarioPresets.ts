import type { IntelligenceFilters } from '../../api/intelligence';

export type IntelligenceScenario = 'pending' | 'leads' | 'hot' | 'in_library' | 'watchlater' | 'all';

export type ScenarioRollingConfig = {
  discovered_after_days?: number;
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

export const SCENARIO_TABS: Array<{ id: IntelligenceScenario; label: string }> = [
  { id: 'pending', label: '待处理' },
  { id: 'leads', label: '线索' },
  { id: 'hot', label: '高互动' },
  { id: 'watchlater', label: '稍后看' },
  { id: 'in_library', label: '已入库' },
  { id: 'all', label: '全部' },
];

const VALID_SCENARIOS = new Set<string>(SCENARIO_TABS.map((tab) => tab.id));

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

export function parseScenarioFromSearch(search: string): IntelligenceScenario {
  const value = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search).get('scenario');
  if (value && VALID_SCENARIOS.has(value)) {
    return value as IntelligenceScenario;
  }
  return 'pending';
}

function discoveredAfterDays(days: number): string {
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
}

export function systemDefaultScenarioFilters(scenario: IntelligenceScenario): ScenarioFilterState {
  switch (scenario) {
    case 'pending':
      return {
        filters: { in_reference_library: 'false' },
        rolling: { discovered_after_days: 7 },
      };
    case 'leads':
      return { filters: { candidate_bucket: 'lead_candidate' }, rolling: {} };
    case 'hot':
      return { filters: { min_like_count: HOT_ENGAGEMENT_MIN_LIKES }, rolling: {} };
    case 'in_library':
      return { filters: { in_reference_library: 'true' }, rolling: {} };
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
