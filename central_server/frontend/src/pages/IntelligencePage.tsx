import { Archive, Check, FilePlus2, Library, RefreshCw, RotateCcw, Search, Send, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  addContentNote,
  assignContent,
  createReferenceLibraryItem,
  enqueueCommentFetch,
  enqueueDetailFetch,
  fetchDataQualityOverview,
  fetchIntelligenceContents,
  fetchProductDetail,
  fetchReferenceLibraryItems,
  setContentStatus,
  updateManualTags,
  type IntelligenceFilters,
} from '../api/intelligence';
import { fetchOptions } from '../api/options';
import { SafeImage } from '../components/SafeImage';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { DataQualityOverview, IntelligenceItem, ProductDetail, ProductOptions, ReferenceLibraryItem, Role } from '../types/api';
import {
  formatDiscoverySourcesSummary,
  formatSearchContext,
  formatTags,
  INTELLIGENCE_SOURCE_OPTIONS,
  labelCandidateBucket,
  labelDataStatus,
  labelPlatform,
  labelSourceSurface,
  labelWorkflowStatus,
  localizeOptionItems,
} from '../utils/intelligenceLabels';
import { formatMetric } from '../utils/formatMetric';

type Props = {
  role: Role;
  userId: string;
};

type PageTab = 'pool' | 'reference' | 'quality';

const blankFilters: IntelligenceFilters = {};

const DATA_STATUS_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'card_only', label: '仅卡片' },
  { value: 'detail_ready', label: '详情就绪' },
  { value: 'comments_ready', label: '评论就绪' },
];

const SORT_OPTIONS = [
  { value: 'latest_discovered_at', label: '最近发现' },
  { value: 'like_count', label: '点赞数' },
  { value: 'comment_count', label: '评论数' },
  { value: 'collect_count', label: '收藏数' },
  { value: 'discovery_count', label: '发现次数' },
  { value: 'best_search_rank', label: '搜索排名' },
];

export function IntelligencePage({ role, userId }: Props) {
  const [tab, setTab] = useState<PageTab>('pool');
  const [options, setOptions] = useState<ProductOptions | null>(null);
  const [filters, setFilters] = useState<IntelligenceFilters>({ sort_by: 'latest_discovered_at', sort_order: 'desc' });
  const [items, setItems] = useState<IntelligenceItem[]>([]);
  const [referenceItems, setReferenceItems] = useState<ReferenceLibraryItem[]>([]);
  const [qualityOverview, setQualityOverview] = useState<DataQualityOverview | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ProductDetail | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [assignee, setAssignee] = useState(userId);
  const [feedback, setFeedback] = useState('');
  const [manualTagInput, setManualTagInput] = useState('');
  const [libraryReason, setLibraryReason] = useState('');
  const [libraryRating, setLibraryRating] = useState('A');

  const selected = useMemo(() => items.find((item) => item.content_id === selectedId) || null, [items, selectedId]);

  const displayOptions = useMemo(() => {
    if (!options) return null;
    return {
      ...options,
      platforms: localizeOptionItems(options.platforms, { xhs: '小红书', douyin: '抖音' }),
      workflow_statuses: localizeOptionItems(options.workflow_statuses, {
        pending_review: '待审核',
        assigned: '已分配',
        selected: '已选中',
        discarded: '已丢弃',
        archived: '已归档',
      }),
      candidate_buckets: localizeOptionItems(options.candidate_buckets, {
        lead_candidate: '线索候选',
        content_candidate: '内容候选',
        pending_enrichment: '待补全',
        discard: '已过滤',
      }),
    };
  }, [options]);

  useEffect(() => {
    fetchOptions(role, userId).then(setOptions).catch((err) => setError(err.message));
  }, [role, userId]);

  useEffect(() => {
    void loadList();
  }, [role, userId, tab]);

  useEffect(() => {
    if (!selectedId || tab !== 'pool') {
      setDetail(null);
      return;
    }
    setLoadingDetail(true);
    fetchProductDetail(role, selectedId, userId)
      .then((next) => {
        setDetail(next);
        setManualTagInput((next.manual_tags || []).join(', '));
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoadingDetail(false));
  }, [selectedId, role, userId, tab]);

  async function loadList(nextFilters = filters) {
    setLoadingList(true);
    setError('');
    try {
      if (tab === 'reference') {
        const response = await fetchReferenceLibraryItems(role, {}, userId);
        setReferenceItems(response.items);
        setSelectedId(null);
        setDetail(null);
      } else if (tab === 'quality') {
        setQualityOverview(await fetchDataQualityOverview(role, userId));
        setSelectedId(null);
        setDetail(null);
      } else {
        const response = await fetchIntelligenceContents(role, nextFilters, userId);
        setItems(response.items);
        setSelectedId((current) => current || response.items[0]?.content_id || null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoadingList(false);
    }
  }

  async function reloadDetail() {
    if (!selectedId) return;
    setDetail(await fetchProductDetail(role, selectedId, userId));
    const response = await fetchIntelligenceContents(role, filters, userId);
    setItems(response.items);
  }

  async function handleAssign() {
    if (!selectedId) return;
    await assignContent(role, selectedId, assignee, userId, userId);
    setFeedback('已分配');
    await reloadDetail();
  }

  async function handleStatus(action: 'select' | 'discard' | 'archive') {
    if (!selectedId) return;
    await setContentStatus(role, selectedId, action, note || undefined, userId);
    setFeedback(action === 'select' ? '已选中' : action === 'discard' ? '已丢弃' : '已归档');
    setNote('');
    await reloadDetail();
  }

  async function handleNote() {
    if (!selectedId || !note.trim()) return;
    await addContentNote(role, selectedId, note.trim(), userId);
    setFeedback('备注已添加');
    setNote('');
    await reloadDetail();
  }

  async function handleSaveManualTags() {
    if (!selectedId) return;
    const tags = manualTagInput.split(/[,，]/).map((item) => item.trim()).filter(Boolean);
    await updateManualTags(role, selectedId, tags, userId);
    setFeedback('运营标签已保存');
    await reloadDetail();
  }

  async function handleEnqueueDetail() {
    if (!selectedId) return;
    const result = await enqueueDetailFetch(role, selectedId, userId);
    setFeedback(`详情补采任务已创建：${result.job_id}`);
    await reloadDetail();
  }

  async function handleEnqueueComment() {
    if (!selectedId) return;
    const result = await enqueueCommentFetch(role, selectedId, userId);
    setFeedback(`评论补采任务已创建：${result.job_id}`);
    await reloadDetail();
  }

  async function handleAddToReferenceLibrary() {
    if (!selectedId) return;
    await createReferenceLibraryItem(role, selectedId, {
      library_type: 'benchmark_work',
      selected_reason: libraryReason || undefined,
      rating: libraryRating,
      manual_tags: manualTagInput.split(/[,，]/).map((item) => item.trim()).filter(Boolean),
    }, userId);
    setFeedback('已加入对标素材库');
    await reloadDetail();
  }

  function updateFilter(key: keyof IntelligenceFilters, value: string) {
    setFilters((current) => ({ ...current, [key]: value || undefined }));
  }

  function applyTagFilter(tag: string) {
    const next = { ...filters, tag };
    setFilters(next);
    void loadList(next);
  }

  return (
    <section className="page-grid intelligence-grid">
      <aside className="filter-panel">
        <div className="panel-title">筛选</div>
        {tab === 'pool' ? (
          <>
            <label>平台</label>
            <select value={filters.platform || ''} onChange={(event) => updateFilter('platform', event.target.value)}>
              <option value="">全部</option>
              {displayOptions?.platforms.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <label>采集来源</label>
            <select value={filters.source_surface || ''} onChange={(event) => updateFilter('source_surface', event.target.value)}>
              {INTELLIGENCE_SOURCE_OPTIONS.map((item) => (
                <option key={item.value || 'all'} value={item.value}>{item.label}</option>
              ))}
            </select>
            <label>搜索关键词</label>
            <input value={filters.search_keyword || ''} onChange={(event) => updateFilter('search_keyword', event.target.value)} placeholder="如：论文、SCI" />
            <label>数据状态</label>
            <select value={filters.data_status || ''} onChange={(event) => updateFilter('data_status', event.target.value)}>
              {DATA_STATUS_OPTIONS.map((item) => <option key={item.value || 'all'} value={item.value}>{item.label}</option>)}
            </select>
            <label>标签</label>
            <input value={filters.tag || ''} onChange={(event) => updateFilter('tag', event.target.value)} placeholder="平台/搜索/运营标签" />
            <label>排序</label>
            <select value={filters.sort_by || 'latest_discovered_at'} onChange={(event) => updateFilter('sort_by', event.target.value)}>
              {SORT_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <label>最低点赞</label>
            <input value={filters.min_like_count || ''} onChange={(event) => updateFilter('min_like_count', event.target.value)} placeholder="如：50" />
            <label>候选分类</label>
            <select value={filters.candidate_bucket || ''} onChange={(event) => updateFilter('candidate_bucket', event.target.value)}>
              <option value="">全部</option>
              {displayOptions?.candidate_buckets.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <label>审核状态</label>
            <select value={filters.workflow_status || ''} onChange={(event) => updateFilter('workflow_status', event.target.value)}>
              <option value="">全部</option>
              {displayOptions?.workflow_statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <label>业务关键词</label>
            <input value={filters.business_keyword || ''} onChange={(event) => updateFilter('business_keyword', event.target.value)} placeholder="正文/标题命中" />
          </>
        ) : tab === 'reference' ? (
          <span className="muted">对标素材库支持按入库时间倒序浏览。</span>
        ) : (
          <span className="muted">展示近 24 小时采集与数据质量概览。</span>
        )}
        {tab === 'pool' ? (
        <div className="filter-actions">
          <button onClick={() => loadList()}><Search size={14} />查询</button>
          <button className="secondary" onClick={() => { setFilters(blankFilters); void loadList(blankFilters); }}><RotateCcw size={14} />重置</button>
        </div>
        ) : (
        <div className="filter-actions">
          <button onClick={() => loadList()}><Search size={14} />刷新</button>
        </div>
        )}
      </aside>
      <section className="list-panel">
        <div className="section-head">
          <div>
            <h1>情报中心</h1>
            <div className="tab-strip">
              <button className={tab === 'pool' ? 'selected' : ''} onClick={() => setTab('pool')}>公共池</button>
              <button className={tab === 'reference' ? 'selected' : ''} onClick={() => setTab('reference')}>对标素材库</button>
              <button className={tab === 'quality' ? 'selected' : ''} onClick={() => setTab('quality')}>数据质量</button>
            </div>
            <span>{tab === 'pool' ? items.length : tab === 'reference' ? referenceItems.length : qualityOverview ? '概览已加载' : '0'} 条当前结果</span>
          </div>
          {error && <span className="inline-error">{error}</span>}
        </div>
        {loadingList ? <LoadingState text="列表加载中" /> : tab === 'quality' ? (
          !qualityOverview ? <EmptyState text="暂无数据质量概览" /> : (
            <div className="detail-body">
              <div className="metric-grid quality-grid">
                <div><dt>今日新增内容</dt><dd>{qualityOverview.today_new_contents}</dd></div>
                <div><dt>卡片层</dt><dd>{qualityOverview.today_card_count}</dd></div>
                <div><dt>详情层</dt><dd>{qualityOverview.today_detail_count}</dd></div>
                <div><dt>评论快照</dt><dd>{qualityOverview.today_comment_count}</dd></div>
                <div><dt>入库数</dt><dd>{qualityOverview.today_reference_library_count}</dd></div>
                <div><dt>detail_fetch 成功率</dt><dd>{qualityOverview.detail_fetch_success_rate != null ? `${(qualityOverview.detail_fetch_success_rate * 100).toFixed(1)}%` : '-'}</dd></div>
                <div><dt>comment_fetch 成功率</dt><dd>{qualityOverview.comment_fetch_success_rate != null ? `${(qualityOverview.comment_fetch_success_rate * 100).toFixed(1)}%` : '-'}</dd></div>
                <div><dt>搜索上下文完整率</dt><dd>{(qualityOverview.search_context_completeness_rate * 100).toFixed(1)}%</dd></div>
                <div><dt>平台标签覆盖率</dt><dd>{(qualityOverview.platform_tags_coverage_rate * 100).toFixed(1)}%</dd></div>
                <div><dt>重复发现内容数</dt><dd>{qualityOverview.multi_discovery_content_count}</dd></div>
                <div><dt>异常账号数</dt><dd>{qualityOverview.abnormal_account_count}</dd></div>
                <div><dt>补采失控风险</dt><dd>{qualityOverview.runaway_detail_fetch_risk ? '是' : '否'}</dd></div>
              </div>
              <div className="detail-section">
                <b>筛选上下文说明</b>
                <span>{qualityOverview.filter_context_note}</span>
              </div>
            </div>
          )
        ) : tab === 'reference' ? (
          referenceItems.length === 0 ? <EmptyState text="暂无对标素材" /> : (
            <div className="data-table">
              <div className="table-row table-head content-row">
                <span>封面</span><span>标题</span><span>作者</span><span>赞/评/藏</span><span>评级</span><span>入库原因</span><span>标签</span><span>入库时间</span>
              </div>
              {referenceItems.map((item) => (
                <div key={item.id} className="table-row content-row">
                  <span><SafeImage src={item.cover_url} className="thumb-image" placeholderClassName="cover-empty" /></span>
                  <span className="strong">{item.title || '未命名内容'}</span>
                  <span>{item.author_name || '-'}</span>
                  <span>{formatMetric(item.like_count)} / {formatMetric(item.comment_count)} / {formatMetric(item.collect_count)}</span>
                  <span>{item.rating || '-'}</span>
                  <span>{item.selected_reason || '-'}</span>
                  <span>{formatTags([...(item.manual_tags || []), ...(item.material_tags || [])])}</span>
                  <span>{new Date(item.created_at).toLocaleString('zh-CN', { hour12: false })}</span>
                </div>
              ))}
            </div>
          )
        ) : items.length === 0 ? <EmptyState text="暂无情报内容" /> : (
          <div className="data-table">
            <div className="table-row table-head content-row" data-testid="intelligence-table-head">
              <span>封面</span><span>标题</span><span>数据状态</span><span>标签</span><span>搜索上下文</span><span>赞/评</span><span>候选</span><span>入库</span><span>来源</span>
            </div>
            {items.map((item) => (
              <button key={item.content_id} className={`table-row content-row ${item.content_id === selectedId ? 'selected' : ''}`} onClick={() => setSelectedId(item.content_id)}>
                <span><SafeImage src={item.cover_url} className="thumb-image" placeholderClassName="cover-empty" /></span>
                <span className="strong">{item.title || '未命名内容'}</span>
                <span><b className="tag">{labelDataStatus(item.data_status)}</b></span>
                <span>{formatTags([...(item.platform_tags || []), ...(item.manual_tags || [])])}</span>
                <span>{formatSearchContext(item)}</span>
                <span>{formatMetric(item.like_count)} / {formatMetric(item.comment_count)}</span>
                <span><b className="tag">{labelCandidateBucket(item.candidate_bucket)}</b></span>
                <span>{item.reference_library_count > 0 ? `已入库 ${item.reference_library_count}` : '-'}</span>
                <span>{formatDiscoverySourcesSummary(item.discovery_sources_summary)}</span>
              </button>
            ))}
          </div>
        )}
      </section>
      <aside className="detail-panel">
        <div className="panel-title">内容详情</div>
        {tab === 'quality' ? <EmptyState text="数据质量 Tab 仅展示概览指标" /> : tab !== 'pool' ? <EmptyState text="对标素材库列表仅展示，详情请回到公共池查看" /> : loadingDetail ? <LoadingState text="详情加载中" /> : !selected ? <EmptyState text="选择一条情报查看详情" /> : !detail ? <ErrorState text="详情尚未加载" /> : (
          <div className="detail-body">
            <div className="detail-title">{detail.latest_snapshot?.title || selected.title || '未命名内容'}</div>
            <div className="meta-line">{labelPlatform(detail.identity.platform)} · {detail.latest_snapshot?.author_name || selected.author_name || '-'} · {labelDataStatus(detail.data_status)}</div>
            <SafeImage src={detail.latest_snapshot?.cover_url} className="detail-cover" placeholderClassName="detail-cover-placeholder" />
            <p className="body-text">{detail.latest_snapshot?.body_text || '暂无正文快照'}</p>
            <dl className="metric-grid">
              <div><dt>点赞</dt><dd>{formatMetric(detail.latest_snapshot?.like_count)}</dd></div>
              <div><dt>评论</dt><dd>{formatMetric(detail.latest_snapshot?.comment_count)}</dd></div>
              <div><dt>收藏</dt><dd>{formatMetric(detail.latest_snapshot?.collect_count)}</dd></div>
              <div><dt>发现次数</dt><dd>{selected.discovery_count}</dd></div>
            </dl>
            <div className="detail-section">
              <b>标签</b>
              <span>平台：{formatTags(detail.platform_tags)}</span>
              <span>搜索：{formatTags(detail.search_tags)}</span>
              <span>运营：{formatTags(detail.manual_tags)}</span>
              {(detail.platform_tags || []).concat(detail.manual_tags || []).map((tag) => (
                <button key={tag} className="tag-button" onClick={() => applyTagFilter(tag)}>{tag}</button>
              ))}
            </div>
            <div className="detail-section">
              <b>搜索上下文</b>
              <span>{formatSearchContext(selected)}</span>
            </div>
            <div className="action-strip">
              <button onClick={handleEnqueueDetail}><RefreshCw size={14} />补采详情</button>
              <button onClick={handleEnqueueComment}><RefreshCw size={14} />补采评论</button>
            </div>
            {(detail.pending_detail_job_id || detail.pending_comment_job_id) && (
              <div className="feedback">
                {detail.pending_detail_job_id ? `详情任务：${detail.pending_detail_job_id}` : ''}
                {detail.pending_comment_job_id ? `评论任务：${detail.pending_comment_job_id}` : ''}
              </div>
            )}
            <div className="detail-section">
              <b>运营标签</b>
              <input value={manualTagInput} onChange={(event) => setManualTagInput(event.target.value)} placeholder="逗号分隔，如：可仿写, 求助" />
              <button onClick={handleSaveManualTags}><FilePlus2 size={14} />保存标签</button>
            </div>
            <div className="detail-section">
              <b>入对标素材库</b>
              <input value={libraryReason} onChange={(event) => setLibraryReason(event.target.value)} placeholder="入库原因" />
              <select value={libraryRating} onChange={(event) => setLibraryRating(event.target.value)}>
                {['S', 'A', 'B', 'C'].map((rating) => <option key={rating} value={rating}>{rating}</option>)}
              </select>
              <button onClick={handleAddToReferenceLibrary}><Library size={14} />加入对标素材库</button>
              {(detail.reference_library_items || []).map((item) => (
                <span key={item.id}>{item.library_type} · {item.rating || '-'} · {item.selected_reason || '无原因'} · {new Date(item.created_at).toLocaleString('zh-CN', { hour12: false })}</span>
              ))}
            </div>
            <div className="decision-block">
              <b>候选判断</b>
              <span>{labelCandidateBucket(detail.latest_candidate_decision?.candidate_bucket)}</span>
            </div>
            <div className="action-strip">
              <input value={assignee} onChange={(event) => setAssignee(event.target.value)} placeholder="负责人用户 ID" />
              <button onClick={handleAssign}><Send size={14} />分配</button>
            </div>
            <div className="action-strip">
              <button onClick={() => handleStatus('select')}><Check size={14} />选中</button>
              <button onClick={() => handleStatus('discard')}><Trash2 size={14} />丢弃</button>
              <button onClick={() => handleStatus('archive')}><Archive size={14} />归档</button>
            </div>
            <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="添加处理备注" />
            <button onClick={handleNote}><FilePlus2 size={14} />添加备注</button>
            {feedback && <div className="feedback">{feedback}</div>}
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
          </div>
        )}
      </aside>
    </section>
  );
}
