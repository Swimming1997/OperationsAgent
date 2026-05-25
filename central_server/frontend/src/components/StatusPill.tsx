export function StatusPill({ status }: { status: string }) {
  const active = status === 'active';
  return <span className={`status-pill ${active ? 'active' : 'inactive'}`}>{active ? '启用' : '停用'}</span>;
}
