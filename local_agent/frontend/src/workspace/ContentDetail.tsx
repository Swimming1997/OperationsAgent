import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useToast } from '../ui/ToastContext';
import { formatNumber, mediaUrl, platformLabel, processingStatusLabel } from '../utils';
import type { ContentDetail as ContentDetailType } from '../types';
import { waitForTask } from './tasks';

interface Props {
  contentId: number;
  reloadToken: number;
  onClose: () => void;
  onOpenMaterial: (item: ContentDetailType) => void;
  onMutated: () => void;
}

export function ContentDetail({ contentId, reloadToken, onClose, onOpenMaterial, onMutated }: Props) {
  const toast = useToast();
  const [item, setItem] = useState<ContentDetailType | null>(null);
  const [checking, setChecking] = useState(false);
  const [slide, setSlide] = useState(0);
  const trackRef = useRef<HTMLDivElement>(null);
  const autoFetchedRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    const data = await api<ContentDetailType>(`/api/local/contents/${contentId}`);
    setItem(data);
    return data;
  }, [contentId]);

  useEffect(() => {
    let cancelled = false;
    load()
      .then(async (data) => {
        if (cancelled) return;
        if (!data.detail_fetched_at && autoFetchedRef.current !== contentId) {
          autoFetchedRef.current = contentId;
          toast('正在补抓正文详情…');
          try {
            const result = await api<{ task_id?: number }>(`/api/local/contents/${contentId}/detail-fetch`, {
              method: 'POST',
              body: '{}',
            });
            if (result.task_id) {
              const task = await waitForTask(result.task_id);
              if (!cancelled && task.latest_run?.status === 'success') await load();
            }
          } catch {
            /* best effort */
          }
        }
      })
      .catch((error: Error) => toast(error.message));
    return () => {
      cancelled = true;
    };
  }, [contentId, reloadToken, load, toast]);

  const checkAcquisition = async () => {
    setChecking(true);
    try {
      const result = await api<{ task_id: number }>(`/api/local/contents/${contentId}/acquisition-check`, {
        method: 'POST',
        body: JSON.stringify({ max_comments: 30 }),
      });
      toast('评论采集已开始');
      await waitForTask(result.task_id);
      await load();
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setChecking(false);
    }
  };

  const discard = async () => {
    try {
      await api('/api/local/contents/batch-status', {
        method: 'POST',
        body: JSON.stringify({ content_ids: [contentId], status: 'discarded' }),
      });
      toast('已废弃 1 条');
      await load();
      onMutated();
    } catch (error) {
      toast((error as Error).message);
    }
  };

  if (!item) {
    return (
      <aside className="detail-panel">
        <div className="detail-placeholder">
          <strong>加载中…</strong>
        </div>
      </aside>
    );
  }

  const imageUrls = item.image_urls?.length ? item.image_urls : item.cover_url ? [item.cover_url] : [];
  const creatorStats = [
    item.author_fans_count != null ? `粉丝 ${formatNumber(item.author_fans_count)}` : '',
    item.author_total_liked_collected != null ? `获赞收藏 ${formatNumber(item.author_total_liked_collected)}` : '',
    item.author_works_count != null ? `作品 ${formatNumber(item.author_works_count)}` : '',
    item.author_ip_location || '',
  ]
    .filter(Boolean)
    .join(' · ');
  const material = item.material_export;

  const move = (direction: number) => {
    const track = trackRef.current;
    if (!track) return;
    track.scrollBy({ left: direction * track.clientWidth, behavior: 'smooth' });
  };

  return (
    <aside className="detail-panel">
      <button className="detail-close" type="button" aria-label="关闭详情" title="关闭详情" onClick={onClose}>
        ×
      </button>
      {imageUrls.length > 0 && (
        <div className="media-carousel">
          <div
            ref={trackRef}
            className="media-track"
            onScroll={(event) => {
              const track = event.currentTarget;
              setSlide(Math.round(track.scrollLeft / Math.max(track.clientWidth, 1)));
            }}
          >
            {imageUrls.map((url, index) => (
              <div className="media-slide" key={`${url}-${index}`}>
                <img src={mediaUrl(url)} alt={`图片 ${index + 1}`} loading={index ? 'lazy' : 'eager'} />
              </div>
            ))}
          </div>
          {imageUrls.length > 1 && (
            <>
              <button className="media-nav media-prev" type="button" aria-label="上一张" onClick={() => move(-1)}>
                ‹
              </button>
              <button className="media-nav media-next" type="button" aria-label="下一张" onClick={() => move(1)}>
                ›
              </button>
              <div className="media-counter">
                {Math.min(slide + 1, imageUrls.length)} / {imageUrls.length}
              </div>
            </>
          )}
        </div>
      )}
      <h2>{item.title || '未命名内容'}</h2>
      <div className="detail-author">
        {item.author_name || '未知作者'} · {platformLabel(item.platform)}
      </div>
      {creatorStats && <div className="creator-stats">{creatorStats}</div>}
      {item.author_signature && <div className="creator-signature">{item.author_signature}</div>}
      {material?.status === 'synced' && <div className="material-synced">已加入中央素材库</div>}
      {material?.status === 'failed' && <div className="material-failed">素材同步待重试</div>}
      <div className="detail-processing">
        状态：
        <span className={`processing-tag processing-${item.processing_status || 'pending'}`}>
          {processingStatusLabel(item.processing_status)}
        </span>
      </div>
      <div className="detail-actions">
        <button className="secondary" type="button" onClick={checkAcquisition} disabled={checking}>
          查获客信号
        </button>
        <button type="button" onClick={() => onOpenMaterial(item)}>
          {material?.status === 'synced' ? '更新素材' : '加入素材库'}
        </button>
        <button className="danger-outline" type="button" onClick={discard}>
          {item.processing_status === 'discarded' ? '已废弃' : '废弃'}
        </button>
      </div>
      <div className="detail-body">{item.body_text || '尚未采集正文详情。'}</div>
      <div className="detail-section">
        <h3>获客信号 {item.acquisition_hit_count || 0}</h3>
        {item.comment_hits?.length
          ? item.comment_hits.map((hit, index) => (
              <div className="hit" key={index}>
                <strong>{hit.matched_keyword}</strong>
                <div>{hit.comment_text}</div>
              </div>
            ))
          : '暂无命中'}
      </div>
      <div className="detail-section">
        <h3>全部评论 {item.comments?.length || 0}</h3>
        {item.comments?.length ? (
          <div className="comment-thread">
            {item.comments.map((comment, index) => (
              <div className="comment-line" key={comment.platform_comment_id || index}>
                <div className="comment-line-text">{comment.comment_text}</div>
                <div className="comment-line-meta">
                  {comment.comment_author || '匿名'}
                  {comment.like_count ? ` · 赞 ${formatNumber(comment.like_count)}` : ''}
                </div>
              </div>
            ))}
          </div>
        ) : (
          '尚未采集评论，可点“查获客信号”或在工作台用“一键全采”拉取。'
        )}
      </div>
      {item.canonical_url ? (
        <a href={item.canonical_url} target="_blank" rel="noreferrer">
          打开平台原文
        </a>
      ) : (
        <div className="preview-note">当前内容没有可用的平台原文地址。</div>
      )}
    </aside>
  );
}
