export type ManualTag = {
  id: string;
  name: string;
  status: string;
  is_system: boolean;
  created_by_user_id: string | null;
  usage_count: number;
  created_at: string;
  updated_at: string;
  archived_at?: string | null;
  can_delete: boolean;
};

export type ManualTagListResponse = {
  items: ManualTag[];
};

export type Role = 'admin' | 'supervisor' | 'operator' | 'sales';

export type OptionItem = {
  value: string;
  label: string;
};

export type ProductOptions = {
  roles: OptionItem[];
  platforms: OptionItem[];
  feed_types: OptionItem[];
  task_template_types: OptionItem[];
  workflow_statuses: OptionItem[];
  candidate_buckets: OptionItem[];
  account_statuses: OptionItem[];
  agent_statuses: OptionItem[];
};

export type IntelligenceItem = {
  content_id: string;
  platform: string;
  platform_content_id: string;
  content_type: string;
  canonical_url: string | null;
  title: string | null;
  author_name: string | null;
  cover_url: string | null;
  cover_display_url: string | null;
  like_count: number | null;
  comment_count: number | null;
  collect_count: number | null;
  candidate_bucket: string | null;
  workflow_status: string;
  assigned_to_user_id: string | null;
  assigned_to_user_display_name: string | null;
  latest_operator_note: string | null;
  latest_snapshot_time: string | null;
  latest_discovered_at: string | null;
  discovery_sources_summary: Record<string, unknown>;
  first_seen_at: string;
  last_seen_at: string;
  data_status: string;
  discovery_count: number;
  discovered_account_count: number;
  discovered_search_keyword_count: number;
  platform_tags: string[];
  search_tags: string[];
  manual_tags: string[];
  search_keyword: string | null;
  search_sort: string | null;
  note_type_filter: string | null;
  publish_time_filter: string | null;
  search_scope_filter: string | null;
  location_filter: string | null;
  best_search_rank: number | null;
  best_feed_position: number | null;
  reference_library_count: number;
  in_reference_library: boolean;
  reference_library_type: string | null;
  reference_library_rating: string | null;
  reference_selection_sources: string[];
  reference_matched_keywords: string[];
  reference_ai_reason: string | null;
  reference_manual_locked: boolean;
};

export type ReferenceLibraryReevaluateResult = {
  content_id: string;
  item_id: string | null;
  status: string;
  library_type: string | null;
  rating: string | null;
  reason: string | null;
};

export type ReferenceLibraryReevaluateResponse = {
  results: ReferenceLibraryReevaluateResult[];
};

export type ReferenceLibraryItem = {
  id: string;
  content_id: string;
  platform?: string;
  library_type: string;
  status: string;
  created_by_user_id: string | null;
  created_by_employee_id: string | null;
  selected_reason: string | null;
  rating: string | null;
  selection_sources: string[];
  matched_keywords: string[];
  selected_at: string | null;
  manual_tags: string[];
  material_tags: string[];
  usage_status: string;
  note: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  title: string | null;
  author_name: string | null;
  cover_url: string | null;
  cover_display_url: string | null;
  like_count: number | null;
  comment_count: number | null;
  collect_count: number | null;
};

export type DataQualityOverview = {
  generated_at: string;
  window_hours: number;
  today_new_contents: number;
  today_card_count: number;
  today_detail_count: number;
  today_comment_count: number;
  today_reference_library_count: number;
  detail_fetch_success_rate: number | null;
  comment_fetch_success_rate: number | null;
  search_context_completeness_rate: number;
  platform_tags_coverage_rate: number;
  multi_discovery_content_count: number;
  abnormal_account_count: number;
  runaway_detail_fetch_risk: boolean;
  filter_context_note: string;
};

export type ReferenceLibraryListResponse = {
  items: ReferenceLibraryItem[];
  page: number;
  page_size: number;
  total: number;
};

export type ReferenceLibraryEvent = {
  id: string;
  library_item_id: string;
  content_id: string;
  event_type: string;
  user_id: string | null;
  employee_id: string | null;
  event_payload: Record<string, unknown>;
  created_at: string;
};

export type ReferenceLibraryBulkResponse = {
  succeeded: ReferenceLibraryItem[];
  failed: Array<{ content_id: string; code: string; message: string }>;
};

export type IntelligenceListResponse = {
  items: IntelligenceItem[];
  page: number;
  page_size: number;
  total: number;
};

export type ContentWorkflow = {
  content_id: string;
  workflow_status: string;
  assigned_to_user_id: string | null;
  assigned_by_user_id: string | null;
  assigned_at: string | null;
  reviewed_at: string | null;
  selected_at: string | null;
  discarded_at: string | null;
  latest_operator_note: string | null;
};

export type ContentNote = {
  id: string;
  content_id: string;
  user_id: string | null;
  note: string;
  created_at: string;
};

export type ProductDetail = {
  identity: {
    id: string;
    platform: string;
    platform_content_id: string;
    canonical_url: string | null;
    content_type: string;
    first_seen_at: string;
    last_seen_at: string;
    metadata: Record<string, unknown>;
  };
  latest_snapshot: null | {
    id: string;
    title: string | null;
    body_text: string | null;
    author_name: string | null;
    cover_url: string | null;
    cover_display_url: string | null;
    like_count: number | null;
    comment_count: number | null;
    collect_count: number | null;
    fetched_at: string;
  };
  comments: {
    id: string;
    platform_comment_id: string;
    parent_platform_comment_id: string | null;
    author_platform_id: string | null;
    author_name: string | null;
    body_text: string;
    like_count: number | null;
    created_time: string | null;
    fetched_at: string;
  }[];
  latest_candidate_decision: null | {
    id: string;
    candidate_bucket: string;
    business_keyword_hits: string[];
    lead_keyword_hits: string[];
    comment_keyword_hits: string[];
    decision_reason: Record<string, unknown>;
    evaluated_at: string;
  };
  workflow_state: ContentWorkflow;
  notes: ContentNote[];
  assignment_history: Array<{
    id: string;
    assigned_to_user_id: string;
    assigned_by_user_id: string | null;
    assigned_at: string;
    status: string;
    remark: string | null;
  }>;
  discovery_events_summary: Array<{
    id: string;
    source_surface: string;
    feed_type: string | null;
    feed_position: number | null;
    discovered_at: string;
    account_id: string | null;
    job_id: string | null;
    search_keyword?: string | null;
    search_keywords?: string[];
  }>;
  reference_library_items: ReferenceLibraryItem[];
  platform_tags: string[];
  search_tags: string[];
  manual_tags: string[];
  data_status: string;
  pending_detail_job_id: string | null;
  pending_comment_job_id: string | null;
};

export type TaskTemplatePermissions = {
  can_edit: boolean;
  can_run: boolean;
  can_schedule: boolean;
  can_delete: boolean;
};

export type TaskTemplateListItem = {
  id: string;
  name: string;
  template_type: string;
  enabled: boolean;
  platform: string | null;
  business_account_type_id: string | null;
  business_account_type_name: string | null;
  created_by_user_id: string | null;
  created_by_display_name: string | null;
  key_fields: Record<string, unknown>;
  permissions: TaskTemplatePermissions;
};

export type TaskTemplateDetail = {
  id: string;
  name: string;
  template_type: string;
  platform: string | null;
  account_id: string | null;
  business_account_type_id: string | null;
  config: Record<string, unknown>;
  enabled: boolean;
  typed_payload: Record<string, unknown>;
};

export type TaskSchedule = {
  id: string;
  task_template_id: string;
  executor_account_id: string | null;
  created_by_user_id: string | null;
  schedule_type: string;
  interval_seconds: number | null;
  daily_time_window: Record<string, unknown>;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  last_materialized_at: string | null;
};

export type TaskRunResponse = {
  task_run_id: string;
  task_template_id: string | null;
  jobs_created: number;
  jobs: Array<{
    job_id: string;
    job_type: string;
    status: string;
  }>;
  readiness: TaskTemplateReadiness;
};

export type ReadinessCheck = {
  key: string;
  ok: boolean;
  message: string;
};

export type TaskTemplateReadiness = {
  ready: boolean;
  checks: ReadinessCheck[];
  messages: string[];
};

export type TaskRunJob = {
  job_id: string;
  job_type: string;
  status: string;
  account_id: string | null;
  claimed_by_agent_id: string | null;
  result_summary: Record<string, unknown>;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type TaskRunQueueContext = {
  waiting_reason: string;
  message: string;
  pending_jobs_ahead: number;
  job_priority?: number | null;
  agent_running_job_id?: string | null;
  agent_running_job_type?: string | null;
  agent_running_since?: string | null;
};

export type TaskRun = {
  id: string;
  task_template_id: string | null;
  trigger_type: string;
  requested_by_user_id: string | null;
  task_schedule_id: string | null;
  status: string;
  jobs_total: number;
  jobs_pending: number;
  jobs_running: number;
  jobs_success: number;
  jobs_failed: number;
  result_summary: Record<string, unknown>;
  error_summary: Record<string, unknown>;
  jobs: TaskRunJob[];
  queue_context?: TaskRunQueueContext | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
};

export type TaskRunListResponse = {
  items: TaskRun[];
};

export type Employee = {
  id: string;
  user_id: string | null;
  user_username?: string | null;
  display_name: string;
  email: string | null;
  status: string;
};

export type PlatformAccount = {
  id: string;
  employee_id: string | null;
  employee_display_name: string | null;
  platform: string;
  display_name: string;
  external_account_id: string | null;
  business_account_type_id: string | null;
  business_account_type_name: string | null;
  legacy_business_account_type: string | null;
  status: string;
  auth_status: string;
  account_role: string;
  health_status: string;
  profile_key: string | null;
  platform_nickname: string | null;
  platform_home_url: string | null;
  last_verified_at: string | null;
  login_cdp_port: number | null;
  default_agent_id?: string | null;
  default_agent_device_name?: string | null;
  bindings?: AccountAgentBinding[];
  session_health_status: string | null;
  active_login_session_status: string | null;
  usage_status: string;
  last_success_at: string | null;
  last_failure_at: string | null;
  consecutive_failures: number;
  metadata: Record<string, unknown>;
};

export type AccountAgentBinding = {
  id: string;
  account_id: string;
  agent_id: string;
  employee_id: string | null;
  agent_device_name: string | null;
  agent_status: string | null;
  enabled: boolean;
  session_status: string | null;
  last_claimed_at: string | null;
};

export type LocalBridgeSessionStatus = {
  account_id: string;
  status: string;
  message: string | null;
  cdp_url: string | null;
  platform_nickname: string | null;
  platform_home_url: string | null;
};

export type LocalBridgeStartResult = {
  account_id: string | null;
  profile_key: string;
  profile_dir: string;
  cdp_url: string;
  pid: number;
  message: string;
};

export type LocalBridgeDiscoveredAgent = {
  device_name: string;
  machine_fingerprint: string;
  agent_id: string | null;
  center_url?: string | null;
  bridge_url?: string | null;
  bridge_port: number;
  status: string;
};

export type AccountLoginSession = {
  id: string;
  platform_account_id: string;
  agent_id: string | null;
  status: string;
  error_message: string | null;
  profile_key: string;
  cdp_port: number | null;
  claimed_by_agent_id: string | null;
  started_at: string;
  finished_at: string | null;
  expires_at: string | null;
};

export type BusinessAccountType = {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  rule_set_count: number;
  benchmark_group_count: number;
};

export type LocalAgent = {
  id: string;
  employee_id: string | null;
  employee_display_name: string | null;
  device_name: string | null;
  machine_fingerprint: string | null;
  status: string;
  agent_version: string | null;
  capabilities: Record<string, unknown>;
  last_heartbeat_at: string | null;
};

export type BenchmarkGroup = {
  id: string;
  name: string;
  description: string | null;
  owner_employee_id: string | null;
  submitter_user_id: string | null;
  submitter_employee_id: string | null;
  submitter_name: string | null;
  enabled: boolean;
  metadata: Record<string, unknown>;
};

export type BenchmarkGroupMember = {
  id: string;
  benchmark_group_id: string;
  creator_monitor_id: string | null;
  platform: string;
  creator_platform_id: string | null;
  creator_profile_url: string | null;
  display_name: string | null;
  platform_context: Record<string, unknown>;
  enabled: boolean;
};

export type BenchmarkGroupBusinessType = {
  id: string;
  benchmark_group_id: string;
  business_account_type_id: string;
  business_account_type_name: string | null;
};

export type KeywordRuleSet = {
  id: string;
  name: string;
  rule_scope: string;
  enabled: boolean;
  created_by_user_id: string | null;
  created_by_employee_id: string | null;
  submitter_name: string | null;
  config: Record<string, unknown>;
};

export type KeywordRule = {
  id: string;
  rule_set_id: string;
  keyword: string;
  normalized_keyword: string | null;
  match_mode: string;
  enabled: boolean;
  weight: number;
};

export type OperationRule = {
  id: string;
  rule_type: string;
  title: string;
  content: string;
  platform: string | null;
  enabled: boolean;
  version: number;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
};

export type BusinessAccountTypeRuleSet = {
  id: string;
  business_account_type_id: string;
  rule_set_id: string;
  rule_set_name: string | null;
  is_default: boolean;
};

export type BusinessAccountTypeBenchmarkGroup = {
  id: string;
  business_account_type_id: string;
  benchmark_group_id: string;
  benchmark_group_name: string | null;
};

export type BehaviorProfile = {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  config: Record<string, unknown>;
};

export type NetworkEgressProfile = {
  id: string;
  name: string;
  strategy: string;
  description: string | null;
  enabled: boolean;
  config: Record<string, unknown>;
};

export type RiskPolicy = {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  behavior_profile_id: string | null;
  network_egress_profile_id: string | null;
  config: Record<string, unknown>;
};

export type ApiError = Error & {
  status?: number;
  detail?: unknown;
};
