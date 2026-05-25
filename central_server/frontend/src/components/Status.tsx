export function LoadingState({ text = '加载中' }: { text?: string }) {
  return <div className="state state-loading">{text}</div>;
}

export function EmptyState({ text = '暂无数据' }: { text?: string }) {
  return <div className="state state-empty">{text}</div>;
}

export function ErrorState({ text }: { text: string }) {
  return <div className="state state-error">{text}</div>;
}
