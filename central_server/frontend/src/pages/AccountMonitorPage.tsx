import { RefreshCw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { listAccountMonitor } from '../api/resources';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { AccountMonitorRow, Role } from '../types/api';

type Props = { role: Role; userId: string };

const PLATFORM_LABELS: Record<string, string> = { xhs: '小红书', douyin: '抖音' };
const AUTH_LABELS: Record<string, string> = {
  not_logged_in: '未登录',
  login_pending: '登录中',
  active: '已登录',
  error: '登录失败',
  expired: '已过期',
};
const HEALTH_LABELS: Record<string, string> = {
  unknown: '未知',
  healthy: '健康',
  warning: '告警',
  blocked: '受限',
};

function platformLabel(value: string) {
  return PLATFORM_LABELS[value] || value;
}

function formatTime(value: string | null) {
  if (!value) return '-';
  const time = Date.parse(value);
  if (Number.isNaN(time)) return '-';
  return new Date(time).toLocaleString();
}

export function AccountMonitorPage({ role, userId }: Props) {
  const [rows, setRows] = useState<AccountMonitorRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, userId]);

  async function reload() {
    setLoading(true);
    setError('');
    try {
      const data = await listAccountMonitor(role, userId);
      setRows(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : '账号监控加载失败');
    } finally {
      setLoading(false);
    }
  }

  const summary = useMemo(() => {
    const total = rows.length;
    const active = rows.filter((row) => row.auth_status === 'active').length;
    const agents = new Set(rows.map((row) => row.agent_id)).size;
    return { total, active, agents };
  }, [rows]);

  return (
    <section className="page-grid">
      <section className="list-panel">
        <div className="section-head">
          <div>
            <h1>账号监控</h1>
            <span>
              {summary.agents} 台 Agent · {summary.total} 个账号 · {summary.active} 已登录（只读镜像，由各员工本地上报）
            </span>
          </div>
          <button className="secondary" onClick={reload}>
            <RefreshCw size={14} />
            刷新
          </button>
        </div>
        {error && <ErrorState text={error} />}
        {loading ? (
          <LoadingState text="账号监控加载中" />
        ) : rows.length === 0 ? (
          <EmptyState text="暂无账号上报。员工在本地工作台添加并登录账号后，会自动同步到这里。" />
        ) : (
          <div className="data-table">
            <div className="table-row table-head account-monitor-row">
              <span>员工 / 设备</span>
              <span>平台</span>
              <span>账号</span>
              <span>登录态</span>
              <span>健康度</span>
              <span>连续失败</span>
              <span>最近校验</span>
              <span>上报时间</span>
            </div>
            {rows.map((row) => (
              <div key={row.id} className="table-row account-monitor-row">
                <span className="strong">
                  {row.employee_display_name || '未绑定'}
                  <small className="muted-line">{row.agent_device_name || row.agent_id.slice(0, 8)}</small>
                </span>
                <span>
                  <b className="tag">{platformLabel(row.platform)}</b>
                </span>
                <span>{row.platform_nickname || row.display_name || '未命名账号'}</span>
                <span>
                  <b className={`tag auth-${row.auth_status}`}>{AUTH_LABELS[row.auth_status] || row.auth_status}</b>
                </span>
                <span>{HEALTH_LABELS[row.health_status] || row.health_status}</span>
                <span>{row.consecutive_failures || 0}</span>
                <span>{formatTime(row.last_verified_at)}</span>
                <span>{formatTime(row.reported_at)}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}
