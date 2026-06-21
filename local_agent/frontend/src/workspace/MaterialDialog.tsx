import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useToast } from '../ui/ToastContext';
import type { ContentDetail } from '../types';

interface Props {
  item: ContentDetail | null;
  onClose: () => void;
  onSubmitted: (contentId: number) => void;
}

export function MaterialDialog({ item, onClose, onSubmitted }: Props) {
  const toast = useToast();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [libraryType, setLibraryType] = useState('uncategorized');
  const [rating, setRating] = useState('');
  const [tags, setTags] = useState('');
  const [note, setNote] = useState('');

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (item) {
      const material = item.material_export || {};
      setLibraryType(material.library_type || (item.acquisition_hit_count ? 'lead' : 'uncategorized'));
      setRating(material.rating || '');
      setTags((material.material_tags || []).join(', '));
      setNote(material.note || '');
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [item]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!item) return;
    const tagList = tags
      .split(/[,，]/)
      .map((value) => value.trim())
      .filter(Boolean);
    try {
      const result = await api<{ status: string }>(`/api/local/contents/${item.id}/material`, {
        method: 'POST',
        body: JSON.stringify({
          library_type: libraryType,
          rating: rating || null,
          material_tags: tagList,
          note: note.trim() || null,
          selected_reason: '本地工作台人工精选',
        }),
      });
      toast(result.status === 'synced' ? '已加入中央素材库' : '收藏意图已保存，等待重试');
      onSubmitted(item.id);
    } catch (error) {
      toast((error as Error).message);
    }
  };

  return (
    <dialog ref={dialogRef} onCancel={onClose}>
      <form className="dialog-form" onSubmit={submit}>
        <div className="dialog-heading">
          <h2>加入中央素材库</h2>
          <button className="icon-close" type="button" aria-label="关闭" onClick={onClose}>
            ×
          </button>
        </div>
        <label htmlFor="libraryType">素材类型</label>
        <select id="libraryType" value={libraryType} onChange={(event) => setLibraryType(event.target.value)}>
          <option value="uncategorized">未分类</option>
          <option value="lead">获客内容</option>
          <option value="non_lead">内容参考</option>
          <option value="benchmark_work">对标作品</option>
          <option value="visual_material">视觉素材</option>
        </select>
        <label htmlFor="materialRating">评级</label>
        <select id="materialRating" value={rating} onChange={(event) => setRating(event.target.value)}>
          <option value="">暂不评级</option>
          <option value="good">优秀</option>
          <option value="medium">一般</option>
          <option value="watching">观察</option>
          <option value="poor">较差</option>
        </select>
        <label htmlFor="materialTags">标签</label>
        <input
          id="materialTags"
          placeholder="标题结构, 评论洞察"
          value={tags}
          onChange={(event) => setTags(event.target.value)}
        />
        <label htmlFor="materialNote">备注</label>
        <textarea
          id="materialNote"
          rows={3}
          placeholder="可借鉴点、风险提示"
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
        <button type="submit">确认加入</button>
      </form>
    </dialog>
  );
}
