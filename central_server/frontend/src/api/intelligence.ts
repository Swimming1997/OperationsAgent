import { apiRequest } from './client';
import type {
  ContentNote,
  ContentWorkflow,
  DataQualityOverview,
  IntelligenceListResponse,
  ManualTag,
  ManualTagListResponse,
  ProductDetail,
  ReferenceLibraryBulkResponse,
  ReferenceLibraryEvent,
  ReferenceLibraryItem,
  ReferenceLibraryListResponse,
  ReferenceLibraryReevaluateResponse,
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
  content_query?: string;
  discovered_after?: string;
  discovered_before?: string;
  data_status?: string;
  tag?: string;
  platform_tag?: string;
  manual_tag?: string;
  manual_tag_id?: string;
  untagged?: string;
  search_sort?: string;
  note_type_filter?: string;
  publish_time_filter?: string;
  min_like_count?: string;
  min_comment_count?: string;
  min_collect_count?: string;
  in_reference_library?: string;
  reference_library_type?: string;
  selection_source?: string;
  reference_rating?: string;
  sort_by?: string;
  sort_order?: string;
  page?: string;
  page_size?: string;
};

export type ReferenceLibraryFilters = {
  library_type?: string;
  platform?: string;
  selection_source?: string;
  rating?: string;
  usage_status?: string;
  search_keyword?: string;
  content_query?: string;
  manual_tag_id?: string;
  untagged?: string;
  sort_by?: string;
  sort_order?: string;
  page?: string;
  page_size?: string;
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

export function fetchReferenceLibraryItems(role: Role, filters: ReferenceLibraryFilters = {}, userId?: string) {
  const qs = query(filters);
  return apiRequest<ReferenceLibraryListResponse>(`/api/reference-library/items${qs ? `?${qs}` : ''}`, { role, userId });
}

export function fetchReferenceLibraryEvents(role: Role, itemId: string, userId?: string) {
  return apiRequest<ReferenceLibraryEvent[]>(`/api/reference-library/items/${itemId}/events`, { role, userId });
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

export function bulkSetContentStatus(
  role: Role,
  payload: { content_ids: string[]; action: 'select' | 'discard' | 'archive'; note?: string },
  userId?: string,
) {
  return apiRequest<{ succeeded: ContentWorkflow[]; failed: Array<{ content_id: string; code: string; message: string }> }>(
    '/api/intelligence/contents/bulk-status',
    {
      method: 'POST',
      role,
      userId,
      body: { ...payload, user_id: userId || `${role}-user` },
    },
  );
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

export function updateContentManualTagIds(role: Role, contentId: string, tagIds: string[], userId?: string) {
  return apiRequest(`/api/intelligence/contents/${contentId}/manual-tags`, {
    method: 'PATCH',
    role,
    userId,
    body: { tag_ids: tagIds, user_id: userId || `${role}-user` },
  });
}

export function fetchManualTags(role: Role, userId?: string, includeArchived = false) {
  const qs = includeArchived ? '?include_archived=true' : '';
  return apiRequest<ManualTagListResponse>(`/api/manual-tags${qs}`, { role, userId });
}

export function createManualTag(role: Role, name: string, userId?: string) {
  return apiRequest<ManualTag>('/api/manual-tags', {
    method: 'POST',
    role,
    userId,
    body: { name },
  });
}

export function deleteManualTag(role: Role, tagId: string, userId?: string) {
  return apiRequest(`/api/manual-tags/${tagId}`, { method: 'DELETE', role, userId });
}

export function archiveManualTag(role: Role, tagId: string, userId?: string) {
  return apiRequest<ManualTag>(`/api/manual-tags/${tagId}/archive`, { method: 'POST', role, userId });
}

export function restoreManualTag(role: Role, tagId: string, userId?: string) {
  return apiRequest<ManualTag>(`/api/manual-tags/${tagId}/restore`, { method: 'POST', role, userId });
}

export function hardDeleteManualTag(role: Role, tagId: string, userId?: string) {
  return apiRequest(`/api/manual-tags/${tagId}/hard`, { method: 'DELETE', role, userId });
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
    selection_sources?: string[];
    selected_reason?: string;
    rating?: string;
    matched_keywords?: string[];
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

export function bulkCreateReferenceLibraryItems(
  role: Role,
  items: Array<{
    content_id: string;
    library_type: string;
    selected_reason?: string;
    rating?: string;
    manual_tags?: string[];
    note?: string;
  }>,
  userId?: string,
) {
  return apiRequest<ReferenceLibraryBulkResponse>('/api/reference-library/items/bulk', {
    method: 'POST',
    role,
    userId,
    body: { items },
  });
}

export function updateReferenceLibraryItem(
  role: Role,
  itemId: string,
  payload: {
    library_type?: string;
    rating?: string;
    manual_tags?: string[];
    material_tags?: string[];
    note?: string;
    selected_reason?: string;
  },
  userId?: string,
) {
  return apiRequest<ReferenceLibraryItem>(`/api/reference-library/items/${itemId}`, {
    method: 'PATCH',
    role,
    userId,
    body: { ...payload, user_id: userId || `${role}-user` },
  });
}

export function prepareReferenceLibraryCreativeMaterial(
  role: Role,
  itemId: string,
  payload: {
    reusable_angles?: string[];
    selling_points?: string[];
    pain_points?: string[];
    risk_notes?: string[];
    applicable_business_type_ids?: string[];
    operator_note?: string;
    material_tags?: string[];
  },
  userId?: string,
) {
  return apiRequest<ReferenceLibraryItem>(`/api/reference-library/items/${itemId}/creative-material`, {
    method: 'POST',
    role,
    userId,
    body: payload,
  });
}

export function archiveReferenceLibraryItem(role: Role, itemId: string, userId?: string) {
  return apiRequest<ReferenceLibraryItem>(`/api/reference-library/items/${itemId}/archive`, {
    method: 'POST',
    role,
    userId,
  });
}

export function revokeReferenceLibraryItem(role: Role, itemId: string, userId?: string) {
  return apiRequest<ReferenceLibraryItem>(`/api/reference-library/items/${itemId}/revoke`, {
    method: 'POST',
    role,
    userId,
  });
}

export function reEvaluateReferenceLibraryItems(
  role: Role,
  payload: { content_ids?: string[]; item_ids?: string[]; trigger_source?: string },
  userId?: string,
) {
  return apiRequest<ReferenceLibraryReevaluateResponse>('/api/reference-library/items/re-evaluate', {
    method: 'POST',
    role,
    userId,
    body: {
      content_ids: payload.content_ids ?? [],
      item_ids: payload.item_ids ?? [],
      trigger_source: payload.trigger_source ?? 'manual_re_evaluate',
    },
  });
}
