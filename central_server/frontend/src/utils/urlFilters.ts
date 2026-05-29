import type { IntelligenceFilters, ReferenceLibraryFilters } from '../api/intelligence';

const INTELLIGENCE_KEYS: (keyof IntelligenceFilters)[] = [
  'platform',
  'source_surface',
  'search_keyword',
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
  'sort_by',
  'sort_order',
];

const REFERENCE_KEYS: (keyof ReferenceLibraryFilters)[] = [
  'platform',
  'library_type',
  'selection_source',
  'rating',
  'usage_status',
  'sort_by',
  'sort_order',
];

function readRecord(params: URLSearchParams, keys: readonly string[]): Record<string, string> {
  const result: Record<string, string> = {};
  keys.forEach((key) => {
    const value = params.get(key);
    if (value) result[key] = value;
  });
  return result;
}

export function parseIntelligenceScenario(search: string): string | null {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  return params.get('scenario');
}

export function parseIntelligenceFilters(search: string, defaults: IntelligenceFilters = {}): IntelligenceFilters {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  return { ...defaults, ...readRecord(params, INTELLIGENCE_KEYS) };
}

export function serializeIntelligenceFilters(filters: IntelligenceFilters, extra?: Record<string, string>): URLSearchParams {
  const params = new URLSearchParams();
  INTELLIGENCE_KEYS.forEach((key) => {
    const value = filters[key];
    if (value) params.set(key, value);
  });
  if (extra) {
    Object.entries(extra).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
  }
  return params;
}

export function parseReferenceLibraryFilters(search: string, defaults: ReferenceLibraryFilters = {}): ReferenceLibraryFilters {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  return { ...defaults, ...readRecord(params, REFERENCE_KEYS) };
}

export function serializeReferenceLibraryFilters(filters: ReferenceLibraryFilters, extra?: Record<string, string>): URLSearchParams {
  const params = new URLSearchParams();
  REFERENCE_KEYS.forEach((key) => {
    const value = filters[key];
    if (value) params.set(key, value);
  });
  if (extra) {
    Object.entries(extra).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
  }
  return params;
}

export function replaceRouteSearch(path: string, params: URLSearchParams) {
  const qs = params.toString();
  const next = qs ? `${path}?${qs}` : path;
  window.history.replaceState({}, '', next);
}
