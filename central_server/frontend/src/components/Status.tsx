export function LoadingState({ text = '加载中' }: { text?: string }) {
  return <div className="state state-loading">{text}</div>;
}

import type { ReactNode } from 'react';

export function EmptyState({ text = '暂无数据', action }: { text?: string; action?: ReactNode }) {
  return (
    <div className="state state-empty">
      <p>{text}</p>
      {action}
    </div>
  );
}

export function ErrorState({ text }: { text: string }) {
  return <div className="state state-error">{text}</div>;
}
