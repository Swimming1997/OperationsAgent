import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { FilterSearchRow } from '../components/FilterSearchRow';
import { ListPaginationBar } from '../components/ListPaginationBar';
import {
  addContentNote,
  assignContent,
  bulkCreateReferenceLibraryItems,
  bulkSetContentStatus,
  createReferenceLibraryItem,
  revokeReferenceLibraryItem,
  updateReferenceLibraryItem,
  enqueueCommentFetch,
  enqueueDetailFetch,
  fetchIntelligenceContents,
  fetchProductDetail,
  reEvaluateReferenceLibraryItems,
  setContentStatus,
  updateManualTags,
  type IntelligenceFilters,
} from '../api/intelligence';
import {
  deleteMyScenarioFilters,
  fetchMyScenarioFilters,
  saveMyScenarioFilters,
} from '../api/intelligenceScenarioFilters';
import { fetchOptions } from '../api/options';
import type { ReferenceExplainSnapshot } from '../components/ReferenceRuleExplain';
import type { IntelligenceItem, ProductDetail, ProductOptions, ReferenceLibraryReevaluateResult, Role } from '../types/api';
import {
  canEditIntelligence,
  isIntelligenceReadOnly,
  shouldUseReferenceRevokeEndpoint,
} from '../utils/intelligencePermissions';
import { parseIntelligenceFilters, replaceRouteSearch, serializeIntelligenceFilters } from '../utils/urlFilters';
import { IntelligenceBulkBar } from './intelligence/IntelligenceBulkBar';
import { IntelligenceContentList } from './intelligence/IntelligenceContentList';
import { IntelligenceDetailPanel } from './intelligence/IntelligenceDetailPanel';
import { buildDisplayOptions, IntelligenceFilterPanel } from './intelligence/IntelligenceFilterPanel';
import {
  applyAdvancedFilterChange,
  buildActiveListFilters,
  cloneScenarioFilterState,
  createCustomScenarioId,
  isCustomScenario,
  materializeScenarioFilterState,
  mergeScenarioStateWithUrlOverlay,
  parseScenarioFromSearch,
  pickAdvancedFiltersFromParsed,
  resolveScenarioFilters,
  scenarioStateFromApi,
  splitAdvancedFiltersForSave,
  systemDefaultScenarioFilters,
  type IntelligenceScenario,
  type ScenarioFilterState,
} from './intelligence/scenarioPresets';
import { useTaskRunRefreshEffect } from '../context/TaskRunRefreshContext';
import { useIntelligenceKeyboard } from './intelligence/useIntelligenceKeyboard';

type Props = {
  role: Role;
  userId: string;
  initialContentId?: string;
  onOpenReferenceLibrary?: (contentId: string, itemId?: string) => void;
  onOpenOperationsJob?: (jobId: string) => void;
  onOpenRules?: () => void;
};


const PAGE_SIZE = 20;
const pageSize = String(PAGE_SIZE);

export function IntelligencePage({ role, userId, initialContentId, onOpenReferenceLibrary, onOpenOperationsJob, onOpenRules }: Props) {
  const readOnly = isIntelligenceReadOnly(role);
  const canEdit = canEditIntelligence(role);
  const initialParsed = useMemo(
    () =>
      parseIntelligenceFilters(window.location.search, {
        sort_by: 'latest_discovered_at',
        sort_order: 'desc',
      }),
    [],
  );
  const initialScenario = useMemo(() => parseScenarioFromSearch(window.location.search), []);
  const scenarioRef = useRef<IntelligenceScenario>(initialScenario);
  const [scenario, setScenario] = useState<IntelligenceScenario>(() => initialScenario);
  const [page, setPage] = useState(() => Math.max(1, Number(initialParsed.page || '1')));
  const initialContentQuery = initialParsed.content_query || initialParsed.business_keyword || '';
  const [contentSearchInput, setContentSearchInput] = useState(initialContentQuery);
  const [appliedContentQuery, setAppliedContentQuery] = useState(initialContentQuery);
  const pendingSelectRef = useRef<'first' | 'last' | null>(null);
  const [options, setOptions] = useState<ProductOptions | null>(null);
  const [savedScenarioFilters, setSavedScenarioFilters] = useState<
    Partial<Record<IntelligenceScenario, ScenarioFilterState>>
  >({});
  const [advancedFilterState, setAdvancedFilterState] = useState<ScenarioFilterState>(() =>
    materializeScenarioFilterState(systemDefaultScenarioFilters(initialScenario)),
  );
  const [filtersLoaded, setFiltersLoaded] = useState(false);
  const [savingScenarioFilters, setSavingScenarioFilters] = useState(false);
  const [quickFilters, setQuickFilters] = useState<IntelligenceFilters>(() => ({
    source_surface: initialParsed.source_surface,
    sort_by: initialParsed.sort_by || 'latest_discovered_at',
    sort_order: initialParsed.sort_order || 'desc',
  }));
  const [advancedOpen, setAdvancedOpen] = useState(() => initialScenario === 'all');
  const [items, setItems] = useState<IntelligenceItem[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(
    () => initialContentId || new URLSearchParams(window.location.search).get('content_id'),
  );
  const [detail, setDetail] = useState<ProductDetail | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [lastFetchJobId, setLastFetchJobId] = useState<string | null>(null);
  const [reevaluating, setReevaluating] = useState(false);
  const [reevaluateResults, setReevaluateResults] = useState<ReferenceLibraryReevaluateResult[]>([]);

  const resolvedAdvancedFilters = useMemo(
    () => resolveScenarioFilters(materializeScenarioFilterState(advancedFilterState)),
    [advancedFilterState],
  );

  const listQueryFilters = useMemo(
    (): IntelligenceFilters =>
      buildActiveListFilters(advancedFilterState, quickFilters, {
        contentQuery: appliedContentQuery || undefined,
        page: String(page),
        pageSize,
      }),
    [advancedFilterState, quickFilters, appliedContentQuery, page],
  );

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasCustomizedFilters = Boolean(savedScenarioFilters[scenario]);

  useEffect(() => {
    scenarioRef.current = scenario;
  }, [scenario]);

  const displayOptions = useMemo(() => buildDisplayOptions(options), [options]);
  const selected = useMemo(() => items.find((item) => item.content_id === selectedId) || null, [items, selectedId]);
  const currentReferenceItem = useMemo(() => detail?.reference_library_items?.[0] || null, [detail]);

  const poolExplainSnapshot = useMemo((): ReferenceExplainSnapshot => {
    if (currentReferenceItem) {
      return {
        in_library: true,
        library_type: currentReferenceItem.library_type,
        rating: currentReferenceItem.rating,
        selection_sources: currentReferenceItem.selection_sources,
        matched_keywords: currentReferenceItem.matched_keywords,
        ai_reason: String(currentReferenceItem.metadata?.ai_reason || ''),
        selected_reason: currentReferenceItem.selected_reason,
        metadata: currentReferenceItem.metadata,
      };
    }
    if (!selected) return { in_library: false };
    return {
      in_library: selected.in_reference_library,
      library_type: selected.reference_library_type,
      rating: selected.reference_library_rating,
      selection_sources: selected.reference_selection_sources,
      matched_keywords: selected.reference_matched_keywords,
      ai_reason: selected.reference_ai_reason,
      manual_locked: selected.reference_manual_locked,
    };
  }, [currentReferenceItem, selected]);

  const syncUrl = useCallback(
    (contentId?: string | null, pageOverride?: number) => {
      const merged = buildActiveListFilters(advancedFilterState, quickFilters, {
        contentQuery: appliedContentQuery || undefined,
        page: String(pageOverride ?? page),
        pageSize,
      });
      replaceRouteSearch(
        '/intelligence',
        serializeIntelligenceFilters(merged, {
          scenario,
          ...(contentId ? { content_id: contentId } : {}),
        }),
      );
    },
    [advancedFilterState, quickFilters, appliedContentQuery, page, scenario],
  );

  const loadList = useCallback(
    async (preferredContentId?: string | null, pageOverride?: number) => {
      const targetPage = pageOverride ?? page;
      setLoadingList(true);
      setError('');
      try {
        const response = await fetchIntelligenceContents(
          role,
          { ...listQueryFilters, page: String(targetPage), page_size: pageSize },
          userId,
        );
        setItems(response.items);
        setTotal(response.total);
        if (targetPage !== page) setPage(targetPage);
        setSelectedIds([]);
        const pendingSelect = pendingSelectRef.current;
        pendingSelectRef.current = null;
        let nextSelected =
          preferredContentId && response.items.some((item) => item.content_id === preferredContentId)
            ? preferredContentId
            : selectedId && response.items.some((item) => item.content_id === selectedId)
              ? selectedId
              : response.items[0]?.content_id || null;
        if (pendingSelect === 'first' && response.items.length > 0) {
          nextSelected = response.items[0].content_id;
        } else if (pendingSelect === 'last' && response.items.length > 0) {
          nextSelected = response.items[response.items.length - 1].content_id;
        }
        setSelectedId(nextSelected);
        syncUrl(nextSelected, targetPage);
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载失败');
      } finally {
        setLoadingList(false);
      }
    },
    [listQueryFilters, page, role, selectedId, syncUrl, userId],
  );

  useEffect(() => {
    fetchOptions(role, userId).then(setOptions).catch((err) => setError(err.message));
  }, [role, userId]);

  useEffect(() => {
    if (initialContentId) setSelectedId(initialContentId);
  }, [initialContentId]);

  useEffect(() => {
    let cancelled = false;
    fetchMyScenarioFilters(role, userId)
      .then((response) => {
        if (cancelled) return;
        const map: Partial<Record<IntelligenceScenario, ScenarioFilterState>> = {};
        response.items.forEach((item) => {
          map[item.scenario] = scenarioStateFromApi(item);
        });
        setSavedScenarioFilters(map);
        let currentScenario = scenarioRef.current;
        if (isCustomScenario(currentScenario) && !map[currentScenario]) {
          currentScenario = 'pending';
          setScenario('pending');
        }
        const urlAdvanced = pickAdvancedFiltersFromParsed(parseIntelligenceFilters(window.location.search, {}));
        const base = map[currentScenario] ?? systemDefaultScenarioFilters(currentScenario);
        setAdvancedFilterState(
          materializeScenarioFilterState(cloneScenarioFilterState(mergeScenarioStateWithUrlOverlay(base, urlAdvanced))),
        );
        setFiltersLoaded(true);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : '加载筛选偏好失败');
        setFiltersLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [role, userId]);

  useEffect(() => {
    if (!filtersLoaded) return;
    void loadList();
  }, [filtersLoaded, page, scenario, advancedFilterState, quickFilters, appliedContentQuery]);

  useTaskRunRefreshEffect(() => {
    void loadList(selectedId ?? undefined);
  }, [loadList, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setLastFetchJobId(null);
    setLoadingDetail(true);
    fetchProductDetail(role, selectedId, userId)
      .then(setDetail)
      .catch((err) => setError(err.message))
      .finally(() => setLoadingDetail(false));
  }, [selectedId, role, userId]);

  async function reloadDetail() {
    if (!selectedId) return;
    const nextDetail = await fetchProductDetail(role, selectedId, userId);
    setDetail(nextDetail);
    await loadList(selectedId);
  }

  function selectContent(contentId: string) {
    setSelectedId(contentId);
    syncUrl(contentId);
  }

  function loadScenarioFilters(next: IntelligenceScenario) {
    const base = savedScenarioFilters[next] ?? systemDefaultScenarioFilters(next);
    setAdvancedFilterState(materializeScenarioFilterState(cloneScenarioFilterState(base)));
  }

  function changeScenario(next: IntelligenceScenario) {
    setScenario(next);
    setPage(1);
    setAdvancedOpen(next === 'all' || isCustomScenario(next));
    loadScenarioFilters(next);
  }

  function applyContentSearch() {
    setAppliedContentQuery(contentSearchInput.trim());
    setPage(1);
  }

  function clearContentSearch() {
    setContentSearchInput('');
    setAppliedContentQuery('');
    setPage(1);
  }

  function runQuery() {
    setAppliedContentQuery(contentSearchInput.trim());
    setPage(1);
  }

  function handleAdvancedOpenChange(open: boolean) {
    setAdvancedOpen(open);
  }

  async function handleSaveScenarioFilters() {
    setSavingScenarioFilters(true);
    setError('');
    try {
      const payload = splitAdvancedFiltersForSave(advancedFilterState);
      if (isCustomScenario(scenario) && !payload.rolling.label) {
        payload.rolling.label = savedScenarioFilters[scenario]?.rolling.label;
      }
      const saved = await saveMyScenarioFilters(role, scenario, payload, userId);
      const nextState = scenarioStateFromApi(saved);
      setSavedScenarioFilters((current) => ({ ...current, [scenario]: nextState }));
      setAdvancedFilterState(materializeScenarioFilterState(cloneScenarioFilterState(nextState)));
      setFeedback(isCustomScenario(scenario) ? '自定义场景已保存' : '筛选已保存');
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存筛选失败');
    } finally {
      setSavingScenarioFilters(false);
    }
  }

  async function handleAddCustomScenario(label: string) {
    setSavingScenarioFilters(true);
    setError('');
    try {
      const customId = createCustomScenarioId();
      const payload = splitAdvancedFiltersForSave(advancedFilterState);
      payload.rolling = { ...payload.rolling, label: label.trim() };
      const saved = await saveMyScenarioFilters(role, customId, payload, userId);
      const nextState = scenarioStateFromApi(saved);
      setSavedScenarioFilters((current) => ({ ...current, [customId]: nextState }));
      setScenario(customId);
      setPage(1);
      setAdvancedOpen(true);
      setAdvancedFilterState(materializeScenarioFilterState(cloneScenarioFilterState(nextState)));
      setFeedback(`已添加场景「${label.trim()}」`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '添加场景失败');
    } finally {
      setSavingScenarioFilters(false);
    }
  }

  async function handleDeleteCustomScenario() {
    if (!isCustomScenario(scenario)) return;
    const label = savedScenarioFilters[scenario]?.rolling.label || '自定义场景';
    if (!window.confirm(`确定删除场景快捷筛选「${label}」？`)) return;
    setSavingScenarioFilters(true);
    setError('');
    try {
      await deleteMyScenarioFilters(role, scenario, userId);
      setSavedScenarioFilters((current) => {
        const next = { ...current };
        delete next[scenario];
        return next;
      });
      setFeedback(`已删除场景「${label}」`);
      changeScenario('pending');
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除场景失败');
    } finally {
      setSavingScenarioFilters(false);
    }
  }

  async function handleRestoreSystemDefault() {
    setSavingScenarioFilters(true);
    setError('');
    try {
      await deleteMyScenarioFilters(role, scenario, userId);
      setSavedScenarioFilters((current) => {
        const next = { ...current };
        delete next[scenario];
        return next;
      });
      setAdvancedFilterState(materializeScenarioFilterState(cloneScenarioFilterState(systemDefaultScenarioFilters(scenario))));
      setContentSearchInput('');
      setAppliedContentQuery('');
      setPage(1);
      setFeedback('已恢复系统默认');
      await loadList(null, 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : '恢复系统默认失败');
    } finally {
      setSavingScenarioFilters(false);
    }
  }

  function applyTagFilter(tag: string) {
    setAdvancedFilterState((current) => applyAdvancedFilterChange(current, 'tag', tag));
    setPage(1);
    void loadList(null, 1);
  }

  function nextContentIdAfter(contentId: string) {
    const index = items.findIndex((item) => item.content_id === contentId);
    if (index < 0) return null;
    return items[index + 1]?.content_id || items[index - 1]?.content_id || null;
  }

  async function advanceAfterDecision(contentId: string, message: string) {
    const nextId = nextContentIdAfter(contentId);
    setSelectedId(nextId);
    setFeedback(nextId ? `${message}，已切到下一条` : message);
    await loadList(nextId);
  }

  async function handleAddToLibrary(libraryType: 'lead' | 'non_lead' | 'uncategorized', reason?: string) {
    if (!selectedId) return;
    const contentId = selectedId;
    await createReferenceLibraryItem(
      role,
      contentId,
      {
        library_type: libraryType,
        rating: 'watching',
        selected_reason: reason,
      },
      userId,
    );
    const label = libraryType === 'lead' ? '已入获客库' : libraryType === 'non_lead' ? '已入非获客库' : '已入待分类库';
    await advanceAfterDecision(contentId, label);
  }

  async function handleWatchLater() {
    if (!selectedId) return;
    const contentId = selectedId;
    await setContentStatus(role, contentId, 'select', undefined, userId);
    const tags = [...new Set([...(detail?.manual_tags || []), '稍后看'])];
    await updateManualTags(role, contentId, tags, userId);
    await advanceAfterDecision(contentId, '已标记稍后处理');
  }

  async function handleDiscard() {
    if (!selectedId) return;
    const contentId = selectedId;
    await setContentStatus(role, contentId, 'discard', undefined, userId);
    await advanceAfterDecision(contentId, '已标记不合适');
  }

  async function handleArchive() {
    if (!selectedId) return;
    await setContentStatus(role, selectedId, 'archive', undefined, userId);
    setFeedback('已归档');
    await reloadDetail();
  }

  async function handleBulkLibrary(libraryType: 'lead' | 'non_lead') {
    if (selectedIds.length === 0) return;
    const response = await bulkCreateReferenceLibraryItems(
      role,
      selectedIds.map((contentId) => ({
        content_id: contentId,
        library_type: libraryType,
        rating: 'watching',
        selected_reason: libraryType === 'lead' ? '批量入获客库' : '批量入非获客库',
      })),
      userId,
    );
    setFeedback(`批量完成：成功 ${response.succeeded.length}，失败 ${response.failed.length}`);
    setSelectedIds([]);
    await loadList();
  }

  async function handleBulkDiscard() {
    if (selectedIds.length === 0) return;
    if (!window.confirm(`确定将 ${selectedIds.length} 条标记为不合适？`)) return;
    const response = await bulkSetContentStatus(
      role,
      { content_ids: selectedIds, action: 'discard' },
      userId,
    );
    setFeedback(`批量完成：成功 ${response.succeeded.length}，失败 ${response.failed.length}`);
    setSelectedIds([]);
    await loadList();
  }

  async function runReevaluate(contentIds: string[]) {
    setReevaluating(true);
    setError('');
    try {
      const response = await reEvaluateReferenceLibraryItems(role, { content_ids: contentIds }, userId);
      setReevaluateResults(response.results);
      setFeedback('规则重评完成');
      if (selectedId) await reloadDetail();
      else await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : '规则重评失败');
    } finally {
      setReevaluating(false);
    }
  }

  const moveSelection = useCallback(
    (delta: number) => {
      if (items.length === 0) return;
      const index = items.findIndex((item) => item.content_id === selectedId);
      const currentIndex = index < 0 ? 0 : index;

      if (delta > 0) {
        if (currentIndex < items.length - 1) {
          selectContent(items[currentIndex + 1].content_id);
          return;
        }
        if (page < totalPages) {
          pendingSelectRef.current = 'first';
          setPage((value) => value + 1);
        }
        return;
      }

      if (currentIndex > 0) {
        selectContent(items[currentIndex - 1].content_id);
        return;
      }
      if (page > 1) {
        pendingSelectRef.current = 'last';
        setPage((value) => value - 1);
      }
    },
    [items, page, selectedId, totalPages, selectContent],
  );

  useIntelligenceKeyboard({
    enabled: items.length > 0 && !loadingList,
    onNext: () => moveSelection(1),
    onPrev: () => moveSelection(-1),
    onLeadLibrary: () => selectedId && void handleAddToLibrary('lead'),
    onContentLibrary: () => selectedId && void handleAddToLibrary('non_lead'),
    onWatchLater: () => selectedId && void handleWatchLater(),
    onDiscard: () => selectedId && void handleDiscard(),
    onShowHelp: () => {
      window.alert('快捷键：J/K 切换条目（页末 J、页首 K 可翻页），H 入获客库，L 入非获客库，S 稍后处理，X 不合适');
    },
  });

  return (
    <section className="page-grid intelligence-grid">
      <IntelligenceFilterPanel
        scenario={scenario}
        filters={resolvedAdvancedFilters}
        quickFilters={quickFilters}
        displayOptions={displayOptions}
        advancedOpen={advancedOpen}
        filterPreferencesEnabled={canEdit}
        hasCustomizedFilters={hasCustomizedFilters}
        savingScenarioFilters={savingScenarioFilters}
        savedScenarioFilters={savedScenarioFilters}
        onScenarioChange={changeScenario}
        onAdvancedOpenChange={handleAdvancedOpenChange}
        onQuickFilterChange={(key, value) => {
          setQuickFilters((current) => ({ ...current, [key]: value || undefined }));
        }}
        onFilterChange={(key, value) => {
          setAdvancedFilterState((current) => applyAdvancedFilterChange(current, key, value));
        }}
        onSearch={runQuery}
        onReset={() => {
          loadScenarioFilters(scenario);
          setQuickFilters({
            sort_by: 'latest_discovered_at',
            sort_order: 'desc',
          });
          setContentSearchInput('');
          setAppliedContentQuery('');
          setPage(1);
        }}
        onSaveScenarioFilters={() => void handleSaveScenarioFilters()}
        onRestoreSystemDefault={() => void handleRestoreSystemDefault()}
        onAddCustomScenario={(label) => void handleAddCustomScenario(label)}
        onDeleteCustomScenario={() => void handleDeleteCustomScenario()}
      />

      <section className="list-panel">
        <div className="section-head intelligence-list-head">
          <div className="section-head-main">
            <h1>情报中心</h1>
            {readOnly ? <p className="muted-hint permission-hint">当前为只读账号，可浏览情报与对标库，无法入库或修改。</p> : null}
            <span>
              共 {total} 条 · 第 {page}/{totalPages} 页
              {appliedContentQuery ? ` · 内容搜索「${appliedContentQuery}」` : ''}
            </span>
            {appliedContentQuery ? (
              <p className="muted-hint content-search-hint">
                {role === 'operator'
                  ? '内容搜索仅在「分配给您」或「由您负责账号采集发现」且符合当前筛选条件的情报中匹配。'
                  : '内容搜索在当前筛选配置范围内匹配标题/作者/正文。'}
              </p>
            ) : null}
          </div>
          <div className="section-head-toolbar">
            <FilterSearchRow
              id="intelligence-content-search"
              label="内容搜索（标题/作者/正文）"
              value={contentSearchInput}
              appliedQuery={appliedContentQuery}
              layout="inline"
              placeholder="标题 / 作者 / 正文"
              onChange={setContentSearchInput}
              onSearch={applyContentSearch}
              onClear={clearContentSearch}
              clearLabel={(query) => `清除「${query}」`}
            />
            {error && <span className="inline-error">{error}</span>}
          </div>
        </div>

        {canEdit ? (
          <IntelligenceBulkBar
            role={role}
            selectedCount={selectedIds.length}
            reevaluating={reevaluating}
            onBulkLeadLibrary={() => void handleBulkLibrary('lead')}
            onBulkContentLibrary={() => void handleBulkLibrary('non_lead')}
            onBulkDiscard={() => void handleBulkDiscard()}
            onBulkReevaluate={() => void runReevaluate(selectedIds)}
          />
        ) : null}

        <IntelligenceContentList
          items={items}
          selectedId={selectedId}
          selectedIds={selectedIds}
          selectionEnabled={canEdit}
          loading={loadingList || !filtersLoaded}
          onSelect={selectContent}
          onToggleSelect={(contentId) =>
            setSelectedIds((current) =>
              current.includes(contentId) ? current.filter((id) => id !== contentId) : [...current, contentId],
            )
          }
        />

        {!loadingList && filtersLoaded && total > 0 && (
          <ListPaginationBar
            testId="intelligence-pagination"
            page={page}
            totalPages={totalPages}
            disabled={loadingList}
            onPrev={() => setPage((value) => Math.max(1, value - 1))}
            onNext={() => setPage((value) => Math.min(totalPages, value + 1))}
          />
        )}
      </section>

      <IntelligenceDetailPanel
        role={role}
        userId={userId}
        readOnly={readOnly}
        selected={selected}
        detail={detail}
        loading={loadingDetail}
        feedback={feedback}
        reevaluating={reevaluating}
        reevaluateResults={reevaluateResults}
        explainSnapshot={poolExplainSnapshot}
        onAddToLibrary={handleAddToLibrary}
        onWatchLater={handleWatchLater}
        onDiscard={handleDiscard}
        onArchive={handleArchive}
        onOpenReferenceLibrary={(contentId, itemId) => onOpenReferenceLibrary?.(contentId, itemId)}
        onEnqueueDetail={async () => {
          if (!selectedId) return;
          setFeedback('正在提交详情补采…');
          try {
            const job = await enqueueDetailFetch(role, selectedId, userId);
            setLastFetchJobId(job.job_id);
            setFeedback(`详情补采已提交：${job.job_id}`);
          } catch (err) {
            const message = err instanceof Error ? err.message : '详情补采提交失败';
            setFeedback(message);
            setError(message);
            return;
          }
          await reloadDetail();
        }}
        onEnqueueComment={async () => {
          if (!selectedId) return;
          setFeedback('正在提交评论补采…');
          try {
            const job = await enqueueCommentFetch(role, selectedId, userId);
            setLastFetchJobId(job.job_id);
            setFeedback(`评论补采已提交：${job.job_id}`);
          } catch (err) {
            const message = err instanceof Error ? err.message : '评论补采提交失败';
            setFeedback(message);
            setError(message);
            return;
          }
          await reloadDetail();
        }}
        onSaveManualTags={async (tags) => {
          if (!selectedId) return;
          await updateManualTags(role, selectedId, tags, userId);
          setFeedback('运营标签已保存');
          await reloadDetail();
        }}
        onAssign={async (assigneeUserId) => {
          if (!selectedId) return;
          await assignContent(role, selectedId, assigneeUserId, userId, userId);
          setFeedback('已分配');
          await reloadDetail();
        }}
        onAddNote={async (note) => {
          if (!selectedId) return;
          await addContentNote(role, selectedId, note, userId);
          setFeedback('备注已添加');
          await reloadDetail();
        }}
        onCustomLibrary={async (payload) => {
          if (!selectedId) return;
          await createReferenceLibraryItem(role, selectedId, payload, userId);
          setFeedback('已入库');
          await reloadDetail();
        }}
        onUpdateReferenceLibrary={async (payload) => {
          const itemId = detail?.reference_library_items?.[0]?.id;
          if (!itemId) return;
          await updateReferenceLibraryItem(role, itemId, payload, userId);
          setFeedback('对标库信息已更新');
          await reloadDetail();
          await loadList(selectedId);
        }}
        onRevokeReferenceLibrary={async () => {
          const refItem = detail?.reference_library_items?.[0];
          if (!refItem?.id) return;
          if (!shouldUseReferenceRevokeEndpoint(role, refItem, userId)) return;
          if (!window.confirm('确定撤回入库？条目将移出对标库。')) return;
          await revokeReferenceLibraryItem(role, refItem.id, userId);
          setFeedback('已撤回入库');
          await reloadDetail();
          await loadList(selectedId);
        }}
        onOpenRules={onOpenRules}
        onReevaluate={async () => {
          if (!selectedId) return;
          await runReevaluate([selectedId]);
        }}
        onClearReevaluateResults={() => setReevaluateResults([])}
        onApplyTagFilter={applyTagFilter}
        onOpenOperationsJob={lastFetchJobId ? () => onOpenOperationsJob?.(lastFetchJobId) : undefined}
      />
    </section>
  );
}
