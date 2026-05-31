import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, X } from 'lucide-react';
import {
  archiveManualTag,
  createManualTag,
  deleteManualTag,
  fetchManualTags,
  hardDeleteManualTag,
  restoreManualTag,
} from '../api/intelligence';
import type { ManualTag, Role } from '../types/api';

type Props = {
  role: Role;
  userId: string;
  valueNames: string[];
  disabled?: boolean;
  onChange: (tagIds: string[]) => void | Promise<void>;
};

export function ManualTagPicker({ role, userId, valueNames, disabled, onChange }: Props) {
  const [tags, setTags] = useState<ManualTag[]>([]);
  const [loading, setLoading] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [newTagName, setNewTagName] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>([]);
  const rootRef = useRef<HTMLDivElement>(null);

  const loadTags = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchManualTags(role, userId, role === 'admin' || role === 'supervisor');
      setTags(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : '标签加载失败');
    } finally {
      setLoading(false);
    }
  }, [role, userId]);

  useEffect(() => {
    void loadTags();
  }, [loadTags]);

  useEffect(() => {
    if (!tags.length) return;
    setSelectedTagIds(tags.filter((item) => valueNames.includes(item.name)).map((item) => item.id));
  }, [tags, valueNames]);

  useEffect(() => {
    if (!panelOpen) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setPanelOpen(false);
      }
    }
    window.addEventListener('mousedown', onPointerDown);
    return () => window.removeEventListener('mousedown', onPointerDown);
  }, [panelOpen]);

  const activeTags = useMemo(() => tags.filter((item) => item.status === 'active'), [tags]);
  const selectedTags = useMemo(() => {
    const byId = new Map(tags.map((item) => [item.id, item]));
    return selectedTagIds
      .map((id) => byId.get(id))
      .filter(Boolean) as ManualTag[];
  }, [selectedTagIds, tags]);

  const archivedSelected = useMemo(
    () => valueNames.filter((name) => !selectedTags.some((item) => item.name === name)),
    [valueNames, selectedTags],
  );

  async function applySelection(next: string[]) {
    setSelectedTagIds(next);
    await onChange(next);
  }

  async function toggleTag(tagId: string) {
    const next = selectedTagIds.includes(tagId)
      ? selectedTagIds.filter((id) => id !== tagId)
      : [...selectedTagIds, tagId];
    await applySelection(next);
  }

  async function handleCreateTag() {
    const name = newTagName.trim();
    if (!name) return;
    setError('');
    setCreating(true);
    try {
      const created = await createManualTag(role, name, userId);
      await loadTags();
      setNewTagName('');
      if (!selectedTagIds.includes(created.id)) {
        await applySelection([...selectedTagIds, created.id]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '新增标签失败');
    } finally {
      setCreating(false);
    }
  }

  const isManager = role === 'admin' || role === 'supervisor';

  return (
    <div className="manual-tag-picker" data-testid="manual-tag-picker" ref={rootRef}>
      <div className="manual-tag-chip-row">
        {selectedTags.map((tag) => (
          <button
            key={tag.id}
            type="button"
            className="tag-button manual-tag-chip"
            disabled={disabled}
            onClick={() => void toggleTag(tag.id)}
          >
            {tag.name}
            {!disabled ? <X size={12} aria-hidden="true" /> : null}
          </button>
        ))}
        {archivedSelected.map((name) => (
          <span key={name} className="manual-tag-chip archived">
            {name}
            <span className="muted-hint">已停用</span>
          </span>
        ))}
      </div>

      {!disabled ? (
        <div className="manual-tag-select-wrap">
          <button
            type="button"
            className={`secondary manual-tag-trigger ${panelOpen ? 'open' : ''}`}
            aria-expanded={panelOpen}
            onClick={() => setPanelOpen((value) => !value)}
          >
            选择标签
            <ChevronDown size={14} aria-hidden="true" />
          </button>
          {panelOpen ? (
            <div className="manual-tag-panel" data-testid="manual-tag-dropdown">
              <div className="manual-tag-panel-section">
                <div className="manual-tag-panel-title">已注册标签</div>
                <div className="manual-tag-option-list">
                  {loading ? <span className="muted-hint">加载中…</span> : null}
                  {!loading && activeTags.length === 0 ? (
                    <span className="muted-hint">暂无注册标签，可在下方新增</span>
                  ) : null}
                  {activeTags.map((tag) => (
                    <label key={tag.id} className="manual-tag-option">
                      <input
                        type="checkbox"
                        checked={selectedTagIds.includes(tag.id)}
                        onChange={() => void toggleTag(tag.id)}
                      />
                      <span className="manual-tag-option-label">{tag.name}</span>
                      {tag.is_system ? <span className="muted-hint manual-tag-option-meta">系统</span> : null}
                    </label>
                  ))}
                </div>
              </div>

              <div className="manual-tag-panel-divider" />

              <div className="manual-tag-panel-section">
                <div className="manual-tag-panel-title">新增 / 管理</div>
                <div className="manual-tag-create-row">
                  <input
                    value={newTagName}
                    onChange={(event) => setNewTagName(event.target.value)}
                    placeholder="新标签名称"
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        void handleCreateTag();
                      }
                    }}
                  />
                  <button type="button" onClick={() => void handleCreateTag()} disabled={!newTagName.trim() || creating}>
                    {creating ? '添加中…' : '添加'}
                  </button>
                </div>
                <button
                  type="button"
                  className="secondary manual-tag-manage-toggle"
                  onClick={() => setManageOpen((value) => !value)}
                >
                  {manageOpen ? '收起标签管理' : '展开标签管理'}
                </button>
                {manageOpen ? (
                  <ManualTagManager
                    role={role}
                    userId={userId}
                    tags={tags}
                    isManager={isManager}
                    onReload={loadTags}
                  />
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {error ? <span className="inline-error">{error}</span> : null}
    </div>
  );
}

type ManagerProps = {
  role: Role;
  userId: string;
  tags: ManualTag[];
  isManager: boolean;
  onReload: () => Promise<void>;
};

function ManualTagManager({ role, userId, tags, isManager, onReload }: ManagerProps) {
  const [workingId, setWorkingId] = useState('');
  const [error, setError] = useState('');

  async function runAction(tagId: string, action: () => Promise<unknown>) {
    setWorkingId(tagId);
    setError('');
    try {
      await action();
      await onReload();
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败');
    } finally {
      setWorkingId('');
    }
  }

  return (
    <div className="manual-tag-manager" data-testid="manual-tag-manager">
      {tags.map((tag) => {
        const deleteDisabled = !tag.can_delete || tag.is_system || tag.usage_count > 0;
        return (
          <div key={tag.id} className="manual-tag-manager-row">
            <span className="manual-tag-manager-name">
              {tag.name}
              {tag.status === 'archived' ? <span className="muted-hint"> · 已停用</span> : null}
              <span className="muted-hint"> · {tag.usage_count} 条</span>
            </span>
            <span className="manual-tag-manager-actions">
              {isManager && tag.status === 'active' ? (
                <button
                  type="button"
                  className="secondary"
                  disabled={workingId === tag.id || tag.is_system}
                  onClick={() => void runAction(tag.id, () => archiveManualTag(role, tag.id, userId))}
                >
                  停用
                </button>
              ) : null}
              {isManager && tag.status === 'archived' ? (
                <button
                  type="button"
                  className="secondary"
                  disabled={workingId === tag.id}
                  onClick={() => void runAction(tag.id, () => restoreManualTag(role, tag.id, userId))}
                >
                  恢复
                </button>
              ) : null}
              {isManager ? (
                <button
                  type="button"
                  className="secondary danger"
                  disabled={workingId === tag.id || tag.is_system}
                  onClick={() => {
                    if (!window.confirm(`确定彻底删除标签「${tag.name}」？将从 ${tag.usage_count} 条内容移除。`)) return;
                    void runAction(tag.id, () => hardDeleteManualTag(role, tag.id, userId));
                  }}
                >
                  彻底删除
                </button>
              ) : null}
              {!isManager ? (
                <button
                  type="button"
                  className="secondary"
                  disabled={deleteDisabled || workingId === tag.id}
                  title={
                    tag.is_system
                      ? '系统标签不可删除'
                      : tag.usage_count > 0
                        ? '标签使用中，无法删除'
                        : !tag.can_delete
                          ? '只能删除自己创建且未使用的标签'
                          : '删除标签'
                  }
                  onClick={() => void runAction(tag.id, () => deleteManualTag(role, tag.id, userId))}
                >
                  删除
                </button>
              ) : null}
            </span>
          </div>
        );
      })}
      {error ? <span className="inline-error">{error}</span> : null}
    </div>
  );
}
