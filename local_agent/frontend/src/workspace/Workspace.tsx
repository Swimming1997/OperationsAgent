import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import { useToast } from '../ui/ToastContext';
import { authStatusLabel, formatNumber, platformLabel, mediaUrl, processingStatusLabel, statusLabel } from '../utils';
import type {
  AccountListResponse,
  CentralSession,
  ContentDetail as ContentDetailType,
  ContentListItem,
  ContentListResponse,
  PlatformAccount,
  SuggestResponse,
  TaskItem,
  TaskListResponse,
} from '../types';
import { ContentDetail } from './ContentDetail';
import { TasksPanel } from './TasksPanel';
import { MaterialDialog } from './MaterialDialog';
import { effectiveStatus, waitForTask } from './tasks';

const PAGE_SIZE = 12;

interface Filters {
  keyword: string;
  platform: string;
  source: string;
  processingStatus: string;
}

const EMPTY_FILTERS: Filters = { keyword: '', platform: '', source: '', processingStatus: '' };

interface Props {
  active: boolean;
  refreshSignal: number;
  centralSession: CentralSession | null;
  reloadCentralSession: () => Promise<CentralSession>;
  openCentralLogin: (onSuccess?: () => void) => void;
  onStatusText: (text: string) => void;
}

export function Workspace({
  active,
  refreshSignal,
  reloadCentralSession,
  openCentralLogin,
  onStatusText,
}: Props) {
  const toast = useToast();
  const [contents, setContents] = useState<ContentListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [draftFilters, setDraftFilters] = useState<Filters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(EMPTY_FILTERS);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detailToken, setDetailToken] = useState(0);
  const [multiSelect, setMultiSelect] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [activeTask, setActiveTask] = useState<string | null>(null);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [maxItems, setMaxItems] = useState('30');
  const [sort, setSort] = useState('comprehensive');
  const [contentForm, setContentForm] = useState('all');
  const [publishTime, setPublishTime] = useState('all');
  const [searchDisabled, setSearchDisabled] = useState(false);
  const [materialItem, setMaterialItem] = useState<ContentDetailType | null>(null);
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [collectAccountId, setCollectAccountId] = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [selectedKeywords, setSelectedKeywords] = useState<Set<string>>(new Set());
  const [suggesting, setSuggesting] = useState(false);
  const [autoDetail, setAutoDetail] = useState(true);

  const loggedInAccountCount = useMemo(
    () => accounts.filter((account) => account.auth_status === 'active').length,
    [accounts],
  );

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const loadContents = useCallback(async () => {
    const params = new URLSearchParams();
    if (appliedFilters.keyword) params.set('keyword', appliedFilters.keyword);
    if (appliedFilters.platform) params.set('platform', appliedFilters.platform);
    if (appliedFilters.source) params.set('source_type', appliedFilters.source);
    if (appliedFilters.processingStatus) params.set('processing_status', appliedFilters.processingStatus);
    params.set('limit', String(PAGE_SIZE));
    params.set('offset', String((page - 1) * PAGE_SIZE));
    const data = await api<ContentListResponse>(`/api/local/contents?${params}`);
    setContents(data.items);
    setTotal(data.total);
    onStatusText(`本地数据库 · ${data.total} 条内容`);
  }, [appliedFilters, page, onStatusText]);

  const loadTasks = useCallback(async () => {
    const data = await api<TaskListResponse>('/api/local/tasks?limit=8');
    setTasks(data.items);
  }, []);

  const loadAccounts = useCallback(async () => {
    const data = await api<AccountListResponse>('/api/local/accounts?platform=xhs');
    setAccounts(data.items);
    setCollectAccountId((current) => (current && !data.items.some((item) => item.id === current) ? '' : current));
  }, []);

  useEffect(() => {
    if (!active) return;
    loadContents().catch((error: Error) => toast(error.message));
  }, [active, loadContents, toast]);

  useEffect(() => {
    if (!active) return;
    loadTasks().catch((error: Error) => toast(error.message));
  }, [active, loadTasks, toast]);

  useEffect(() => {
    if (!active) return;
    loadAccounts().catch((error: Error) => toast(error.message));
  }, [active, loadAccounts, toast]);

  useEffect(() => {
    if (!active || refreshSignal === 0) return;
    Promise.all([loadContents(), loadTasks(), loadAccounts()]).catch((error: Error) => toast(error.message));
  }, [refreshSignal, active, loadContents, loadTasks, loadAccounts, toast]);

  const trackTaskRef = useRef<(taskId: number) => Promise<void>>(async () => {});
  trackTaskRef.current = async (taskId: number) => {
    try {
      const finalTask = await waitForTask(taskId, (task) => {
        const status = effectiveStatus(task);
        const count = task.latest_run?.item_count || 0;
        setActiveTask(
          `“${task.target || task.task_type}” ${statusLabel(status)}${status === 'success' ? `，采集 ${count} 条` : ''}`,
        );
        loadTasks().catch(() => {});
      });
      const status = effectiveStatus(finalTask);
      if (status === 'success') {
        await loadContents();
      } else if (status === 'failed') {
        const summary = finalTask.latest_run?.error_summary_json;
        const message = summary ? (JSON.parse(summary) as { message?: string }).message : '采集失败';
        toast(message || '采集失败');
      } else if (status === 'paused') {
        toast('任务已暂停');
      }
      await loadTasks();
    } finally {
      setSearchDisabled(false);
    }
  };

  const loadSuggestions = async (event: React.FormEvent) => {
    event.preventDefault();
    const keyword = searchKeyword.trim();
    if (!keyword) return;
    setSuggesting(true);
    try {
      const data = await api<SuggestResponse>('/api/local/search-suggest', {
        method: 'POST',
        body: JSON.stringify({
          keyword,
          ...(collectAccountId ? { account_id: collectAccountId } : {}),
        }),
      });
      const words = [keyword, ...data.items.map((item) => item.suggested_keyword)].filter(
        (word, index, list) => word && list.indexOf(word) === index,
      );
      setSuggestions(words);
      setSelectedKeywords(new Set(words));
      if (words.length <= 1) toast('未联想到长尾词，可直接采集该关键词');
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setSuggesting(false);
    }
  };

  const runDetailBatch = async () => {
    const result = await api<{ task_id?: number; status?: string; target_count?: number; worker_count?: number }>(
      '/api/local/detail-batch',
      { method: 'POST', body: JSON.stringify({ max_comments: 30 }) },
    );
    if (result.status === 'empty' || !result.task_id) {
      toast('没有需要补抓正文/评论的笔记');
      return;
    }
    const total = result.target_count || 0;
    const workerCount = result.worker_count || 1;
    setActiveTask(`多账号拉取正文+评论中（${workerCount} 个浏览器并发 / ${total} 条）`);
    let lastDone = -1;
    await waitForTask(result.task_id, (task) => {
      const done = task.latest_run?.item_count || 0;
      setActiveTask(`拉取正文+评论中… ${workerCount} 个浏览器并发，已完成 ${done}/${total}`);
      // Real-time feedback: refresh the list as new like/comment counts land.
      if (done !== lastDone) {
        lastDone = done;
        loadContents().catch(() => {});
      }
    });
    setActiveTask(`正文+评论采集完成（${total} 条）`);
    await loadContents();
    toast('正文+评论采集完成');
  };

  const runBatchCollect = async (keywords: string[]) => {
    const cleaned = keywords.map((word) => word.trim()).filter(Boolean);
    if (cleaned.length === 0) {
      toast('请先选择要采集的关键词');
      return;
    }
    setSearchDisabled(true);
    setPage(1);
    try {
      const task = await api<{ task_id: number }>('/api/local/search-batch', {
        method: 'POST',
        body: JSON.stringify({
          keywords: cleaned,
          max_items: Number(maxItems),
          platform: 'xhs',
          sort,
          content_form: contentForm,
          publish_time: publishTime,
          ...(collectAccountId ? { account_id: collectAccountId } : {}),
        }),
      });
      await trackTaskRef.current(task.task_id);
      if (autoDetail) {
        await runDetailBatch();
      }
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setSearchDisabled(false);
    }
  };

  const onSearch = async (event: React.FormEvent) => {
    await loadSuggestions(event);
  };

  const toggleKeyword = (word: string, checked: boolean) => {
    setSelectedKeywords((prev) => {
      const next = new Set(prev);
      if (checked) next.add(word);
      else next.delete(word);
      return next;
    });
  };

  const addMonitor = async (target: string, intervalSeconds: number) => {
    try {
      const task = await api<{ task_id: number }>('/api/local/tasks', {
        method: 'POST',
        body: JSON.stringify({
          task_type: 'creator_monitor',
          target,
          schedule_seconds: intervalSeconds,
          max_items: 20,
          ...(collectAccountId ? { account_id: collectAccountId } : {}),
        }),
      });
      await loadTasks();
      await trackTaskRef.current(task.task_id);
    } catch (error) {
      toast((error as Error).message);
    }
  };

  const refreshRecommend = async (intervalSeconds?: number) => {
    try {
      const body: Record<string, unknown> = { task_type: 'recommend', max_items: 30 };
      if (intervalSeconds) body.schedule_seconds = intervalSeconds;
      if (collectAccountId) body.account_id = collectAccountId;
      const task = await api<{ task_id: number }>('/api/local/tasks', { method: 'POST', body: JSON.stringify(body) });
      await loadTasks();
      await trackTaskRef.current(task.task_id);
    } catch (error) {
      toast((error as Error).message);
    }
  };

  const taskAction = async (taskId: number, action: string) => {
    await api(`/api/local/tasks/${taskId}/${action}`, { method: 'POST', body: '{}' });
    await loadTasks();
    const messages: Record<string, string> = {
      run: '任务已重新运行',
      resume: '任务已继续运行',
      pause: '任务已暂停',
      cancel: '任务已取消',
    };
    if (messages[action]) toast(messages[action]);
  };

  const applyFilters = () => {
    setPage(1);
    setAppliedFilters(draftFilters);
  };

  const changePage = (next: number) => {
    setPage(Math.max(1, Math.min(next, pageCount)));
  };

  const toggleSelect = (id: number, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const visibleIds = useMemo(() => contents.map((item) => item.id), [contents]);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

  const updateContentStatus = async (ids: number[], status: string, reloadDetail = false) => {
    await api('/api/local/contents/batch-status', { method: 'POST', body: JSON.stringify({ content_ids: ids, status }) });
    setSelectedIds((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.delete(id));
      return next;
    });
    toast(status === 'discarded' ? `已废弃 ${ids.length} 条` : `已设为待处理 ${ids.length} 条`);
    await loadContents();
    if (reloadDetail && selectedId) setDetailToken((value) => value + 1);
  };

  const ensureCentral = async (onReady: () => void) => {
    const session = await reloadCentralSession();
    if (!session.authenticated) {
      openCentralLogin(onReady);
      return;
    }
    onReady();
  };

  const addSelectedToMaterial = async (ids: number[]) => {
    await ensureCentral(async () => {
      let completed = 0;
      for (const contentId of ids) {
        const result = await api<{ status: string }>(`/api/local/contents/${contentId}/material`, {
          method: 'POST',
          body: JSON.stringify({
            library_type: 'uncategorized',
            rating: null,
            material_tags: [],
            note: null,
            selected_reason: '本地工作台批量精选',
          }),
        });
        if (result.status === 'synced' || result.status === 'failed') completed += 1;
      }
      setSelectedIds((prev) => {
        const next = new Set(prev);
        ids.forEach((id) => next.delete(id));
        return next;
      });
      toast(`已提交 ${completed} 条到素材库`);
      await loadContents();
      if (selectedId && ids.includes(selectedId)) setDetailToken((value) => value + 1);
    });
  };

  const openMaterial = (item: ContentDetailType) => {
    ensureCentral(() => setMaterialItem(item));
  };

  return (
    <>
      <section className="search-band">
        <form onSubmit={onSearch}>
          <div className="collect-controls">
            <div className="collect-account">
              <label htmlFor="collectAccount">采集账号</label>
              <select
                id="collectAccount"
                value={collectAccountId}
                onChange={(event) => setCollectAccountId(event.target.value)}
              >
                <option value="">默认浏览器（端口 9222）</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {(account.platform_nickname || account.display_name || '未命名账号') +
                      `（${authStatusLabel(account.auth_status)}）`}
                  </option>
                ))}
              </select>
            </div>
            <div className="collect-account">
              <label htmlFor="sortSelect">排序</label>
              <select id="sortSelect" value={sort} onChange={(event) => setSort(event.target.value)}>
                <option value="comprehensive">综合</option>
                <option value="latest">最新</option>
                <option value="most_liked">最多点赞</option>
                <option value="most_commented">最多评论</option>
                <option value="most_collected">最多收藏</option>
              </select>
            </div>
            <div className="collect-account">
              <label htmlFor="formSelect">类型</label>
              <select id="formSelect" value={contentForm} onChange={(event) => setContentForm(event.target.value)}>
                <option value="all">全部</option>
                <option value="video">视频</option>
                <option value="image_text">图文</option>
              </select>
            </div>
            <div className="collect-account">
              <label htmlFor="publishSelect">发布时间</label>
              <select
                id="publishSelect"
                value={publishTime}
                onChange={(event) => setPublishTime(event.target.value)}
              >
                <option value="all">不限</option>
                <option value="one_day">一天内</option>
                <option value="one_week">一周内</option>
                <option value="half_year">半年内</option>
              </select>
            </div>
            <div className="collect-account">
              <label htmlFor="countSelect">每词数量</label>
              <select id="countSelect" value={maxItems} onChange={(event) => setMaxItems(event.target.value)}>
                <option value="20">20 条</option>
                <option value="30">30 条</option>
                <option value="50">50 条</option>
              </select>
            </div>
          </div>
          <label htmlFor="keyword">搜索小红书内容</label>
          <div className="search-row">
            <input
              id="keyword"
              type="search"
              placeholder="输入关键词，先联想长尾词再批量采集"
              autoComplete="off"
              required
              value={searchKeyword}
              onChange={(event) => setSearchKeyword(event.target.value)}
            />
            <button type="submit" disabled={suggesting}>
              {suggesting ? '联想中…' : '联想长尾词'}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={searchDisabled || !searchKeyword.trim()}
              onClick={() => runBatchCollect([searchKeyword])}
            >
              直接采集
            </button>
          </div>
          <label className="auto-detail">
            <input
              type="checkbox"
              checked={autoDetail}
              onChange={(event) => setAutoDetail(event.target.checked)}
            />
            <span>
              采集后自动用多账号拉正文+评论
              {loggedInAccountCount > 0 ? `（${loggedInAccountCount} 个已登录账号并发）` : '（当前用默认浏览器）'}
            </span>
          </label>
        </form>

        {suggestions.length > 0 && (
          <div className="suggest-band">
            <div className="suggest-head">
              <span>长尾词（勾选要采集的）</span>
              <div className="suggest-actions">
                <button
                  type="button"
                  className="secondary compact-button"
                  onClick={() => setSelectedKeywords(new Set(suggestions))}
                >
                  全选
                </button>
                <button
                  type="button"
                  className="secondary compact-button"
                  onClick={() => setSelectedKeywords(new Set())}
                >
                  清空
                </button>
                <button
                  type="button"
                  className="compact-button"
                  disabled={searchDisabled || selectedKeywords.size === 0}
                  onClick={() => runBatchCollect([...selectedKeywords])}
                >
                  {searchDisabled ? '采集中…' : `一键全采（${selectedKeywords.size}）`}
                </button>
              </div>
            </div>
            <div className="suggest-chips">
              {suggestions.map((word) => (
                <label key={word} className={`suggest-chip ${selectedKeywords.has(word) ? 'on' : ''}`}>
                  <input
                    type="checkbox"
                    checked={selectedKeywords.has(word)}
                    onChange={(event) => toggleKeyword(word, event.target.checked)}
                  />
                  <span>{word}</span>
                </label>
              ))}
            </div>
          </div>
        )}
        {activeTask && <div className="task-line">{activeTask}</div>}
      </section>

      <section className="workspace">
        <aside className="filters">
          <h2>筛选</h2>
          <label htmlFor="localKeyword">本地内容</label>
          <input
            id="localKeyword"
            type="search"
            placeholder="标题、正文、作者"
            value={draftFilters.keyword}
            onChange={(event) => setDraftFilters({ ...draftFilters, keyword: event.target.value })}
            onKeyDown={(event) => {
              if (event.key === 'Enter') applyFilters();
            }}
          />
          <label htmlFor="platformFilter">平台</label>
          <select
            id="platformFilter"
            value={draftFilters.platform}
            onChange={(event) => setDraftFilters({ ...draftFilters, platform: event.target.value })}
          >
            <option value="">全部平台</option>
            <option value="xhs">小红书</option>
            <option value="douyin">抖音</option>
          </select>
          <label htmlFor="sourceFilter">来源</label>
          <select
            id="sourceFilter"
            value={draftFilters.source}
            onChange={(event) => setDraftFilters({ ...draftFilters, source: event.target.value })}
          >
            <option value="">全部来源</option>
            <option value="search">搜索</option>
            <option value="recommend">推荐流</option>
            <option value="creator">对标博主</option>
          </select>
          <label htmlFor="statusFilter">处理状态</label>
          <select
            id="statusFilter"
            value={draftFilters.processingStatus}
            onChange={(event) => setDraftFilters({ ...draftFilters, processingStatus: event.target.value })}
          >
            <option value="">全部状态</option>
            <option value="pending">待处理</option>
            <option value="material">素材库</option>
            <option value="discarded">已废弃</option>
          </select>
          <button className="secondary full" type="button" onClick={applyFilters}>
            应用筛选
          </button>

          <TasksPanel
            tasks={tasks}
            onAddMonitor={addMonitor}
            onRefreshRecommend={refreshRecommend}
            onTaskAction={taskAction}
          />
        </aside>

        <section className="results">
          <div className="section-heading">
            <h2>内容</h2>
            <div className="section-heading-actions">
              <span>{total} 条</span>
              <button
                className="secondary compact-button"
                type="button"
                onClick={() => {
                  setMultiSelect((value) => {
                    if (value) setSelectedIds(new Set());
                    return !value;
                  });
                }}
              >
                {multiSelect ? '退出多选' : '多选'}
              </button>
            </div>
          </div>

          {multiSelect && (
            <div className="batch-toolbar">
              <label className="select-all">
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setSelectedIds((prev) => {
                      const next = new Set(prev);
                      visibleIds.forEach((id) => (checked ? next.add(id) : next.delete(id)));
                      return next;
                    });
                  }}
                />
                <span>全选本页</span>
              </label>
              <span>已选 {selectedIds.size} 条</span>
              <button
                className="secondary"
                type="button"
                disabled={selectedIds.size === 0}
                onClick={() => updateContentStatus([...selectedIds], 'pending').catch((error) => toast(error.message))}
              >
                设为待处理
              </button>
              <button
                className="danger-outline"
                type="button"
                disabled={selectedIds.size === 0}
                onClick={() => updateContentStatus([...selectedIds], 'discarded').catch((error) => toast(error.message))}
              >
                废弃
              </button>
              <button
                type="button"
                disabled={selectedIds.size === 0}
                onClick={() => addSelectedToMaterial([...selectedIds]).catch((error) => toast(error.message))}
              >
                加入素材库
              </button>
            </div>
          )}

          {total === 0 && (
            <div className="empty-state">
              <strong>还没有本地内容</strong>
              <span>提交关键词后，采集结果会保存在这台电脑。</span>
            </div>
          )}

          <div className="content-list">
            {contents.map((item) => (
              <div
                key={item.id}
                className={`content-row ${selectedId === item.id ? 'active' : ''} ${
                  multiSelect ? 'multi-select-active' : ''
                }`}
              >
                {multiSelect && (
                  <label className="content-select" title="选择内容">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      onChange={(event) => toggleSelect(item.id, event.target.checked)}
                    />
                  </label>
                )}
                <button
                  className="content-open"
                  type="button"
                  onClick={() => {
                    setSelectedId(item.id);
                    setDetailToken((value) => value + 1);
                  }}
                >
                  {item.cover_url ? (
                    <img className="cover" src={mediaUrl(item.cover_url)} alt="" />
                  ) : (
                    <div className="cover cover-fallback">无封面</div>
                  )}
                  <div className="content-copy">
                    <p className="content-title">{item.title || '未命名内容'}</p>
                    <div className="content-meta">
                      {platformLabel(item.platform)} · {item.author_name || '未知作者'}
                    </div>
                  </div>
                  <span
                    className={`processing-tag content-status-tag processing-${item.processing_status || 'pending'}`}
                  >
                    {processingStatusLabel(item.processing_status)}
                  </span>
                  <div className="metrics">
                    <span>赞 {formatNumber(item.like_count)}</span>
                    <span>评 {formatNumber(item.comment_count)}</span>
                    {item.acquisition_hit_count ? <span>获客 {item.acquisition_hit_count}</span> : null}
                  </div>
                </button>
              </div>
            ))}
          </div>

          {total > PAGE_SIZE && (
            <nav className="pagination" aria-label="内容分页">
              <button className="secondary" type="button" disabled={page <= 1} onClick={() => changePage(page - 1)}>
                上一页
              </button>
              <span>
                第 {page} / {pageCount} 页
              </span>
              <button
                className="secondary"
                type="button"
                disabled={page >= pageCount}
                onClick={() => changePage(page + 1)}
              >
                下一页
              </button>
            </nav>
          )}
        </section>

        {selectedId !== null ? (
          <ContentDetail
            contentId={selectedId}
            reloadToken={detailToken}
            onClose={() => setSelectedId(null)}
            onOpenMaterial={openMaterial}
            onMutated={() => loadContents().catch((error) => toast(error.message))}
          />
        ) : (
          <aside className="detail-panel">
            <div className="detail-placeholder">
              <strong>选择一条内容</strong>
              <span>查看正文、图片和获客信号。</span>
            </div>
          </aside>
        )}
      </section>

      <MaterialDialog
        item={materialItem}
        onClose={() => setMaterialItem(null)}
        onSubmitted={(contentId) => {
          setMaterialItem(null);
          setDetailToken((value) => value + 1);
          loadContents().catch((error) => toast(error.message));
          if (selectedId !== contentId) setSelectedId(contentId);
        }}
      />
    </>
  );
}
