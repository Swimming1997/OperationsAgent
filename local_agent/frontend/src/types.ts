export type Platform = 'xhs' | 'douyin';

export interface ContentListItem {
  id: number;
  platform: Platform | string;
  title?: string | null;
  author_name?: string | null;
  cover_url?: string | null;
  like_count?: number | null;
  comment_count?: number | null;
  acquisition_hit_count?: number | null;
  processing_status?: string | null;
}

export interface ContentListResponse {
  items: ContentListItem[];
  total: number;
}

export interface CommentHit {
  matched_keyword: string;
  comment_text: string;
}

export interface CommentRow {
  platform_comment_id?: string;
  comment_text: string;
  comment_author?: string | null;
  like_count?: number | null;
  published_at?: string | null;
}

export interface SuggestItem {
  suggested_keyword: string;
  rank?: number | null;
}

export interface SuggestResponse {
  core_keyword: string;
  items: SuggestItem[];
}

export interface CommentSearchItem {
  id: number;
  content_id: number;
  comment_text: string;
  comment_author?: string | null;
  like_count?: number | null;
  published_at?: string | null;
  platform: string;
  content_title?: string | null;
  canonical_url?: string | null;
  content_author?: string | null;
}

export interface CommentSearchResponse {
  items: CommentSearchItem[];
  total: number;
}

export interface MaterialExport {
  status?: string;
  library_type?: string;
  rating?: string;
  material_tags?: string[];
  note?: string;
}

export interface ContentDetail extends ContentListItem {
  body_text?: string | null;
  image_urls?: string[];
  canonical_url?: string | null;
  detail_fetched_at?: string | null;
  comment_hits?: CommentHit[];
  comments?: CommentRow[];
  author_fans_count?: number | null;
  author_total_liked_collected?: number | null;
  author_works_count?: number | null;
  author_ip_location?: string | null;
  author_signature?: string | null;
  material_export?: MaterialExport | null;
}

export interface TaskRun {
  status: string;
  item_count?: number;
  error_summary_json?: string;
}

export interface TaskItem {
  id: number;
  task_type: string;
  target?: string | null;
  status: string;
  new_content_count?: number;
  latest_run?: TaskRun | null;
}

export interface TaskListResponse {
  items: TaskItem[];
}

export interface CentralUser {
  username?: string;
  display_name?: string;
}

export interface CentralSession {
  authenticated: boolean;
  center_url?: string;
  user?: CentralUser | null;
}

export interface PlatformAccount {
  id: string;
  platform: Platform | string;
  display_name: string;
  external_account_id?: string | null;
  account_role: string;
  status: string;
  auth_status: string;
  health_status: string;
  profile_key: string;
  cdp_port?: number | null;
  platform_nickname?: string | null;
  platform_home_url?: string | null;
  last_verified_at?: string | null;
  consecutive_failures?: number;
  metadata?: Record<string, unknown>;
}

export interface AccountListResponse {
  items: PlatformAccount[];
  total: number;
}
