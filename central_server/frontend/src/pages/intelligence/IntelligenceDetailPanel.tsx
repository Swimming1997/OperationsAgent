import {
  Archive,
  Bookmark,
  Check,
  ExternalLink,
  FilePlus2,
  Heart,
  Library,
  MessageCircle,
  RefreshCw,
  Scale,
  Send,
  Trash2,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { listEmployees } from '../../api/resources';
import {
  canReevaluateReference,
  ReferenceRuleExplainSummary,
  ReevaluateResultPanel,
  type ReferenceExplainSnapshot,
} from '../../components/ReferenceRuleExplain';
import { SafeImage } from '../../components/SafeImage';
import { coverSrc } from '../../utils/mediaUrl';
import { EmptyState, ErrorState, LoadingState } from '../../components/Status';
import type {
  Employee,
  IntelligenceItem,
  ProductDetail,
  ReferenceLibraryReevaluateResult,
  Role,
} from '../../types/api';
import {
  deriveContentStatusBadge,
  formatDiscoveryPosition,
  formatTags,
  labelCandidateBucket,
  labelDataStatus,
  labelPlatform,
  labelReferenceLibraryRating,
  labelReferenceLibraryType,
  labelSourceSurface,
} from '../../utils/intelligenceLabels';
import { formatMetric } from '../../utils/formatMetric';
const LIBRARY_TYPE_OPTIONS = [
  { value: 'lead', label: '获客库' },
  { value: 'non_lead', label: '非获客库' },
  { value: 'uncategorized', label: '待分类' },
];

const RATING_OPTIONS = [
  { value: 'watching', label: '待观察' },
  { value: 'poor', label: '差' },
  { value: 'medium', label: '中' },
  { value: 'good', label: '好' },
];

function defaultLibraryTypeForBucket(bucket: string | null | undefined): 'lead' | 'non_lead' | 'uncategorized' {
  if (bucket === 'lead_candidate') return 'lead';
  if (bucket === 'content_candidate') return 'non_lead';
  return 'uncategorized';
}

function compactSignals(values: Array<string | null | undefined>, fallback = '暂无命中词') {
  const unique = [...new Set(values.filter(Boolean).map(String))];
  return unique.length ? unique.slice(0, 6).join(' / ') : fallback;
}

function formatCommentTime(value: string | null | undefined) {
  if (!value) return '';
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

type Props = {
  role: Role;
  userId: string;
  selected: IntelligenceItem | null;
  detail: ProductDetail | null;
  loading: boolean;
  feedback: string;
  reevaluating: boolean;
  reevaluateResults: ReferenceLibraryReevaluateResult[];
  explainSnapshot: ReferenceExplainSnapshot;
  onAddToLibrary: (libraryType: 'lead' | 'non_lead' | 'uncategorized', reason?: string) => Promise<void>;
  onWatchLater: () => Promise<void>;
  onDiscard: () => Promise<void>;
  onArchive: () => Promise<void>;
  onOpenReferenceLibrary: (contentId: string, itemId?: string) => void;
  onEnqueueDetail: () => Promise<void>;
  onEnqueueComment: () => Promise<void>;
  onSaveManualTags: (tags: string[]) => Promise<void>;
  onAssign: (assigneeUserId: string) => Promise<void>;
  onAddNote: (note: string) => Promise<void>;
  onCustomLibrary: (payload: {
    library_type: string;
    rating: string;
    selected_reason?: string;
    manual_tags?: string[];
  }) => Promise<void>;
  onReevaluate: () => Promise<void>;
  onClearReevaluateResults: () => void;
  onApplyTagFilter: (tag: string) => void;
  onOpenOperationsJob?: () => void;
};

export function IntelligenceDetailPanel({
  role,
  userId,
  selected,
  detail,
  loading,
  feedback,
  reevaluating,
  reevaluateResults,
  explainSnapshot,
  onAddToLibrary,
  onWatchLater,
  onDiscard,
  onArchive,
  onOpenReferenceLibrary,
  onEnqueueDetail,
  onEnqueueComment,
  onSaveManualTags,
  onAssign,
  onAddNote,
  onCustomLibrary,
  onReevaluate,
  onClearReevaluateResults,
  onApplyTagFilter,
  onOpenOperationsJob,
}: Props) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);
  const [libraryDecisionOpen, setLibraryDecisionOpen] = useState(false);
  const [decisionLibraryType, setDecisionLibraryType] = useState<'lead' | 'non_lead' | 'uncategorized'>('non_lead');
  const [inlineReason, setInlineReason] = useState('');
  const [manualTagInput, setManualTagInput] = useState('');
  const [note, setNote] = useState('');
  const [assignee, setAssignee] = useState(userId);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [libraryType, setLibraryType] = useState('uncategorized');
  const [libraryRating, setLibraryRating] = useState('watching');
  const [libraryReason, setLibraryReason] = useState('');
  const [submittingFetch, setSubmittingFetch] = useState<'detail' | 'comment' | null>(null);

  const canReevaluate = canReevaluateReference(role);
  const canAssign = role === 'admin' || role === 'supervisor';
  const inLibrary = Boolean(selected?.in_reference_library);
  const refItem = detail?.reference_library_items?.[0];
  const badge = selected ? deriveContentStatusBadge(selected) : null;
  const hasSuccessfulDetailFetch = detail?.data_status === 'detail_ready' || detail?.data_status === 'comments_ready';
  const hasSuccessfulCommentFetch = detail?.data_status === 'comments_ready' || Boolean(detail?.comments.length);

  useEffect(() => {
    listEmployees(role, userId)
      .then(setEmployees)
      .catch(() => setEmployees([]));
  }, [role, userId]);

  useEffect(() => {
    if (detail) {
      setManualTagInput((detail.manual_tags || []).join(', '));
    }
  }, [detail?.identity.id, detail?.manual_tags]);

  useEffect(() => {
    setDecisionLibraryType(defaultLibraryTypeForBucket(detail?.latest_candidate_decision?.candidate_bucket || selected?.candidate_bucket));
    setLibraryDecisionOpen(false);
    setInlineReason('');
  }, [detail?.identity.id, detail?.latest_candidate_decision?.candidate_bucket, selected?.candidate_bucket]);

  const assignableEmployees = useMemo(
    () => employees.filter((item) => item.user_id),
    [employees],
  );

  const discoveryLine = useMemo(() => {
    if (!selected) return '-';
    const position = formatDiscoveryPosition(selected);
    const time = selected.latest_discovered_at
      ? new Date(selected.latest_discovered_at).toLocaleString('zh-CN', { hour12: false })
      : null;
    return time ? `${position} · ${time}` : position;
  }, [selected]);

  const insight = useMemo(() => {
    const decision = detail?.latest_candidate_decision;
    const keywordText = compactSignals([
      ...(decision?.lead_keyword_hits || []),
      ...(decision?.comment_keyword_hits || []),
      ...(decision?.business_keyword_hits || []),
      ...(selected?.search_tags || []),
    ]);
    return {
      bucket: labelCandidateBucket(decision?.candidate_bucket || selected?.candidate_bucket),
      keywords: keywordText,
      source: discoveryLine,
    };
  }, [detail?.latest_candidate_decision, discoveryLine, selected?.candidate_bucket, selected?.search_tags]);

  if (loading) {
    return (
      <aside className="detail-panel">
        <div className="panel-title">内容详情</div>
        <LoadingState text="详情加载中" />
      </aside>
    );
  }

  if (!selected) {
    return (
      <aside className="detail-panel">
        <div className="panel-title">内容详情</div>
        <EmptyState text="选择一条情报查看详情" />
      </aside>
    );
  }

  if (!detail) {
    return (
      <aside className="detail-panel">
        <div className="panel-title">内容详情</div>
        <ErrorState text="详情尚未加载" />
      </aside>
    );
  }

  async function confirmDiscard() {
    if (!window.confirm('确定标记为「不合适」？')) return;
    await onDiscard();
  }

  async function submitLibraryDecision() {
    await onAddToLibrary(decisionLibraryType, inlineReason.trim() || undefined);
    setLibraryDecisionOpen(false);
    setInlineReason('');
  }

  async function submitDetailFetch() {
    setSubmittingFetch('detail');
    try {
      await onEnqueueDetail();
    } finally {
      setSubmittingFetch(null);
    }
  }

  async function submitCommentFetch() {
    setSubmittingFetch('comment');
    try {
      await onEnqueueComment();
    } finally {
      setSubmittingFetch(null);
    }
  }

  return (
    <aside className="detail-panel">
      <div className="detail-top-bar">
        <div className="panel-title">内容详情</div>
        <button type="button" className="secondary detail-more-button" onClick={() => setMoreOpen((value) => !value)}>
          {moreOpen ? '收起更多' : '更多操作'}
        </button>
      </div>
      <div className="detail-body">
        {moreOpen && (
          <div className="more-panel detail-more-menu" data-testid="intelligence-more-panel">
            <div className="action-strip">
              <button
                type="button"
                onClick={() => void submitDetailFetch()}
                disabled={Boolean(detail.pending_detail_job_id) || submittingFetch !== null}
              >
                <RefreshCw size={14} />
                {submittingFetch === 'detail' ? '提交中…' : hasSuccessfulDetailFetch ? '重采详情' : '补采详情'}
              </button>
              <button
                type="button"
                onClick={() => void submitCommentFetch()}
                disabled={Boolean(detail.pending_comment_job_id) || submittingFetch !== null}
              >
                <RefreshCw size={14} />
                {submittingFetch === 'comment' ? '提交中…' : hasSuccessfulCommentFetch ? '重采评论' : '补采评论'}
              </button>
            </div>
            {(detail.pending_detail_job_id || detail.pending_comment_job_id) && (
              <div className="feedback">
                {detail.pending_detail_job_id ? `详情补采排队中：${detail.pending_detail_job_id}` : ''}
                {detail.pending_comment_job_id ? `评论补采排队中：${detail.pending_comment_job_id}` : ''}
              </div>
            )}

            <div className="detail-section">
              <b>标签</b>
              <span>运营：{formatTags(detail.manual_tags)}</span>
              {(detail.manual_tags || []).map((tag) => (
                <button key={tag} type="button" className="tag-button" onClick={() => onApplyTagFilter(tag)}>
                  {tag}
                </button>
              ))}
            </div>

            <div className="detail-section">
              <b>运营标签</b>
              <input
                value={manualTagInput}
                onChange={(event) => setManualTagInput(event.target.value)}
                placeholder="逗号分隔，如：可仿写, 求助"
              />
              <button
                type="button"
                onClick={() =>
                  onSaveManualTags(
                    manualTagInput
                      .split(/[,，]/)
                      .map((item) => item.trim())
                      .filter(Boolean),
                  )
                }
              >
                <FilePlus2 size={14} />
                保存标签
              </button>
            </div>

            {canAssign && (
              <div className="detail-section">
                <b>分配负责人</b>
                <select value={assignee} onChange={(event) => setAssignee(event.target.value)}>
                  {assignableEmployees.map((item) => (
                    <option key={item.id} value={item.user_id || ''} disabled={!item.user_id}>
                      {item.display_name}
                    </option>
                  ))}
                </select>
                <button type="button" onClick={() => onAssign(assignee)}>
                  <Send size={14} />
                  分配
                </button>
              </div>
            )}

            <div className="detail-section">
              <b>发现记录</b>
              {detail.discovery_events_summary.map((event) => (
                <span key={event.id}>
                  {labelSourceSurface(event.source_surface)}
                  {event.search_keyword ? ` · 关键词 ${event.search_keyword}` : ''}
                  {' · '}
                  {new Date(event.discovered_at).toLocaleString('zh-CN', { hour12: false })}
                </span>
              ))}
            </div>

            <div className="decision-block">
              <b>候选判断</b>
              <span>{labelCandidateBucket(detail.latest_candidate_decision?.candidate_bucket)}</span>
              <span className="muted-hint">数据层：{labelDataStatus(detail.data_status)}</span>
            </div>

            {canReevaluate && (
              <>
                <ReferenceRuleExplainSummary snapshot={explainSnapshot} />
                <div className="action-strip">
                  <button
                    type="button"
                    data-testid="reevaluate-current-btn"
                    disabled={reevaluating}
                    onClick={onReevaluate}
                  >
                    <Scale size={14} />
                    规则重评
                  </button>
                </div>
                <ReevaluateResultPanel results={reevaluateResults} onClear={onClearReevaluateResults} />
              </>
            )}

            <div className="action-strip">
              <button type="button" className="secondary" onClick={onArchive}>
                <Archive size={14} />
                归档
              </button>
            </div>

            <button type="button" className="secondary linkish" onClick={() => setCustomOpen((value) => !value)}>
              {customOpen ? '收起高级入库' : '高级入库'}
            </button>
            {customOpen && !inLibrary && (
              <div className="detail-section">
                <select value={libraryType} onChange={(event) => setLibraryType(event.target.value)}>
                  {LIBRARY_TYPE_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <input
                  value={libraryReason}
                  onChange={(event) => setLibraryReason(event.target.value)}
                  placeholder="入库原因"
                />
                <select value={libraryRating} onChange={(event) => setLibraryRating(event.target.value)}>
                  {RATING_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() =>
                    onCustomLibrary({
                      library_type: libraryType,
                      rating: libraryRating,
                      selected_reason: libraryReason || undefined,
                      manual_tags: manualTagInput
                        .split(/[,，]/)
                        .map((item) => item.trim())
                        .filter(Boolean),
                    })
                  }
                >
                  <Library size={14} />
                  高级入库
                </button>
              </div>
            )}

            <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="添加处理备注" />
            <button type="button" onClick={() => note.trim() && onAddNote(note.trim())}>
              <FilePlus2 size={14} />
              添加备注
            </button>
          </div>
        )}

        <article className="xhs-note-detail">
          <div className="xhs-author-row">
            <div className="xhs-avatar" aria-hidden="true">
              {(detail.latest_snapshot?.author_name || selected.author_name || '?').slice(0, 1)}
            </div>
            <div className="xhs-author-meta">
              <b>{detail.latest_snapshot?.author_name || selected.author_name || '未知作者'}</b>
              <span>
                {labelPlatform(detail.identity.platform)}
                {badge ? ` · ${badge.label}` : ''}
              </span>
            </div>
            {badge ? <b className={`tag status-badge status-${badge.tone}`}>{badge.label}</b> : null}
          </div>

          <SafeImage src={coverSrc(detail.latest_snapshot) ?? coverSrc(selected)} className="detail-cover xhs-note-cover" placeholderClassName="detail-cover-placeholder xhs-note-cover-placeholder" />

          <div className="xhs-note-copy">
            <div className="detail-title">{detail.latest_snapshot?.title || selected.title || '未命名内容'}</div>
            <p className="body-text">{detail.latest_snapshot?.body_text || '暂无正文快照'}</p>
            {(detail.platform_tags.length > 0 || detail.search_tags.length > 0 || detail.manual_tags.length > 0) && (
              <div className="xhs-tag-cloud" aria-label="内容标签">
                {[
                  ...detail.platform_tags.map((tag) => ({ tag, type: '平台' })),
                  ...detail.search_tags.map((tag) => ({ tag, type: '搜索' })),
                  ...detail.manual_tags.map((tag) => ({ tag, type: '运营' })),
                ].map((item) => (
                  <button
                    key={`${item.type}-${item.tag}`}
                    type="button"
                    className="xhs-content-tag"
                    onClick={() => onApplyTagFilter(item.tag)}
                    title={`${item.type}标签`}
                  >
                    #{item.tag}
                  </button>
                ))}
              </div>
            )}
          </div>

          <dl className="xhs-engagement-bar">
            <div>
              <dt><Heart size={15} />点赞</dt>
              <dd>{formatMetric(detail.latest_snapshot?.like_count)}</dd>
            </div>
            <div>
              <dt><MessageCircle size={15} />评论</dt>
              <dd>{formatMetric(detail.latest_snapshot?.comment_count)}</dd>
            </div>
            <div>
              <dt><Bookmark size={15} />收藏</dt>
              <dd>{formatMetric(detail.latest_snapshot?.collect_count)}</dd>
            </div>
            <div>
              <dt>发现</dt>
              <dd>{selected.discovery_count}</dd>
            </div>
          </dl>

          <div className="detail-section comment-preview-section xhs-comment-section">
            <b>评论内容</b>
            {detail.comments.length > 0 ? (
              <div className="comment-preview-list">
                {detail.comments.map((comment) => (
                  <div key={comment.id} className="comment-preview-item xhs-comment-item">
                    <div className="comment-preview-meta">
                      <span>{comment.author_name || '匿名用户'}</span>
                      <span>{formatCommentTime(comment.created_time || comment.fetched_at)}</span>
                      {typeof comment.like_count === 'number' ? <span>{comment.like_count} 赞</span> : null}
                    </div>
                    <p>{comment.body_text}</p>
                  </div>
                ))}
              </div>
            ) : (
              <span className="muted-hint">
                {detail.pending_comment_job_id ? '评论补采正在排队或执行中，完成后刷新详情可查看。' : '暂无评论快照，可在更多操作里补采评论。'}
              </span>
            )}
          </div>

          <div className="decision-summary xhs-insight-strip">
            <div>
              <b>发现位置</b>
              <span>{discoveryLine}</span>
            </div>
            <div>
              <b>推荐判断</b>
              <span>{insight.bucket}</span>
            </div>
            <div>
              <b>命中信号</b>
              <span>{insight.keywords}</span>
            </div>
            <div>
              <b>来源线索</b>
              <span>{insight.source}</span>
            </div>
          </div>
        </article>

        <div className="detail-sticky-actions">
          {inLibrary ? (
            <div className="primary-actions">
              <button
                type="button"
                className="primary-cta"
                onClick={() =>
                  onOpenReferenceLibrary(
                    selected.content_id,
                    refItem?.id,
                  )
                }
              >
                <ExternalLink size={14} />
                在对标库中编辑
              </button>
              {refItem && (
                <span className="muted-hint">
                  {labelReferenceLibraryType(refItem.library_type)} · {labelReferenceLibraryRating(refItem.rating)}
                </span>
              )}
            </div>
          ) : (
            <div className="primary-actions intelligence-primary-actions" data-testid="intelligence-primary-actions">
              <button type="button" className="primary-cta" onClick={() => setLibraryDecisionOpen((value) => !value)}>
                <Library size={14} />
                入库
              </button>
              <button type="button" className="secondary" onClick={onWatchLater}>
                <Check size={14} />
                稍后处理
              </button>
              <button type="button" className="secondary" onClick={confirmDiscard}>
                <Trash2 size={14} />
                不合适
              </button>
            </div>
          )}
        </div>

        {libraryDecisionOpen && !inLibrary && (
          <div className="inline-modal" data-testid="library-reason-modal">
            <label>入库位置</label>
            <select
              value={decisionLibraryType}
              onChange={(event) => setDecisionLibraryType(event.target.value as 'lead' | 'non_lead' | 'uncategorized')}
            >
              <option value="non_lead">内容库</option>
              <option value="lead">获客库</option>
              <option value="uncategorized">待分类</option>
            </select>
            <label>原因（可选）</label>
            <input value={inlineReason} onChange={(event) => setInlineReason(event.target.value)} placeholder="如：评论区多条求推" />
            <div className="action-strip">
              <button type="button" onClick={submitLibraryDecision}>
                确认入库
              </button>
              <button type="button" className="secondary" onClick={() => setLibraryDecisionOpen(false)}>
                取消
              </button>
            </div>
          </div>
        )}

        {feedback && (
          <div className="feedback">
            <span>{feedback}</span>
            {onOpenOperationsJob ? (
              <button type="button" className="secondary linkish" onClick={onOpenOperationsJob}>
                查看执行记录
              </button>
            ) : null}
          </div>
        )}
      </div>
    </aside>
  );
}
