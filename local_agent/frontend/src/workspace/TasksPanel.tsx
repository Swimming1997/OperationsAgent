import { useState } from 'react';
import { statusLabel } from '../utils';
import type { TaskItem } from '../types';
import { effectiveStatus } from './tasks';

interface Props {
  tasks: TaskItem[];
  onAddMonitor: (target: string, intervalSeconds: number) => Promise<void>;
  onRefreshRecommend: (intervalSeconds?: number) => Promise<void>;
  onTaskAction: (taskId: number, action: string) => Promise<void>;
}

function TaskActions({ task, onTaskAction }: { task: TaskItem; onTaskAction: Props['onTaskAction'] }) {
  const status = effectiveStatus(task);
  const button = (action: string, label: string, cancel = false) => (
    <button type="button" className={cancel ? 'task-cancel' : undefined} onClick={() => onTaskAction(task.id, action)}>
      {label}
    </button>
  );
  if (status === 'running')
    return (
      <>
        {button('pause', '暂停')}
        {button('cancel', '取消', true)}
      </>
    );
  if (status === 'queued') return button('cancel', '取消', true);
  if (status === 'paused') return button('resume', '继续运行');
  if (status === 'success' || status === 'failed') return button('run', '重新运行');
  if (status === 'active')
    return (
      <>
        {button('run', '立即运行')}
        {button('pause', '暂停')}
      </>
    );
  return null;
}

export function TasksPanel({ tasks, onAddMonitor, onRefreshRecommend, onTaskAction }: Props) {
  const [creatorTarget, setCreatorTarget] = useState('');
  const [monitorInterval, setMonitorInterval] = useState('3600');
  const [recommendInterval, setRecommendInterval] = useState('3600');
  const [busy, setBusy] = useState(false);

  const submitMonitor = async (event: React.FormEvent) => {
    event.preventDefault();
    const target = creatorTarget.trim();
    if (!target) return;
    await onAddMonitor(target, Number(monitorInterval));
    setCreatorTarget('');
  };

  return (
    <div className="task-panel">
      <h2>对标监控</h2>
      <form className="compact-form" onSubmit={submitMonitor}>
        <label htmlFor="creatorTarget">博主主页或 ID</label>
        <input
          id="creatorTarget"
          type="text"
          placeholder="粘贴主页链接"
          required
          value={creatorTarget}
          onChange={(event) => setCreatorTarget(event.target.value)}
        />
        <label htmlFor="monitorInterval">检查周期</label>
        <select id="monitorInterval" value={monitorInterval} onChange={(event) => setMonitorInterval(event.target.value)}>
          <option value="1800">30 分钟</option>
          <option value="3600">1 小时</option>
          <option value="21600">6 小时</option>
          <option value="86400">每天</option>
        </select>
        <button type="submit" className="full">
          添加监控
        </button>
      </form>
      <div className="recommend-controls">
        <label htmlFor="recommendInterval">推荐流</label>
        <select
          id="recommendInterval"
          value={recommendInterval}
          onChange={(event) => setRecommendInterval(event.target.value)}
        >
          <option value="1800">每 30 分钟</option>
          <option value="3600">每小时</option>
          <option value="21600">每 6 小时</option>
        </select>
        <div className="button-pair">
          <button
            className="secondary"
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onRefreshRecommend();
              } finally {
                setBusy(false);
              }
            }}
          >
            立即刷新
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onRefreshRecommend(Number(recommendInterval));
              } finally {
                setBusy(false);
              }
            }}
          >
            定时刷新
          </button>
        </div>
      </div>

      <h2 className="recent-title">最近任务</h2>
      <div className="task-list">
        {tasks.length === 0 && <span>暂无任务</span>}
        {tasks.map((task) => {
          const status = effectiveStatus(task);
          const finished = ['success', 'failed', 'paused'].includes(status);
          return (
            <div className={`task-item ${finished ? 'task-item-muted' : ''}`} key={task.id}>
              <div className="task-head">
                <strong>{task.target || task.task_type}</strong>
                {task.new_content_count ? <span className="unread-count">{task.new_content_count} 新</span> : null}
              </div>
              <span className={`status-${status}`}>{statusLabel(status)}</span>
              <div className="task-actions">
                <TaskActions task={task} onTaskAction={onTaskAction} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
