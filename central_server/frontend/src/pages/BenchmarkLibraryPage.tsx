import { Archive, Bookmark, Check, ExternalLink, Heart, ImagePlus, MessageCircle, Palette, PenLine, RotateCcw, Scale, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  archiveReferenceLibraryItem,
  fetchProductDetail,
  fetchReferenceLibraryEvents,
  fetchReferenceLibraryItems,
  reEvaluateReferenceLibraryItems,
  updateReferenceLibraryItem,
  type ReferenceLibraryFilters,
} from '../api/intelligence';
import { canReevaluateReference, ReferenceRuleExplainSummary, ReevaluateResultPanel } from '../components/ReferenceRuleExplain';
import { SafeImage } from '../components/SafeImage';
import { coverSrc } from '../utils/mediaUrl';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { ProductDetail, ReferenceLibraryEvent, ReferenceLibraryItem, ReferenceLibraryReevaluateResult, Role } from '../types/api';
import {
  formatTags,
  labelPlatform,
  labelReferenceLibraryRating,
  labelReferenceLibraryType,
  labelSelectionSource,
} from '../utils/intelligenceLabels';
import { formatMetric } from '../utils/formatMetric';
import { parseReferenceLibraryFilters, replaceRouteSearch, serializeReferenceLibraryFilters } from '../utils/urlFilters';

type Props = {
  role: Role;
  userId: string;
  onOpenIntelligencePool?: (contentId: string) => void;
};

const LIBRARY_TYPE_OPTIONS = [
  { value: '', label: '全部库类型' },
  { value: 'lead', label: '获客库' },
  { value: 'non_lead', label: '非获客库' },
  { value: 'uncategorized', label: '待分类' },
];

const PLATFORM_TABS = [
  { value: '', label: '全部平台' },
  { value: 'xhs', label: '小红书' },
  { value: 'douyin', label: '抖音' },
];

const SOURCE_TABS = [
  { value: '', label: '全部来源' },
  { value: 'manual', label: '我的选中' },
  { value: 'ai', label: '规则自动' },
];

const RATING_OPTIONS = [
  { value: '', label: '全部评级' },
  { value: 'watching', label: '待观察' },
  { value: 'poor', label: '差' },
  { value: 'medium', label: '中' },
  { value: 'good', label: '好' },
];

const SORT_OPTIONS = [
  { value: 'selected_at', label: '入库时间' },
  { value: 'like_count', label: '点赞数' },
  { value: 'comment_count', label: '评论数' },
  { value: 'created_at', label: '创建时间' },
];

const PENDING_ACTIONS = [
  { id: 'background', label: '加入底图库', icon: ImagePlus, hint: 'P1 底图库上线后开放' },
  { id: 'rewrite', label: '仿写', icon: PenLine, hint: 'P1 仿写中心上线后开放' },
  { id: 'illustration', label: '仿画', icon: Palette, hint: 'P2 仿画中心上线后开放' },
] as const;

function filtersFromLayers(platform: string, selectionSource: string, libraryType: string, extra: ReferenceLibraryFilters): ReferenceLibraryFilters {
  return {
    ...extra,
    platform: platform || undefined,
    selection_source: selectionSource || undefined,
    library_type: libraryType || undefined,
    sort_by: extra.sort_by || 'selected_at',
    sort_order: extra.sort_order || 'desc',
  };
}

function formatCommentTime(value: string | null | undefined) {
  if (!value) return '';
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

export function BenchmarkLibraryPage({ role, userId, onOpenIntelligencePool }: Props) {
  const initialParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const initial = useMemo(
    () => parseReferenceLibraryFilters(window.location.search, { sort_by: 'selected_at', sort_order: 'desc' }),
    [initialParams],
  );
  const [platformTab, setPlatformTab] = useState(initial.platform || '');
  const [sourceTab, setSourceTab] = useState(initial.selection_source || '');
  const [libraryTab, setLibraryTab] = useState(initial.library_type || '');
  const [rating, setRating] = useState(initial.rating || '');
  const [sortBy, setSortBy] = useState(initial.sort_by || 'selected_at');
  const [items, setItems] = useState<ReferenceLibraryItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initialParams.get('item_id'));
  const [detail, setDetail] = useState<ProductDetail | null>(null);
  const [events, setEvents] = useState<ReferenceLibraryEvent[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [pendingHint, setPendingHint] = useState('');
  const [reevaluating, setReevaluating] = useState(false);
  const [reevaluateResults, setReevaluateResults] = useState<ReferenceLibraryReevaluateResult[]>([]);
  const [edit, setEdit] = useState({ library_type: 'uncategorized', rating: 'watching', note: '', selected_reason: '' });
  const [editOpen, setEditOpen] = useState(false);

  const canReevaluate = canReevaluateReference(role);
  const canEdit = role === 'admin' || role === 'supervisor' || role === 'operator';
  const canArchive = role === 'admin' || role === 'supervisor';
  const selected = useMemo(() => items.find((item) => item.id === selectedId) || null, [items, selectedId]);

  const activeFilters = useMemo(
    () => filtersFromLayers(platformTab, sourceTab, libraryTab, { rating, sort_by: sortBy, sort_order: 'desc' }),
    [platformTab, sourceTab, libraryTab, rating, sortBy],
  );

  const syncUrl = useCallback((filters: ReferenceLibraryFilters, itemId?: string | null) => {
    const params = serializeReferenceLibraryFilters(filters, itemId ? { item_id: itemId } : undefined);
    replaceRouteSearch('/reference-library', params);
  }, []);

  const loadList = useCallback(async (filters = activeFilters, preferredItemId?: string | null, preferredContentId?: string | null) => {
    setLoadingList(true);
    setError('');
    try {
      const response = await fetchReferenceLibraryItems(role, filters, userId);
      setItems(response.items);
      let nextId: string | null = null;
      if (preferredItemId && response.items.some((item) => item.id === preferredItemId)) {
        nextId = preferredItemId;
      } else if (preferredContentId) {
        nextId = response.items.find((item) => item.content_id === preferredContentId)?.id || null;
      }
      if (!nextId) {
        nextId = response.items[0]?.id || null;
      }
      setSelectedId(nextId);
      syncUrl(filters, nextId);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoadingList(false);
    }
  }, [activeFilters, role, syncUrl, userId]);

  const initialContentId = useMemo(() => initialParams.get('content_id'), [initialParams]);

  useEffect(() => {
    void loadList(activeFilters, selectedId, initialContentId);
  }, [platformTab, sourceTab, libraryTab, rating, sortBy]);

  useEffect(() => {
    if (!selected) return;
    setEdit({
      library_type: selected.library_type || 'uncategorized',
      rating: selected.rating || 'watching',
      note: selected.note || '',
      selected_reason: selected.selected_reason || '',
    });
    setEditOpen(false);
  }, [selected]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      setEvents([]);
      return;
    }
    setLoadingDetail(true);
    Promise.all([
      fetchProductDetail(role, selected.content_id, userId),
      fetchReferenceLibraryEvents(role, selected.id, userId),
    ])
      .then(([nextDetail, nextEvents]) => {
        setDetail(nextDetail);
        setEvents(nextEvents);
      })
      .catch((err) => setError(err instanceof Error ? err.message : '详情加载失败'))
      .finally(() => setLoadingDetail(false));
  }, [selected, role, userId]);

  async function handleSave() {
    if (!selected) return;
    await updateReferenceLibraryItem(role, selected.id, edit, userId);
    setFeedback('对标条目已更新');
    await loadList(activeFilters, selected.id);
  }

  async function handleArchive() {
    if (!selected) return;
    await archiveReferenceLibraryItem(role, selected.id, userId);
    setFeedback('已移出对标库');
    setSelectedId(null);
    await loadList(activeFilters);
  }

  async function handleReevaluate() {
    if (!selected || !canReevaluate) return;
    setReevaluating(true);
    try {
      const response = await reEvaluateReferenceLibraryItems(
        role,
        { content_ids: [selected.content_id], item_ids: [selected.id] },
        userId,
      );
      setReevaluateResults(response.results);
      setFeedback('规则重评完成');
      await loadList(activeFilters, selected.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '规则重评失败');
    } finally {
      setReevaluating(false);
    }
  }

  const explainSnapshot = useMemo(() => {
    if (!selected) return { in_library: false };
    return {
      in_library: true,
      library_type: selected.library_type,
      rating: selected.rating,
      selection_sources: selected.selection_sources,
      matched_keywords: selected.matched_keywords,
      ai_reason: String(selected.metadata?.ai_reason || ''),
      selected_reason: selected.selected_reason,
      metadata: selected.metadata,
    };
  }, [selected]);

  return (
    <section className="page-grid intelligence-grid benchmark-library-grid">
      <aside className="filter-panel">
        <div className="panel-title">对标作品库</div>
        <div className="layer-tabs">
          <span className="layer-label">平台</span>
          <div className="tab-strip compact">
            {PLATFORM_TABS.map((tab) => (
              <button key={tab.value || 'all'} type="button" className={platformTab === tab.value ? 'selected' : ''} onClick={() => setPlatformTab(tab.value)}>
                {tab.label}
              </button>
            ))}
          </div>
        </div>
        <div className="layer-tabs">
          <span className="layer-label">选中来源</span>
          <div className="tab-strip compact">
            {SOURCE_TABS.map((tab) => (
              <button key={tab.value || 'all'} type="button" className={sourceTab === tab.value ? 'selected' : ''} onClick={() => setSourceTab(tab.value)}>
                {tab.label}
              </button>
            ))}
          </div>
        </div>
        <div className="layer-tabs">
          <span className="layer-label">库类型</span>
          <div className="tab-strip compact">
            {LIBRARY_TYPE_OPTIONS.map((tab) => (
              <button key={tab.value || 'all'} type="button" className={libraryTab === tab.value ? 'selected' : ''} onClick={() => setLibraryTab(tab.value)}>
                {tab.label}
              </button>
            ))}
          </div>
        </div>
        <label>评级</label>
        <select value={rating} onChange={(event) => setRating(event.target.value)}>
          {RATING_OPTIONS.map((item) => <option key={item.value || 'all'} value={item.value}>{item.label}</option>)}
        </select>
        <label>排序</label>
        <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
          {SORT_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
        <div className="filter-actions">
          <button type="button" onClick={() => loadList()}><Search size={14} />刷新</button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setPlatformTab('');
              setSourceTab('');
              setLibraryTab('');
              setRating('');
              setSortBy('selected_at');
            }}
          >
            <RotateCcw size={14} />重置
          </button>
        </div>
      </aside>

      <section className="list-panel">
        <div className="section-head">
          <div>
            <h1>对标作品库</h1>
            <span>{items.length} 条当前结果</span>
          </div>
          {error && <span className="inline-error">{error}</span>}
        </div>
        {loadingList ? <LoadingState text="列表加载中" /> : items.length === 0 ? (
          <EmptyState text="当前筛选下暂无对标作品" />
        ) : (
          <div className="data-table" data-testid="benchmark-library-table">
            <div className="table-row table-head content-row">
              <span>封面</span><span>标题</span><span>平台</span><span>分类</span><span>评级</span><span>来源</span><span>入库时间</span>
            </div>
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`table-row content-row ${item.id === selectedId ? 'selected' : ''}`}
                onClick={() => {
                  setSelectedId(item.id);
                  syncUrl(activeFilters, item.id);
                }}
              >
                <span><SafeImage src={coverSrc(item)} className="thumb-image" placeholderClassName="cover-empty" /></span>
                <span className="strong">{item.title || '未命名内容'}</span>
                <span>{labelPlatform(item.platform || '-')}</span>
                <span>{labelReferenceLibraryType(item.library_type)}</span>
                <span>{labelReferenceLibraryRating(item.rating)}</span>
                <span>{formatTags((item.selection_sources || []).map(labelSelectionSource))}</span>
                <span>{item.selected_at ? new Date(item.selected_at).toLocaleString('zh-CN', { hour12: false }) : '-'}</span>
              </button>
            ))}
          </div>
        )}
      </section>

      <aside className="detail-panel">
        <div className="detail-top-bar">
          <div className="panel-title">作品详情</div>
          {selected && canEdit ? (
            <button type="button" className="secondary" onClick={() => setEditOpen((value) => !value)}>
              <PenLine size={14} />{editOpen ? '收起编辑' : '编辑'}
            </button>
          ) : null}
        </div>
        {!selected ? <EmptyState text="选择一条对标作品" /> : loadingDetail ? <LoadingState text="详情加载中" /> : (
          <div className="detail-body">
            <article className="xhs-note-detail">
              <div className="xhs-author-row">
                <div className="xhs-avatar" aria-hidden="true">
                  {(selected.author_name || detail?.latest_snapshot?.author_name || '?').slice(0, 1)}
                </div>
                <div className="xhs-author-meta">
                  <b>{selected.author_name || detail?.latest_snapshot?.author_name || '未知作者'}</b>
                  <span>
                    {labelPlatform(selected.platform || detail?.identity.platform)} · {labelReferenceLibraryType(selected.library_type)} · {labelReferenceLibraryRating(selected.rating)}
                  </span>
                </div>
              </div>
              <SafeImage src={coverSrc(detail?.latest_snapshot) ?? coverSrc(selected)} className="detail-cover xhs-note-cover" placeholderClassName="detail-cover-placeholder xhs-note-cover-placeholder" />
              <div className="xhs-note-copy">
                <div className="detail-title">{selected.title || detail?.latest_snapshot?.title || '未命名内容'}</div>
                {detail?.latest_snapshot?.body_text && <p className="body-text">{detail.latest_snapshot.body_text}</p>}
              </div>
              <dl className="xhs-engagement-bar">
                <div><dt><Heart size={15} />点赞</dt><dd>{formatMetric(selected.like_count ?? detail?.latest_snapshot?.like_count)}</dd></div>
                <div><dt><MessageCircle size={15} />评论</dt><dd>{formatMetric(selected.comment_count ?? detail?.latest_snapshot?.comment_count)}</dd></div>
                <div><dt><Bookmark size={15} />收藏</dt><dd>{formatMetric(selected.collect_count ?? detail?.latest_snapshot?.collect_count)}</dd></div>
              </dl>

              <div className="detail-section comment-preview-section xhs-comment-section benchmark-comment-section">
                <b>评论内容</b>
                {detail?.comments && detail.comments.length > 0 ? (
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
                  <span className="muted-hint">暂无评论快照，可回到情报池补采评论。</span>
                )}
              </div>
            </article>

            <ReferenceRuleExplainSummary snapshot={explainSnapshot} />
            <ReevaluateResultPanel results={reevaluateResults} onClear={() => setReevaluateResults([])} />

            {canEdit && editOpen && (
              <div className="detail-section benchmark-edit-panel">
                <b>编辑</b>
                <select value={edit.library_type} disabled={!canEdit} onChange={(event) => setEdit((current) => ({ ...current, library_type: event.target.value }))}>
                  {LIBRARY_TYPE_OPTIONS.filter((item) => item.value).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
                <select value={edit.rating} disabled={!canEdit} onChange={(event) => setEdit((current) => ({ ...current, rating: event.target.value }))}>
                  {RATING_OPTIONS.filter((item) => item.value).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
                <input value={edit.selected_reason} onChange={(event) => setEdit((current) => ({ ...current, selected_reason: event.target.value }))} placeholder="入库原因" />
                <textarea value={edit.note} onChange={(event) => setEdit((current) => ({ ...current, note: event.target.value }))} placeholder="备注" />
                <div className="action-strip">
                  <button type="button" onClick={handleSave}><Check size={14} />保存</button>
                  {canArchive && <button type="button" className="secondary" onClick={handleArchive}><Archive size={14} />移出</button>}
                  {canReevaluate && (
                    <button type="button" data-testid="reevaluate-current-btn" disabled={reevaluating} onClick={handleReevaluate}><Scale size={14} />规则重评</button>
                  )}
                  {onOpenIntelligencePool && (
                    <button type="button" className="secondary" onClick={() => onOpenIntelligencePool(selected.content_id)}>
                      <ExternalLink size={14} />在情报池打开
                    </button>
                  )}
                </div>
              </div>
            )}

            <div className="detail-section pending-actions">
              <b>后续动作（占位）</b>
              <div className="action-strip">
                {PENDING_ACTIONS.map((action) => {
                  const Icon = action.icon;
                  return (
                    <button
                      key={action.id}
                      type="button"
                      className="secondary"
                      disabled
                      title={action.hint}
                      onClick={() => setPendingHint(action.hint)}
                    >
                      <Icon size={14} />{action.label}
                    </button>
                  );
                })}
              </div>
              {pendingHint && <span className="muted-hint">{pendingHint}</span>}
            </div>

            <div className="detail-section">
              <b>事件记录</b>
              {events.length === 0 ? <span>-</span> : events.map((event) => (
                <span key={event.id}>{event.event_type} · {new Date(event.created_at).toLocaleString('zh-CN', { hour12: false })}</span>
              ))}
            </div>
            {feedback && <div className="feedback">{feedback}</div>}
          </div>
        )}
      </aside>
    </section>
  );
}
