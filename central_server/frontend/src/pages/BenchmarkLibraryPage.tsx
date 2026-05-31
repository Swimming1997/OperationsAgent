import { Archive, Bookmark, Check, ExternalLink, Heart, MessageCircle, RotateCcw, Scale, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { FilterSearchRow } from '../components/FilterSearchRow';
import { ListPaginationBar } from '../components/ListPaginationBar';
import {
  archiveReferenceLibraryItem,
  revokeReferenceLibraryItem,
  fetchManualTags,
  fetchProductDetail,
  fetchReferenceLibraryEvents,
  fetchReferenceLibraryItems,
  reEvaluateReferenceLibraryItems,
  updateReferenceLibraryItem,
  type ReferenceLibraryFilters,
} from '../api/intelligence';
import {
  ReferencePermissionHint,
  ReferenceRuleExplainSummary,
  ReevaluateResultPanel,
} from '../components/ReferenceRuleExplain';
import {
  canArchiveReference,
  canEditReferenceLibrary,
  canReevaluateReference,
  canRevokeOwnReferenceLibraryItem,
  formatReferenceRevokeRemaining,
  isIntelligenceReadOnly,
  referenceArchiveActionLabel,
  shouldUseReferenceRevokeEndpoint,
} from '../utils/intelligencePermissions';
import { SafeImage } from '../components/SafeImage';
import { coverSrc } from '../utils/mediaUrl';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { ManualTag, ProductDetail, ReferenceLibraryEvent, ReferenceLibraryItem, ReferenceLibraryReevaluateResult, Role } from '../types/api';
import {
  formatTags,
  labelPlatform,
  labelReferenceLibraryEventType,
  labelReferenceLibraryRating,
  labelReferenceLibraryType,
  labelSelectionSource,
  REFERENCE_LIBRARY_RATING_FORM_OPTIONS,
  REFERENCE_LIBRARY_TYPE_FORM_OPTIONS,
} from '../utils/intelligenceLabels';
import { formatMetric } from '../utils/formatMetric';
import { parseReferenceLibraryFilters, replaceRouteSearch, serializeReferenceLibraryFilters } from '../utils/urlFilters';

type Props = {
  role: Role;
  userId: string;
  onOpenIntelligencePool?: (contentId?: string) => void;
  onOpenRules?: () => void;
};

const PAGE_SIZE = 20;

const LIBRARY_TYPE_FILTER_OPTIONS = [
  { value: '', label: '全部库类型' },
  ...REFERENCE_LIBRARY_TYPE_FORM_OPTIONS,
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

const RATING_FILTER_OPTIONS = [
  { value: '', label: '全部评级' },
  ...REFERENCE_LIBRARY_RATING_FORM_OPTIONS,
];

const SORT_OPTIONS = [
  { value: 'selected_at', label: '入库时间' },
  { value: 'like_count', label: '点赞数' },
  { value: 'comment_count', label: '评论数' },
  { value: 'created_at', label: '创建时间' },
];

const UNTAGGED_FILTER = '__untagged__';

function filtersFromLayers(
  platform: string,
  selectionSource: string,
  libraryType: string,
  manualTagFilter: string,
  extra: ReferenceLibraryFilters,
): ReferenceLibraryFilters {
  return {
    ...extra,
    platform: platform || undefined,
    selection_source: selectionSource || undefined,
    library_type: libraryType || undefined,
    manual_tag_id: manualTagFilter && manualTagFilter !== UNTAGGED_FILTER ? manualTagFilter : undefined,
    untagged: manualTagFilter === UNTAGGED_FILTER ? 'true' : undefined,
    sort_by: extra.sort_by || 'selected_at',
    sort_order: extra.sort_order || 'desc',
    page: extra.page || '1',
    page_size: extra.page_size || String(PAGE_SIZE),
  };
}

function formatCommentTime(value: string | null | undefined) {
  if (!value) return '';
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

function formatEventPayload(event: ReferenceLibraryEvent): string {
  const payload = event.event_payload || {};
  const parts: string[] = [];
  if (payload.library_type) parts.push(labelReferenceLibraryType(String(payload.library_type)));
  if (payload.rating) parts.push(labelReferenceLibraryRating(String(payload.rating)));
  if (payload.selected_reason) parts.push(String(payload.selected_reason));
  return parts.length ? parts.join(' · ') : '';
}

export function BenchmarkLibraryPage({ role, userId, onOpenIntelligencePool, onOpenRules }: Props) {
  const initialParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const initial = useMemo(
    () =>
      parseReferenceLibraryFilters(window.location.search, {
        sort_by: 'selected_at',
        sort_order: 'desc',
        page: '1',
        page_size: String(PAGE_SIZE),
      }),
    [initialParams],
  );
  const [platformTab, setPlatformTab] = useState(initial.platform || '');
  const [sourceTab, setSourceTab] = useState(initial.selection_source || '');
  const [libraryTab, setLibraryTab] = useState(initial.library_type || '');
  const [rating, setRating] = useState(initial.rating || '');
  const [manualTagFilter, setManualTagFilter] = useState(
    initial.untagged === 'true' ? UNTAGGED_FILTER : initial.manual_tag_id || '',
  );
  const [registryTags, setRegistryTags] = useState<ManualTag[]>([]);
  const [sortBy, setSortBy] = useState(initial.sort_by || 'selected_at');
  const initialContentQuery = initial.content_query || initial.search_keyword || '';
  const [searchInput, setSearchInput] = useState(initialContentQuery);
  const [contentQuery, setContentQuery] = useState(initialContentQuery);
  const [page, setPage] = useState(Number(initial.page || '1'));
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<ReferenceLibraryItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initialParams.get('item_id'));
  const [bulkIds, setBulkIds] = useState<string[]>([]);
  const [bulkLibraryType, setBulkLibraryType] = useState('uncategorized');
  const [detail, setDetail] = useState<ProductDetail | null>(null);
  const [events, setEvents] = useState<ReferenceLibraryEvent[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [listError, setListError] = useState('');
  const [detailError, setDetailError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [reevaluating, setReevaluating] = useState(false);
  const [bulkWorking, setBulkWorking] = useState(false);
  const [reevaluateResults, setReevaluateResults] = useState<ReferenceLibraryReevaluateResult[]>([]);
  const [edit, setEdit] = useState({ library_type: 'uncategorized', rating: 'watching', note: '', selected_reason: '' });

  const readOnly = isIntelligenceReadOnly(role);
  const canReevaluate = canReevaluateReference(role);
  const canEdit = canEditReferenceLibrary(role);
  const selected = useMemo(() => items.find((item) => item.id === selectedId) || null, [items, selectedId]);
  const canArchiveCurrent = selected ? canArchiveReference(role, selected, userId) : false;
  const archiveActionLabel = selected ? referenceArchiveActionLabel(role, selected, userId) : '移出对标库';
  const revokeRemaining = selected ? formatReferenceRevokeRemaining(selected) : null;
  const canArchiveBulk = useMemo(() => {
    if (bulkIds.length === 0) return false;
    if (role === 'admin' || role === 'supervisor') return true;
    return bulkIds.every((id) => {
      const item = items.find((entry) => entry.id === id);
      return item ? canRevokeOwnReferenceLibraryItem(role, item, userId) : false;
    });
  }, [bulkIds, items, role, userId]);
  const bulkArchiveLabel =
    role === 'operator' ? '批量撤回入库' : '批量移出';

  const activeFilters = useMemo(
    () =>
      filtersFromLayers(platformTab, sourceTab, libraryTab, manualTagFilter, {
        rating,
        content_query: contentQuery || undefined,
        sort_by: sortBy,
        sort_order: 'desc',
        page: String(page),
        page_size: String(PAGE_SIZE),
      }),
    [platformTab, sourceTab, libraryTab, manualTagFilter, rating, contentQuery, sortBy, page],
  );

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const syncUrl = useCallback((filters: ReferenceLibraryFilters, itemId?: string | null) => {
    const params = serializeReferenceLibraryFilters(filters, itemId ? { item_id: itemId } : undefined);
    replaceRouteSearch('/reference-library', params);
  }, []);

  const loadList = useCallback(
    async (filters = activeFilters, preferredItemId?: string | null, preferredContentId?: string | null) => {
      setLoadingList(true);
      setListError('');
      try {
        const response = await fetchReferenceLibraryItems(role, filters, userId);
        setItems(response.items);
        setTotal(response.total);
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
        setBulkIds((current) => current.filter((id) => response.items.some((item) => item.id === id)));
        syncUrl(filters, nextId);
      } catch (err) {
        setListError(err instanceof Error ? err.message : '列表加载失败');
      } finally {
        setLoadingList(false);
      }
    },
    [activeFilters, role, syncUrl, userId],
  );

  const initialContentId = useMemo(() => initialParams.get('content_id'), [initialParams]);

  useEffect(() => {
    void fetchManualTags(role, userId)
      .then((response) => setRegistryTags(response.items.filter((item) => item.status === 'active')))
      .catch(() => setRegistryTags([]));
  }, [role, userId]);

  useEffect(() => {
    void loadList(activeFilters, selectedId, initialContentId);
  }, [platformTab, sourceTab, libraryTab, rating, manualTagFilter, sortBy, contentQuery, page]);

  useEffect(() => {
    if (!selected) return;
    setEdit({
      library_type: selected.library_type || 'uncategorized',
      rating: selected.rating || 'watching',
      note: selected.note || '',
      selected_reason: selected.selected_reason || '',
    });
  }, [selected]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      setEvents([]);
      return;
    }
    setLoadingDetail(true);
    setDetailError('');
    Promise.all([
      fetchProductDetail(role, selected.content_id, userId),
      fetchReferenceLibraryEvents(role, selected.id, userId),
    ])
      .then(([nextDetail, nextEvents]) => {
        setDetail(nextDetail);
        setEvents(nextEvents);
      })
      .catch((err) => setDetailError(err instanceof Error ? err.message : '详情加载失败'))
      .finally(() => setLoadingDetail(false));
  }, [selected, role, userId]);

  function applySearch() {
    setContentQuery(searchInput.trim());
    setPage(1);
  }

  function clearSearch() {
    setSearchInput('');
    setContentQuery('');
    setPage(1);
  }

  function resetFilters() {
    setPlatformTab('');
    setSourceTab('');
    setLibraryTab('');
    setRating('');
    setManualTagFilter('');
    setSortBy('selected_at');
    setSearchInput('');
    setContentQuery('');
    setPage(1);
  }

  function toggleBulk(itemId: string) {
    setBulkIds((current) => (current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]));
  }

  function toggleBulkAll() {
    if (bulkIds.length === items.length) {
      setBulkIds([]);
      return;
    }
    setBulkIds(items.map((item) => item.id));
  }

  async function handleSave() {
    if (!selected) return;
    await updateReferenceLibraryItem(role, selected.id, edit, userId);
    setFeedback('对标条目已更新');
    await loadList(activeFilters, selected.id);
  }

  async function handleArchive() {
    if (!selected || !canArchiveCurrent) return;
    if (!window.confirm(`确定${archiveActionLabel}？`)) return;
    if (shouldUseReferenceRevokeEndpoint(role, selected, userId)) {
      await revokeReferenceLibraryItem(role, selected.id, userId);
    } else {
      await archiveReferenceLibraryItem(role, selected.id, userId);
    }
    setFeedback(archiveActionLabel === '撤回入库' ? '已撤回入库' : '已移出对标库');
    setSelectedId(null);
    await loadList(activeFilters);
  }

  async function handleReevaluate(targetIds?: string[]) {
    const ids = targetIds || (selected ? [selected.id] : []);
    const contentIds = items.filter((item) => ids.includes(item.id)).map((item) => item.content_id);
    if (contentIds.length === 0 || !canReevaluate) return;
    setReevaluating(true);
    try {
      const response = await reEvaluateReferenceLibraryItems(
        role,
        { content_ids: contentIds, item_ids: ids },
        userId,
      );
      setReevaluateResults(response.results);
      setFeedback(`规则重评完成（${contentIds.length} 条）`);
      await loadList(activeFilters, selected?.id);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : '规则重评失败');
    } finally {
      setReevaluating(false);
    }
  }

  async function handleBulkUpdateLibraryType() {
    if (bulkIds.length === 0 || !canEdit) return;
    setBulkWorking(true);
    try {
      const results = await Promise.allSettled(
        bulkIds.map((id) => updateReferenceLibraryItem(role, id, { library_type: bulkLibraryType }, userId)),
      );
      const ok = results.filter((item) => item.status === 'fulfilled').length;
      setFeedback(`批量改库类型：成功 ${ok}，失败 ${results.length - ok}`);
      await loadList(activeFilters, selectedId);
    } finally {
      setBulkWorking(false);
    }
  }

  async function handleBulkArchive() {
    if (bulkIds.length === 0 || !canArchiveBulk) return;
    if (!window.confirm(`确定将选中的 ${bulkIds.length} 条${bulkArchiveLabel}？`)) return;
    setBulkWorking(true);
    try {
      const results = await Promise.allSettled(
        bulkIds.map((id) => {
          const item = items.find((entry) => entry.id === id);
          if (item && shouldUseReferenceRevokeEndpoint(role, item, userId)) {
            return revokeReferenceLibraryItem(role, id, userId);
          }
          return archiveReferenceLibraryItem(role, id, userId);
        }),
      );
      const ok = results.filter((item) => item.status === 'fulfilled').length;
      setFeedback(`批量移出：成功 ${ok}，失败 ${results.length - ok}`);
      setBulkIds([]);
      await loadList(activeFilters);
    } finally {
      setBulkWorking(false);
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
              <button key={tab.value || 'all'} type="button" className={platformTab === tab.value ? 'selected' : ''} onClick={() => { setPlatformTab(tab.value); setPage(1); }}>
                {tab.label}
              </button>
            ))}
          </div>
        </div>
        <div className="layer-tabs">
          <span className="layer-label">选中来源</span>
          <div className="tab-strip compact">
            {SOURCE_TABS.map((tab) => (
              <button key={tab.value || 'all'} type="button" className={sourceTab === tab.value ? 'selected' : ''} onClick={() => { setSourceTab(tab.value); setPage(1); }}>
                {tab.label}
              </button>
            ))}
          </div>
        </div>
        <div className="layer-tabs">
          <span className="layer-label">库类型</span>
          <div className="tab-strip compact">
            {LIBRARY_TYPE_FILTER_OPTIONS.map((tab) => (
              <button key={tab.value || 'all'} type="button" className={libraryTab === tab.value ? 'selected' : ''} onClick={() => { setLibraryTab(tab.value); setPage(1); }}>
                {tab.label}
              </button>
            ))}
          </div>
        </div>
        <label>评级</label>
        <select value={rating} onChange={(event) => { setRating(event.target.value); setPage(1); }}>
          {RATING_FILTER_OPTIONS.map((item) => <option key={item.value || 'all'} value={item.value}>{item.label}</option>)}
        </select>
        <label>运营标签</label>
        <select
          value={manualTagFilter}
          data-testid="benchmark-manual-tag-filter"
          onChange={(event) => { setManualTagFilter(event.target.value); setPage(1); }}
        >
          <option value="">全部标签</option>
          <option value={UNTAGGED_FILTER}>未打标签</option>
          {registryTags.map((tag) => (
            <option key={tag.id} value={tag.id}>{tag.name}</option>
          ))}
        </select>
        <label>排序</label>
        <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
          {SORT_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
        <div className="filter-actions">
          <button type="button" onClick={() => loadList()}><Search size={14} />刷新</button>
          <button type="button" className="secondary" onClick={resetFilters}>
            <RotateCcw size={14} />重置
          </button>
        </div>
      </aside>

      <section className="list-panel">
        <div className="section-head intelligence-list-head">
          <div className="section-head-main">
            <h1>对标作品库</h1>
            {readOnly ? <p className="muted-hint permission-hint">当前为只读账号，可浏览对标作品，无法编辑或移出。</p> : null}
            <span>
              共 {total} 条 · 第 {page}/{totalPages} 页
              {contentQuery ? ` · 内容搜索「${contentQuery}」` : ''}
            </span>
            {contentQuery ? (
              <p className="muted-hint content-search-hint">内容搜索在当前筛选配置范围内匹配标题/作者/备注。</p>
            ) : null}
          </div>
          <div className="section-head-toolbar">
            <FilterSearchRow
              id="benchmark-search"
              label="内容搜索（标题/作者/备注）"
              value={searchInput}
              appliedQuery={contentQuery}
              layout="inline"
              placeholder="标题 / 作者 / 备注"
              onChange={setSearchInput}
              onSearch={applySearch}
              onClear={clearSearch}
              clearLabel={(query) => `清除「${query}」`}
            />
            {listError && <span className="inline-error">{listError}</span>}
          </div>
        </div>

        {canEdit && items.length > 0 && (
          <div className="bulk-bar" data-testid="benchmark-bulk-bar">
            <span>已选 {bulkIds.length}</span>
            <label className="bulk-inline-label">
              批量改为
              <select value={bulkLibraryType} onChange={(event) => setBulkLibraryType(event.target.value)}>
                {REFERENCE_LIBRARY_TYPE_FORM_OPTIONS.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </label>
            <button type="button" disabled={bulkIds.length === 0 || bulkWorking} onClick={() => void handleBulkUpdateLibraryType()}>
              应用库类型
            </button>
            {canArchiveBulk ? (
              <button type="button" className="secondary" disabled={bulkIds.length === 0 || bulkWorking} onClick={() => void handleBulkArchive()}>
                <Archive size={14} />
                {bulkArchiveLabel}
              </button>
            ) : canEdit ? (
              <ReferencePermissionHint role={role} action={role === 'operator' ? 'revoke' : 'archive'} />
            ) : null}
            {canReevaluate ? (
              <button type="button" className="secondary" disabled={bulkIds.length === 0 || reevaluating} onClick={() => void handleReevaluate(bulkIds)}>
                <Scale size={14} />批量规则重评
              </button>
            ) : (
              <ReferencePermissionHint role={role} action="reevaluate" />
            )}
          </div>
        )}

        {loadingList ? <LoadingState text="列表加载中" /> : items.length === 0 ? (
          <EmptyState
            text={contentQuery || platformTab || sourceTab || libraryTab || rating ? '当前筛选下暂无对标作品' : '对标作品库还是空的，请先在情报中心选品入库'}
            action={
              onOpenIntelligencePool && !readOnly ? (
                <button type="button" className="primary-cta" data-testid="benchmark-empty-cta" onClick={() => onOpenIntelligencePool()}>
                  前往情报中心选品
                </button>
              ) : undefined
            }
          />
        ) : (
          <>
            <div className="data-table" data-testid="benchmark-library-table">
              <div className={`table-row table-head content-row benchmark-library-head ${canEdit ? 'benchmark-library-row--with-check' : ''}`}>
                {canEdit ? (
                <span>
                  <input
                    type="checkbox"
                    checked={bulkIds.length > 0 && bulkIds.length === items.length}
                    onChange={toggleBulkAll}
                    aria-label="全选当前页"
                  />
                </span>
                ) : null}
                <span>封面</span><span>标题</span><span>平台</span><span>分类</span><span>评级</span><span>标签</span><span>来源</span><span>入库时间</span>
              </div>
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`table-row content-row benchmark-library-row ${canEdit ? 'benchmark-library-row--with-check' : ''} ${item.id === selectedId ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedId(item.id);
                    syncUrl(activeFilters, item.id);
                  }}
                >
                  {canEdit ? (
                  <span
                    className="benchmark-row-check"
                    onClick={(event) => event.stopPropagation()}
                    onKeyDown={(event) => event.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={bulkIds.includes(item.id)}
                      onChange={() => toggleBulk(item.id)}
                      aria-label={`选择 ${item.title || item.id}`}
                    />
                  </span>
                  ) : null}
                  <span><SafeImage src={coverSrc(item)} className="thumb-image" placeholderClassName="cover-empty" /></span>
                  <span className="strong">{item.title || '未命名内容'}</span>
                  <span>{labelPlatform(item.platform || '-')}</span>
                  <span>{labelReferenceLibraryType(item.library_type)}</span>
                  <span>{labelReferenceLibraryRating(item.rating)}</span>
                  <span>{formatTags(item.manual_tags)}</span>
                  <span>{formatTags((item.selection_sources || []).map(labelSelectionSource))}</span>
                  <span>{item.selected_at ? new Date(item.selected_at).toLocaleString('zh-CN', { hour12: false }) : '-'}</span>
                </button>
              ))}
            </div>
            <ListPaginationBar
              testId="benchmark-pagination"
              page={page}
              totalPages={totalPages}
              disabled={loadingList}
              onPrev={() => setPage((value) => Math.max(1, value - 1))}
              onNext={() => setPage((value) => Math.min(totalPages, value + 1))}
            />
          </>
        )}
      </section>

      <aside className="detail-panel">
        <div className="detail-top-bar">
          <div className="panel-title">作品详情</div>
        </div>
        {!selected ? <EmptyState text="选择一条对标作品" /> : loadingDetail ? <LoadingState text="详情加载中" /> : detailError ? (
          <ErrorState text={detailError} />
        ) : (
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
              <SafeImage
                src={coverSrc(detail?.latest_snapshot) ?? coverSrc(selected)}
                className="detail-cover"
                frameClassName="cover-media-frame cover-media-frame-detail"
                placeholderClassName="detail-cover-placeholder"
              />
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

            <ReferenceRuleExplainSummary snapshot={explainSnapshot} onOpenRules={onOpenRules} />
            <ReevaluateResultPanel results={reevaluateResults} onClear={() => setReevaluateResults([])} />

            {canEdit && (
              <div className="detail-section benchmark-edit-panel" data-testid="benchmark-edit-panel">
                <b>编辑对标库信息</b>
                <select value={edit.library_type} onChange={(event) => setEdit((current) => ({ ...current, library_type: event.target.value }))}>
                  {REFERENCE_LIBRARY_TYPE_FORM_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
                <select value={edit.rating} onChange={(event) => setEdit((current) => ({ ...current, rating: event.target.value }))}>
                  {REFERENCE_LIBRARY_RATING_FORM_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
                <input value={edit.selected_reason} onChange={(event) => setEdit((current) => ({ ...current, selected_reason: event.target.value }))} placeholder="入库原因" />
                <textarea value={edit.note} onChange={(event) => setEdit((current) => ({ ...current, note: event.target.value }))} placeholder="备注" />
                <div className="action-strip">
                  <button type="button" onClick={() => void handleSave()}><Check size={14} />保存</button>
                  {canArchiveCurrent ? (
                    <button type="button" className="secondary" onClick={() => void handleArchive()}>
                      <Archive size={14} />
                      {archiveActionLabel}
                    </button>
                  ) : canEdit ? (
                    <ReferencePermissionHint role={role} action={role === 'operator' ? 'revoke' : 'archive'} />
                  ) : null}
                  {revokeRemaining && role === 'operator' ? (
                    <span className="muted-hint">撤回剩余：{revokeRemaining}</span>
                  ) : null}
                  {canReevaluate ? (
                    <button type="button" data-testid="reevaluate-current-btn" disabled={reevaluating} onClick={() => void handleReevaluate()}>
                      <Scale size={14} />规则重评
                    </button>
                  ) : (
                    <ReferencePermissionHint role={role} action="reevaluate" />
                  )}
                  {onOpenIntelligencePool && (
                    <button type="button" className="secondary" onClick={() => onOpenIntelligencePool(selected.content_id)}>
                      <ExternalLink size={14} />在情报池打开
                    </button>
                  )}
                </div>
              </div>
            )}

            <p className="muted-hint benchmark-future-hint">
              底图库、仿写、仿画将在后续版本从对标作品一键串联（当前未开放）。
            </p>

            <div className="detail-section">
              <b>事件记录</b>
              {events.length === 0 ? (
                <span className="muted-hint">暂无事件</span>
              ) : (
                <ul className="reference-event-list">
                  {events.map((event) => (
                    <li key={event.id}>
                      <span className="strong">{labelReferenceLibraryEventType(event.event_type)}</span>
                      <span>{new Date(event.created_at).toLocaleString('zh-CN', { hour12: false })}</span>
                      {formatEventPayload(event) && <span className="muted-hint">{formatEventPayload(event)}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {feedback && <div className="feedback">{feedback}</div>}
          </div>
        )}
      </aside>
    </section>
  );
}
