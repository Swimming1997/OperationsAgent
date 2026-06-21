import { api } from '../api';
import type { TaskItem } from '../types';

const TERMINAL = new Set(['success', 'failed', 'paused']);

export function effectiveStatus(task: TaskItem): string {
  if (task.status === 'active' && task.latest_run?.status === 'running') return 'running';
  if (task.status === 'active' && task.latest_run) return task.latest_run.status;
  return task.status;
}

export async function waitForTask(taskId: number, onTick?: (task: TaskItem) => void): Promise<TaskItem> {
  for (;;) {
    const task = await api<TaskItem>(`/api/local/tasks/${taskId}`);
    if (onTick) onTick(task);
    if (TERMINAL.has(effectiveStatus(task))) return task;
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
}
