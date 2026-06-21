import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../ui/ToastContext';
import { formatNumber, platformLabel } from '../utils';
import type { CommentSearchItem, CommentSearchResponse } from '../types';

const PAGE_SIZE = 30;

interface Props {
  active: boolean;
  refreshSignal: number;
}

export function CommentsPage({ active, refreshSignal }: Props) {
  const toast = useToast();
  const [keyword, setKeyword] = useState('');
  const [platform, setPlatform] = useState('');
  const [items, setItems] = useState<CommentSearchItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(
    async (targetPage: number) => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (keyword.trim()) params.set('keyword', keyword.trim());
        if (platform) params.set('platform', platform);
        params.set('limit', String(PAGE_SIZE));
        params.set('offset', String((targetPage - 1) * PAGE_SIZE));
        const data = await api<CommentSearchResponse>(`/api/local/comments?${params}`);
        setItems(data.items);
        setTotal(data.total);
        setPage(targetPage);
      } catch (error) {
        toast((error as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [keyword, platform, toast],
  );

  useEffect(() => {
    if (!active) return;
    load(1).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, refreshSignal]);

  return (
    <section className="comments-page">
      <form
        className="comments-search"
        onSubmit={(event) => {
          event.preventDefault();
          load(1).catch(() => {});
        }}
      >
        <input
          type="search"
          placeholder="在所有已采集评论里搜索，例如：求推荐 / 链接 / 多少钱"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
        />
        <select value={platform} onChange={(event) => setPlatform(event.target.value)}>
          <option value="">全部平台</option>
          <option value="xhs">小红书</option>
          <option value="douyin">抖音</option>
        </select>
        <button type="submit" disabled={loading}>
          {loading ? '搜索中…' : '搜索评论'}
        </button>
      </form>

      <div className="comments-summary">命中 {total} 条评论</div>

      {total === 0 ? (
        <div className="empty-state">
          <strong>还没有评论命中</strong>
          <span>先在工作台用“一键全采”拉取笔记的正文和评论，再回来搜索商机关键词。</span>
        </div>
      ) : (
        <div className="comments-list">
          {items.map((item) => (
            <article className="comment-card" key={item.id}>
              <div className="comment-body">{item.comment_text}</div>
              <div className="comment-meta">
                <span>{item.comment_author || '匿名'}</span>
                {item.like_count ? <span>赞 {formatNumber(item.like_count)}</span> : null}
                <span>{platformLabel(item.platform)}</span>
              </div>
              <div className="comment-source">
                来自笔记：{item.content_title || '未命名内容'}
                {item.content_author ? ` · ${item.content_author}` : ''}
                {item.canonical_url ? (
                  <a href={item.canonical_url} target="_blank" rel="noreferrer">
                    打开原文
                  </a>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      )}

      {total > PAGE_SIZE && (
        <nav className="pagination" aria-label="评论分页">
          <button className="secondary" type="button" disabled={page <= 1} onClick={() => load(page - 1)}>
            上一页
          </button>
          <span>
            第 {page} / {pageCount} 页
          </span>
          <button
            className="secondary"
            type="button"
            disabled={page >= pageCount}
            onClick={() => load(page + 1)}
          >
            下一页
          </button>
        </nav>
      )}
    </section>
  );
}
