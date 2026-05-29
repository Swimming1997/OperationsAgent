import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  addContentNote,
  assignContent,
  bulkCreateReferenceLibraryItems,
  bulkSetContentStatus,
  createReferenceLibraryItem,
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
import { parseIntelligenceFilters, replaceRouteSearch, serializeIntelligenceFilters } from '../utils/urlFilters';
import { IntelligenceBulkBar } from './intelligence/IntelligenceBulkBar';
import { IntelligenceContentList } from './intelligence/IntelligenceContentList';
import { IntelligenceDetailPanel } from './intelligence/IntelligenceDetailPanel';
import { buildDisplayOptions, IntelligenceFilterPanel } from './intelligence/IntelligenceFilterPanel';
import { IntelligenceScenarioTabs } from './intelligence/IntelligenceScenarioTabs';
import {
  applyAdvancedFilterChange,
  cloneScenarioFilterState,
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
import { useIntelligenceKeyboard } from './intelligence/useIntelligenceKeyboard';

type Props = {
  role: Role;
  userId: string;
  initialContentId?: string;
  onOpenReferenceLibrary?: (contentId: string, itemId?: string) => void;
  onOpenOperationsJob?: (jobId: string) => void;
};

const defaultFilters: IntelligenceFilters = { sort_by: 'latest_discovered_at', sort_order: 'desc' };
const pageSize = '20';

const defaultQuickFilters: IntelligenceFilters = {
  sort_by: 'latest_discovered_at',
  sort_order: 'desc',
};

export function IntelligencePage({ role, userId, initialContentId, onOpenReferenceLibrary, onOpenOperationsJob }: Props) {
  const initialScenario = useMemo(() => parseScenarioFromSearch(window.location.search), []);
  const scenarioRef = useRef<IntelligenceScenario>(initialScenario);
  const [scenario, setScenario] = useState<IntelligenceScenario>(() => initialScenario);
  const [options, setOptions] = useState<ProductOptions | null>(null);
  const [savedScenarioFilters, setSavedScenarioFilters] = useState<
    Partial<Record<IntelligenceScenario, ScenarioFilterState>>
  >({});
  const [advancedFilterState, setAdvancedFilterState] = useState<ScenarioFilterState>(() =>
    systemDefaultScenarioFilters(initialScenario),
  );
  const [filtersLoaded, setFiltersLoaded] = useState(false);
  const [savingScenarioFilters, setSavingScenarioFilters] = useState(false);
  const [quickFilters, setQuickFilters] = useState<IntelligenceFilters>(() => {
    const parsed = parseIntelligenceFilters(window.location.search, defaultQuickFilters);
    return {
      source_surface: parsed.source_surface,
      search_keyword: parsed.search_keyword,
      sort_by: parsed.sort_by || 'latest_discovered_at',
      sort_order: parsed.sort_order || 'desc',
    };
  });
  const [advancedOpen, setAdvancedOpen] = useState(() => initialScenario === 'all');
  const [items, setItems] = useState<IntelligenceItem[]>([]);
  const [hiddenDecisionIds, setHiddenDecisionIds] = useState<string[]>([]);
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
    () => resolveScenarioFilters(advancedFilterState),
    [advancedFilterState],
  );

  const activeFilters = useMemo(
    () => ({
      ...defaultFilters,
      ...resolvedAdvancedFilters,
      ...quickFilters,
    }),
    [resolvedAdvancedFilters, quickFilters],
  );

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
    (contentId?: string | null) => {
      const merged = { ...resolvedAdvancedFilters, ...quickFilters };
      replaceRouteSearch(
        '/intelligence',
        serializeIntelligenceFilters(merged, {
          scenario,
          ...(contentId ? { content_id: contentId } : {}),
        }),
      );
    },
    [resolvedAdvancedFilters, quickFilters, scenario],
  );

  const loadList = useCallback(
    async (preferredContentId?: string | null, justHandledContentId?: string | null) => {
      setLoadingList(true);
      setError('');
      try {
        const response = await fetchIntelligenceContents(role, { ...activeFilters, page: '1', page_size: pageSize }, userId);
        const hidden = new Set([
          ...hiddenDecisionIds,
          ...(justHandledContentId ? [justHandledContentId] : []),
        ]);
        const visibleItems = response.items.filter((item) => !hidden.has(item.content_id));
        setItems(visibleItems);
        setTotal(response.total);
        setSelectedIds([]);
        const nextSelected =
          preferredContentId && visibleItems.some((item) => item.content_id === preferredContentId)
            ? preferredContentId
            : selectedId && visibleItems.some((item) => item.content_id === selectedId)
              ? selectedId
              : visibleItems[0]?.content_id || null;
        setSelectedId(nextSelected);
        syncUrl(nextSelected);
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载失败');
      } finally {
        setLoadingList(false);
      }
    },
    [activeFilters, hiddenDecisionIds, role, selectedId, syncUrl, userId],
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
        const currentScenario = scenarioRef.current;
        const urlAdvanced = pickAdvancedFiltersFromParsed(parseIntelligenceFilters(window.location.search, {}));
        const base = map[currentScenario] ?? systemDefaultScenarioFilters(currentScenario);
        setAdvancedFilterState(cloneScenarioFilterState(mergeScenarioStateWithUrlOverlay(base, urlAdvanced)));
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
  }, [filtersLoaded, scenario]);

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
    setAdvancedFilterState(cloneScenarioFilterState(base));
  }

  function changeScenario(next: IntelligenceScenario) {
    setScenario(next);
    setHiddenDecisionIds([]);
    setAdvancedOpen(next === 'all');
    loadScenarioFilters(next);
  }

  function handleAdvancedOpenChange(open: boolean) {
    setAdvancedOpen(open);
  }

  async function handleSaveScenarioFilters() {
    setSavingScenarioFilters(true);
    setError('');
    try {
      const payload = splitAdvancedFiltersForSave(advancedFilterState);
      const saved = await saveMyScenarioFilters(role, scenario, payload, userId);
      const nextState = scenarioStateFromApi(saved);
      setSavedScenarioFilters((current) => ({ ...current, [scenario]: nextState }));
      setAdvancedFilterState(cloneScenarioFilterState(nextState));
      setFeedback('筛选已保存');
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存筛选失败');
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
      setAdvancedFilterState(cloneScenarioFilterState(systemDefaultScenarioFilters(scenario)));
      setFeedback('已恢复系统默认');
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : '恢复系统默认失败');
    } finally {
      setSavingScenarioFilters(false);
    }
  }

  function applyTagFilter(tag: string) {
    setAdvancedFilterState((current) => applyAdvancedFilterChange(current, 'tag', tag));
    void loadList();
  }

  function nextContentIdAfter(contentId: string) {
    const index = items.findIndex((item) => item.content_id === contentId);
    if (index < 0) return null;
    return items[index + 1]?.content_id || items[index - 1]?.content_id || null;
  }

  async function advanceAfterDecision(contentId: string, message: string) {
    const nextId = nextContentIdAfter(contentId);
    setHiddenDecisionIds((current) => [...new Set([...current, contentId])]);
    setItems((current) => current.filter((item) => item.content_id !== contentId));
    setSelectedId(nextId);
    setFeedback(nextId ? `${message}，已切到下一条` : message);
    await loadList(nextId, contentId);
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
    const label = libraryType === 'lead' ? '已入获客库' : libraryType === 'non_lead' ? '已入内容库' : '已入待分类库';
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
        selected_reason: libraryType === 'lead' ? '批量入获客库' : '批量入内容库',
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
      const nextIndex = index < 0 ? 0 : Math.min(Math.max(index + delta, 0), items.length - 1);
      selectContent(items[nextIndex].content_id);
    },
    [items, selectedId],
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
      window.alert('快捷键：J/K 切换条目，H 入获客库，L 入内容库，S 稍后处理，X 不合适');
    },
  });

  return (
    <section className="page-grid intelligence-grid">
      <IntelligenceFilterPanel
        filters={resolvedAdvancedFilters}
        quickFilters={quickFilters}
        displayOptions={displayOptions}
        advancedOpen={advancedOpen}
        hasCustomizedFilters={hasCustomizedFilters}
        savingScenarioFilters={savingScenarioFilters}
        onAdvancedOpenChange={handleAdvancedOpenChange}
        onQuickFilterChange={(key, value) => {
          setQuickFilters((current) => ({ ...current, [key]: value || undefined }));
        }}
        onFilterChange={(key, value) => {
          setAdvancedFilterState((current) => applyAdvancedFilterChange(current, key, value));
        }}
        onSearch={() => void loadList()}
        onReset={() => {
          loadScenarioFilters(scenario);
          setQuickFilters(defaultQuickFilters);
          void loadList();
        }}
        onSaveScenarioFilters={() => void handleSaveScenarioFilters()}
        onRestoreSystemDefault={() => void handleRestoreSystemDefault()}
      />

      <section className="list-panel">
        <div className="section-head">
          <div>
            <h1>情报中心</h1>
            <IntelligenceScenarioTabs active={scenario} onChange={changeScenario} />
            <span>当前 {items.length} / 共 {total} 条</span>
          </div>
          {error && <span className="inline-error">{error}</span>}
        </div>

        <IntelligenceBulkBar
          role={role}
          selectedCount={selectedIds.length}
          reevaluating={reevaluating}
          onBulkLeadLibrary={() => void handleBulkLibrary('lead')}
          onBulkContentLibrary={() => void handleBulkLibrary('non_lead')}
          onBulkDiscard={() => void handleBulkDiscard()}
          onBulkReevaluate={() => void runReevaluate(selectedIds)}
        />

        <IntelligenceContentList
          items={items}
          selectedId={selectedId}
          selectedIds={selectedIds}
          loading={loadingList || !filtersLoaded}
          onSelect={selectContent}
          onToggleSelect={(contentId) =>
            setSelectedIds((current) =>
              current.includes(contentId) ? current.filter((id) => id !== contentId) : [...current, contentId],
            )
          }
        />
      </section>

      <IntelligenceDetailPanel
        role={role}
        userId={userId}
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
