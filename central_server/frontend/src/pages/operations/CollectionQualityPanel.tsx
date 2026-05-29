import { useEffect, useState } from 'react';
import { fetchDataQualityOverview } from '../../api/intelligence';
import { LoadingState } from '../../components/Status';
import type { DataQualityOverview, Role } from '../../types/api';

type Props = {
  role: Role;
  userId: string;
};

export function CollectionQualityPanel({ role, userId }: Props) {
  const [open, setOpen] = useState(false);
  const [overview, setOverview] = useState<DataQualityOverview | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || overview) return;
    setLoading(true);
    fetchDataQualityOverview(role, userId)
      .then(setOverview)
      .catch(() => setOverview(null))
      .finally(() => setLoading(false));
  }, [open, overview, role, userId]);

  return (
    <section className="ops-quality-panel" data-testid="collection-quality-panel">
      <button type="button" className="secondary ops-quality-toggle" onClick={() => setOpen((value) => !value)}>
        {open ? '收起采集质量（近24h）' : '展开采集质量（近24h）'}
      </button>
      {open && (
        <div className="detail-body quality-grid-wrap">
          {loading ? (
            <LoadingState text="质量概览加载中" />
          ) : !overview ? (
            <span className="muted-hint">暂无质量概览</span>
          ) : (
            <>
              <div className="metric-grid quality-grid">
                <div>
                  <dt>今日新增内容</dt>
                  <dd>{overview.today_new_contents}</dd>
                </div>
                <div>
                  <dt>卡片层</dt>
                  <dd>{overview.today_card_count}</dd>
                </div>
                <div>
                  <dt>详情层</dt>
                  <dd>{overview.today_detail_count}</dd>
                </div>
                <div>
                  <dt>评论快照</dt>
                  <dd>{overview.today_comment_count}</dd>
                </div>
                <div>
                  <dt>入库数</dt>
                  <dd>{overview.today_reference_library_count}</dd>
                </div>
                <div>
                  <dt>详情补采成功率</dt>
                  <dd>
                    {overview.detail_fetch_success_rate != null
                      ? `${(overview.detail_fetch_success_rate * 100).toFixed(1)}%`
                      : '-'}
                  </dd>
                </div>
                <div>
                  <dt>评论补采成功率</dt>
                  <dd>
                    {overview.comment_fetch_success_rate != null
                      ? `${(overview.comment_fetch_success_rate * 100).toFixed(1)}%`
                      : '-'}
                  </dd>
                </div>
                <div>
                  <dt>发现位置完整率</dt>
                  <dd>{(overview.search_context_completeness_rate * 100).toFixed(1)}%</dd>
                </div>
                <div>
                  <dt>平台标签覆盖率</dt>
                  <dd>{(overview.platform_tags_coverage_rate * 100).toFixed(1)}%</dd>
                </div>
                <div>
                  <dt>重复发现内容数</dt>
                  <dd>{overview.multi_discovery_content_count}</dd>
                </div>
                <div>
                  <dt>异常账号数</dt>
                  <dd>{overview.abnormal_account_count}</dd>
                </div>
                <div>
                  <dt>补采失控风险</dt>
                  <dd>{overview.runaway_detail_fetch_risk ? '是' : '否'}</dd>
                </div>
              </div>
              <div className="detail-section">
                <b>说明</b>
                <span>{overview.filter_context_note}</span>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
