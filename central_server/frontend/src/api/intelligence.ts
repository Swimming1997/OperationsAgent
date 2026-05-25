import { apiRequest } from './client';
import type {
  ContentNote,
  ContentWorkflow,
  DataQualityOverview,
  IntelligenceListResponse,
  ProductDetail,
  ReferenceLibraryItem,
  ReferenceLibraryListResponse,
  Role,
} from '../types/api';

export type IntelligenceFilters = {
  platform?: string;
  source_surface?: string;
  search_keyword?: string;
  candidate_bucket?: string;
  workflow_status?: string;
  assigned_to_user_id?: string;
  business_keyword?: string;
  discovered_after?: string;
  discovered_before?: string;
  data_status?: string;
  tag?: string;
  platform_tag?: string;
  manual_tag?: string;
  search_sort?: string;
  note_type_filter?: string;
  publish_time_filter?: string;
  min_like_count?: string;
  min_comment_count?: string;
  min_collect_count?: string;
  sort_by?: string;
  sort_order?: string;
};

function query(filters: Record<string, string | undefined>) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return params.toString();
}

export function fetchIntelligenceContents(role: Role, filters: IntelligenceFilters, userId?: string) {
  const qs = query(filters);
  return apiRequest<IntelligenceListResponse>(`/api/intelligence/contents/product${qs ? `?${qs}` : ''}`, { role, userId });
}

export function fetchDataQualityOverview(role: Role, userId?: string, windowHours = 24) {
  return apiRequest<DataQualityOverview>(`/api/intelligence/data-quality/overview?window_hours=${windowHours}`, { role, userId });
}

export function fetchReferenceLibraryItems(role: Role, filters: { library_type?: string; usage_status?: string } = {}, userId?: string) {
  const qs = query(filters);
  return apiRequest<ReferenceLibraryListResponse>(`/api/reference-library/items${qs ? `?${qs}` : ''}`, { role, userId });
}

export function fetchProductDetail(role: Role, contentId: string, userId?: string) {
  return apiRequest<ProductDetail>(`/api/intelligence/contents/${contentId}/product-detail`, { role, userId });
}

export function assignContent(role: Role, contentId: string, assignedToUserId: string, assignedByUserId?: string, userId?: string) {
  return apiRequest<ContentWorkflow>(`/api/intelligence/contents/${contentId}/assign`, {
    method: 'POST',
    role,
    userId,
    body: { assigned_to_user_id: assignedToUserId, assigned_by_user_id: assignedByUserId },
  });
}

export function setContentStatus(role: Role, contentId: string, action: 'select' | 'discard' | 'archive', note?: string, userId?: string) {
  return apiRequest<ContentWorkflow>(`/api/intelligence/contents/${contentId}/${action}`, {
    method: 'POST',
    role,
    userId,
    body: { user_id: userId || `${role}-user`, note },
  });
}

export function addContentNote(role: Role, contentId: string, note: string, userId?: string) {
  return apiRequest<ContentNote>(`/api/intelligence/contents/${contentId}/notes`, {
    method: 'POST',
    role,
    userId,
    body: { user_id: userId || `${role}-user`, note },
  });
}

export function updateManualTags(role: Role, contentId: string, manualTags: string[], userId?: string) {
  return apiRequest(`/api/intelligence/contents/${contentId}/manual-tags`, {
    method: 'PATCH',
    role,
    userId,
    body: { manual_tags: manualTags, user_id: userId || `${role}-user` },
  });
}

export function enqueueDetailFetch(role: Role, contentId: string, userId?: string) {
  return apiRequest<{ job_id: string; job_type: string; status: string }>(`/api/intelligence/contents/${contentId}/enqueue-detail-fetch`, {
    method: 'POST',
    role,
    userId,
  });
}

export function enqueueCommentFetch(role: Role, contentId: string, userId?: string) {
  return apiRequest<{ job_id: string; job_type: string; status: string }>(`/api/intelligence/contents/${contentId}/enqueue-comment-fetch`, {
    method: 'POST',
    role,
    userId,
  });
}

export function createReferenceLibraryItem(
  role: Role,
  contentId: string,
  payload: {
    library_type: string;
    selected_reason?: string;
    rating?: string;
    manual_tags?: string[];
    material_tags?: string[];
    note?: string;
  },
  userId?: string,
) {
  return apiRequest<ReferenceLibraryItem>(`/api/intelligence/contents/${contentId}/reference-library-items`, {
    method: 'POST',
    role,
    userId,
    body: { ...payload, user_id: userId || `${role}-user` },
  });
}
