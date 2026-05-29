import { apiRequest } from './client';
import type { Role } from '../types/api';
import type { IntelligenceScenario, SavedScenarioFilter, ScenarioFilterState } from '../pages/intelligence/scenarioPresets';

type ScenarioFilterListResponse = {
  items: SavedScenarioFilter[];
};

export function fetchMyScenarioFilters(role: Role, userId?: string) {
  return apiRequest<ScenarioFilterListResponse>('/api/product/me/intelligence/scenario-filters', {
    role,
    userId,
  });
}

export function saveMyScenarioFilters(
  role: Role,
  scenario: IntelligenceScenario,
  payload: ScenarioFilterState,
  userId?: string,
) {
  return apiRequest<SavedScenarioFilter>(`/api/product/me/intelligence/scenario-filters/${scenario}`, {
    role,
    userId,
    method: 'PUT',
    body: payload,
  });
}

export function deleteMyScenarioFilters(role: Role, scenario: IntelligenceScenario, userId?: string) {
  return apiRequest<void>(`/api/product/me/intelligence/scenario-filters/${scenario}`, {
    role,
    userId,
    method: 'DELETE',
  });
}
