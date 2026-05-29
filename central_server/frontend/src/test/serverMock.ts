import { vi } from 'vitest';
import { agents, behaviorProfiles, benchmarkGroups, businessTypes, intelligenceList, networkProfiles, options, platformAccounts, productDetail, readinessBlocked, readinessReady, referenceLibraryItems, riskPolicies, ruleSets, taskDetail, taskList, taskRun } from './mockData';
import { operationsJobDetail, operationsJobs, operationsSummary, operationsTaskRunDetail, operationsTaskRuns } from './operationsMockData';

type FetchMockConfig = {
  blockedReadiness?: boolean;
  failRun?: boolean;
  orgUsers?: Array<Record<string, unknown>>;
  orgEmployees?: Array<Record<string, unknown>>;
  authUserId?: string;
  authUsername?: string;
  authDisplayName?: string;
  authRoles?: string[];
  authEmployeeId?: string | null;
};

export function installFetchMock(config: FetchMockConfig = {}) {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  const scenarioFilterStore = new Map<string, Record<string, unknown>>();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    requests.push({ url, init });
    if (url.includes('/api/auth/bootstrap-status')) {
      return json({ users_count: 1, admin_exists: true, needs_bootstrap: false });
    }
    if (url.includes('/api/auth/me')) {
      return json({
        id: config.authUserId ?? 'supervisor-user',
        username: config.authUsername ?? 'supervisor',
        display_name: config.authDisplayName ?? '演示主管',
        email: null,
        status: 'active',
        roles: config.authRoles ?? ['supervisor'],
        employee_id: config.authEmployeeId ?? null,
      });
    }
    if (url.includes('/api/auth/login') || url.includes('/api/auth/bootstrap-admin') || url.includes('/api/auth/register')) {
      return json({
        access_token: 'test-token',
        token_type: 'bearer',
        user: {
          id: 'supervisor-user',
          username: 'supervisor',
          display_name: '演示主管',
          email: null,
          status: 'active',
          roles: ['supervisor'],
          employee_id: null,
        },
      });
    }
    if (/^http:\/\/127\.0\.0\.1:\d+\/healthz$/.test(url)) {
      return json({ status: 'ok' });
    }
    if (url.includes('/bridge/agents/discover')) {
      const portMatch = url.match(/127\.0\.0\.1:(\d+)/);
      const port = portMatch ? Number(portMatch[1]) : 18765;
      return json({
        items: [{
          device_name: 'WIN-AGENT',
          machine_fingerprint: 'fp',
          agent_id: 'agent-1',
          center_url: 'http://127.0.0.1:8000',
          bridge_url: `http://127.0.0.1:${port}`,
          status: 'online',
        }],
      });
    }
    if (url.includes('http://127.0.0.1:18765/bridge/chrome/start')) {
      return json({
        account_id: 'account-1',
        profile_key: 'accounts/account-1',
        profile_dir: 'profiles/accounts/account-1',
        cdp_url: 'http://127.0.0.1:9222',
        pid: 12345,
        message: 'chrome started',
      });
    }
    if (url.includes('/bridge/accounts/account-1/session-status') || url.includes('/bridge/accounts/account-1/revalidate')) {
      return json({
        account_id: 'account-1',
        status: 'ready',
        message: 'xhs session ready',
        cdp_url: 'http://127.0.0.1:9222',
        platform_nickname: '测试昵称',
        platform_home_url: 'https://www.xiaohongshu.com/explore',
      });
    }
    if (url.includes('/api/users') && (!init?.method || init.method === 'GET')) {
      return json(config.orgUsers ?? []);
    }
    if (url.includes('/api/users') && init?.method === 'POST') {
      return json(config.orgUsers?.[0] ?? {
        id: 'user-new',
        username: 'newuser',
        display_name: '新用户',
        email: null,
        status: 'active',
        roles: ['operator'],
        employee_id: null,
      });
    }
    if (url.includes('/api/employees/with-user')) {
      return json({
        id: 'emp-new',
        user_id: 'user-new',
        display_name: '新员工',
        email: null,
        status: 'active',
        user_username: 'newuser',
        account_count: 0,
        agent_count: 0,
      });
    }
    if (url.includes('/api/product/options')) return json(options);
    if (url.includes('/bridge-chrome-context') && init?.method === 'POST') {
      return json({ account_id: 'account-1', profile_key: 'accounts/account-1', login_cdp_port: 9301 });
    }
    if (url.includes('/sync-local-login') && init?.method === 'POST') {
      return json({
        account_id: 'account-1',
        auth_status: 'active',
        message: '本机会话已同步到中央，账号登录态已更新为可用',
      });
    }
    if (url.includes('/login-sessions/active')) return json(null);
    if (url.includes('/login-sessions/reset') && init?.method === 'POST') {
      return json({ account_id: 'account-1', auth_status: 'not_logged_in', message: '登录态已重置为未登录，可重新发起登录' });
    }
    if (url.includes('/login-sessions') && init?.method === 'POST') {
      return json({
        session: {
          id: 'login-session-1',
          platform_account_id: 'account-1',
          agent_id: 'agent-1',
          status: 'waiting_user_login',
          error_message: null,
          profile_key: 'accounts/account-1',
          cdp_port: 9300,
          claimed_by_agent_id: 'agent-1',
          claimed_at: '2026-05-19T01:00:00Z',
          started_at: '2026-05-19T01:00:00Z',
          finished_at: null,
          expires_at: '2026-05-19T01:15:00Z',
        },
        message: '浏览器已打开，请在 Chrome 中完成小红书登录',
      });
    }
    if (url.includes('/api/product/accounts')) return json(init?.method === 'PATCH' || init?.method === 'POST' ? platformAccounts[0] : platformAccounts);
    if (url.includes('/api/business-account-types/type-1/rule-sets')) return json([{ id: 'bind-1', business_account_type_id: 'type-1', rule_set_id: 'rule-set-1', rule_set_name: 'SCI 关键词', is_default: false }]);
    if (url.includes('/api/business-account-types') && init?.method === 'DELETE') return new Response(null, { status: 204 });
    if (url.includes('/api/business-account-types')) return json(init?.method === 'PATCH' || init?.method === 'POST' ? businessTypes[0] : businessTypes);
    if (url.includes('/api/product/me/local-agents/resolve-discover') && init?.method === 'POST') {
      const body = init.body ? JSON.parse(String(init.body)) : { items: [] };
      const item = body.items?.[0];
      const agent = agents.find((row) => row.machine_fingerprint === item?.machine_fingerprint) || agents[0];
      return json([{ agent: { ...agent, last_heartbeat_at: new Date().toISOString() }, bridge_port: item?.bridge_port ?? 18765 }]);
    }
    if (url.includes('/api/local-agents/') && init?.method === 'PATCH') {
      const body = init.body ? JSON.parse(String(init.body)) : {};
      const agentId = url.split('/api/local-agents/')[1]?.split('?')[0] || 'agent-1';
      const base = agents.find((item) => item.id === agentId) || agents[0];
      const employee = (config.orgEmployees ?? [{ id: 'employee-1', display_name: '运营一组' }]).find((item) => item.id === body.employee_id);
      return json({
        ...base,
        employee_id: body.employee_id ?? null,
        employee_display_name: employee?.display_name ?? null,
        last_heartbeat_at: new Date().toISOString(),
      });
    }
    if (url.includes('/api/local-agents/agent-1')) {
      return json({ ...agents[0], last_heartbeat_at: new Date().toISOString() });
    }
    if (url.includes('/api/local-agents')) {
      return json(agents.map((agent) => ({ ...agent, last_heartbeat_at: new Date().toISOString() })));
    }
    if (url.includes('/api/employees') && (!init?.method || init.method === 'GET')) {
      return json(config.orgEmployees ?? [{ id: 'employee-1', user_id: 'operator-user', display_name: '运营一组', email: null, status: 'active', user_username: 'operator', account_count: 0, agent_count: 0 }]);
    }
    if (url.includes('/api/benchmark-groups/group-1/members')) return json(init?.method === 'POST' ? { id: 'member-2', benchmark_group_id: 'group-1', platform: 'xhs', enabled: true } : [{ id: 'member-1', benchmark_group_id: 'group-1', creator_monitor_id: 'monitor-1', platform: 'xhs', creator_platform_id: 'creator-1', creator_profile_url: null, display_name: '对标作者', platform_context: {}, enabled: true }]);
    if (url.includes('/api/benchmark-groups/group-1/business-account-types')) return json(init?.method === 'POST' ? { binding_id: 'gbind-1' } : [{ id: 'gbind-1', benchmark_group_id: 'group-1', business_account_type_id: 'type-1', business_account_type_name: '论文服务号' }]);
    if (url.includes('/api/benchmark-groups') && init?.method === 'DELETE') return new Response(null, { status: 204 });
    if (url.includes('/api/benchmark-groups')) return json(init?.method === 'PATCH' || init?.method === 'POST' ? benchmarkGroups[0] : benchmarkGroups);
    if (url.includes('/api/operation-rules')) {
      const operationRule = {
        id: 'op-rule-1',
        rule_type: 'title',
        title: '标题控制',
        content: '小红书标题建议不超过 20 字',
        platform: 'xhs',
        enabled: true,
        version: 1,
        created_by_user_id: 'supervisor-user',
        created_at: '2026-05-19T01:00:00Z',
        updated_at: '2026-05-19T01:00:00Z',
      };
      if (init?.method === 'DELETE') return new Response(null, { status: 204 });
      if (init?.method === 'POST' || init?.method === 'PATCH') return json(operationRule);
      return json([operationRule]);
    }
    if (url.includes('/api/keyword-rule-sets/rule-set-1/rules')) return json(init?.method === 'POST' ? { id: 'rule-2', rule_set_id: 'rule-set-1', keyword: '投稿', normalized_keyword: null, match_mode: 'contains', enabled: true, weight: 1 } : [{ id: 'rule-1', rule_set_id: 'rule-set-1', keyword: 'SCI', normalized_keyword: 'sci', match_mode: 'contains', enabled: true, weight: 2 }]);
    if (url.includes('/api/keyword-rule-sets') && init?.method === 'DELETE') return new Response(null, { status: 204 });
    if (url.includes('/api/keyword-rule-sets')) return json(init?.method === 'PATCH' || init?.method === 'POST' ? ruleSets[0] : ruleSets);
    if (url.includes('/api/keyword-rules')) return json({ id: 'rule-1', rule_set_id: 'rule-set-1', keyword: 'SCI', normalized_keyword: 'sci', match_mode: 'contains', enabled: true, weight: 2 });
    if (url.includes('/api/behavior-profiles')) return json(behaviorProfiles);
    if (url.includes('/api/network-egress-profiles')) return json(networkProfiles);
    if (url.includes('/api/risk-policies')) return json(riskPolicies);
    if (url.includes('/api/media/cover/')) {
      const gif = Uint8Array.from(atob('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'), (char) => char.charCodeAt(0));
      return Promise.resolve(new Response(gif, { status: 200, headers: { 'Content-Type': 'image/gif' } }));
    }
    if (url.includes('/api/product/me/intelligence/scenario-filters')) {
      const scenarioMatch = url.match(/scenario-filters\/([^/?]+)/);
      if (scenarioMatch && init?.method === 'PUT') {
        const scenario = scenarioMatch[1];
        const body = JSON.parse(String(init.body || '{}'));
        scenarioFilterStore.set(scenario, {
          scenario,
          filters: body.filters || {},
          rolling: body.rolling || {},
          updated_at: '2026-05-30T00:00:00.000Z',
          is_user_customized: true,
        });
        return json(scenarioFilterStore.get(scenario));
      }
      if (scenarioMatch && init?.method === 'DELETE') {
        scenarioFilterStore.delete(scenarioMatch[1]);
        return new Response(null, { status: 204 });
      }
      if (scenarioMatch) {
        const saved = scenarioFilterStore.get(scenarioMatch[1]);
        if (!saved) return new Response(JSON.stringify({ detail: 'not found' }), { status: 404 });
        return json(saved);
      }
      return json({ items: Array.from(scenarioFilterStore.values()) });
    }
    if (url.includes('/api/intelligence/contents/product')) return json(intelligenceList);
    if (url.includes('/api/intelligence/data-quality/overview')) {
      return json({
        generated_at: '2026-05-19T01:00:00Z',
        window_hours: 24,
        today_new_contents: 12,
        today_card_count: 3,
        today_detail_count: 8,
        today_comment_count: 5,
        today_reference_library_count: 2,
        detail_fetch_success_rate: 0.8,
        comment_fetch_success_rate: 0.6,
        search_context_completeness_rate: 0.72,
        platform_tags_coverage_rate: 0.35,
        multi_discovery_content_count: 4,
        abnormal_account_count: 0,
        runaway_detail_fetch_risk: false,
        filter_context_note: '当前只能记录 requested filter，尚不能证明 Local Agent 已实际点选小红书筛选控件。',
      });
    }
    if (url.includes('/api/reference-library/items/re-evaluate') && init?.method === 'POST') {
      return json({
        results: [{
          content_id: 'content-1',
          item_id: 'ref-1',
          status: 'skipped_manual_locked',
          library_type: 'non_lead',
          rating: 'poor',
          reason: '人工锁定，规则重评已跳过',
        }],
      });
    }
    if (url.includes('/api/intelligence/contents/') && url.includes('/reference-library-items') && init?.method === 'POST') {
      return json(referenceLibraryItems[0]);
    }
    if (url.includes('/api/intelligence/contents/bulk-status') && init?.method === 'POST') {
      return json({ succeeded: [productDetail.workflow_state], failed: [] });
    }
    if (url.includes('/api/intelligence/contents/content-1/manual-tags') && init?.method === 'PATCH') {
      return json({ content_id: 'content-1', manual_tags: ['稍后看', '可仿写'] });
    }
    if (url.includes('/api/intelligence/contents/content-1/enqueue-detail-fetch') && init?.method === 'POST') {
      return json({ job_id: 'job-detail-1', job_type: 'detail_fetch', status: 'pending' });
    }
    if (url.includes('/api/intelligence/contents/content-1/enqueue-comment-fetch') && init?.method === 'POST') {
      return json({ job_id: 'job-comment-1', job_type: 'comment_fetch', status: 'pending' });
    }
    if (url.includes('/api/reference-library/items/bulk')) return json({ succeeded: referenceLibraryItems, failed: [] });
    if (url.includes('/api/reference-library/items/ref-1/events')) return json([
      { id: 'event-ref-1', library_item_id: 'ref-1', content_id: 'content-1', event_type: 'created', user_id: 'supervisor-user', employee_id: null, event_payload: {}, created_at: '2026-05-19T01:00:00Z' },
    ]);
    if (url.includes('/api/reference-library/items/ref-1/archive')) return json({ ...referenceLibraryItems[0], status: 'archived', usage_status: 'archived' });
    if (url.includes('/api/reference-library/items/ref-1') && init?.method === 'PATCH') {
      const body = init.body ? JSON.parse(String(init.body)) : {};
      return json({ ...referenceLibraryItems[0], ...body });
    }
    if (url.includes('/api/reference-library/items')) return json({ items: referenceLibraryItems, page: 1, page_size: 20, total: referenceLibraryItems.length });
    if (url.includes('/api/intelligence/contents/content-1/product-detail')) return json(productDetail);
    if (url.includes('/api/intelligence/contents/content-1/assign')) return json(productDetail.workflow_state);
    if (url.includes('/api/intelligence/contents/content-1/select')) return json({ ...productDetail.workflow_state, workflow_status: 'selected' });
    if (url.includes('/api/intelligence/contents/content-1/discard')) return json({ ...productDetail.workflow_state, workflow_status: 'discarded' });
    if (url.includes('/api/intelligence/contents/content-1/archive')) return json({ ...productDetail.workflow_state, workflow_status: 'archived' });
    if (url.includes('/api/intelligence/contents/content-1/notes')) return json(productDetail.notes[0]);
    if (url.includes('/api/task-templates/list')) return json(taskList);
    if (url.includes('/api/task-templates/task-1/readiness')) return json(config.blockedReadiness ? readinessBlocked : readinessReady);
    if (url.includes('/api/task-templates/task-1/runs')) return json({ items: [taskRun] });
    if (url.includes('/api/task-runs/run-1')) return json(taskRun);
    if (url.includes('/api/task-templates/task-1/run')) {
      if (config.failRun) return jsonError({ detail: readinessBlocked }, 409);
      return json({ task_run_id: 'run-1', task_template_id: 'task-1', jobs_created: 1, jobs: [{ job_id: 'job-1', job_type: 'feed_collect', status: 'pending' }], readiness: readinessReady });
    }
    if (url.includes('/api/task-templates/task-1')) return json(taskDetail);
    if (url.includes('/api/task-templates/recommendation-feed')) return json(taskDetail);
    if (url.includes('/api/task-templates/creator-monitor')) return json({ ...taskDetail, id: 'task-2', template_type: 'creator_monitor_task', typed_payload: { executor_account_id: 'account-1', benchmark_group_id: 'group-1', auto_detail_fetch: true } });
    if (url.includes('/api/task-templates/keyword-search')) return json({ ...taskDetail, id: 'task-3', template_type: 'keyword_search_task', typed_payload: { executor_account_id: 'account-1', platform: 'xhs', keywords: ['论文'], max_items: 50 } });
    if (url.includes('/api/operations/queue-summary')) return json(operationsSummary);
    if (url.includes('/api/operations/task-runs/run-1')) return json(operationsTaskRunDetail);
    if (url.includes('/api/operations/task-runs')) return json({ items: operationsTaskRuns, total: operationsTaskRuns.length, page: 1, page_size: 30 });
    if (url.includes('/api/operations/jobs/job-comment-1')) return json(operationsJobDetail);
    if (url.includes('/api/operations/jobs')) return json({ items: operationsJobs, total: operationsJobs.length, page: 1, page_size: 80 });
    if (url.includes('/api/operations/jobs/fail-stale-running')) return json({ affected_count: 2, job_ids: [], message: '已将 2 个超时执行项标记为失败' });
    if (url.includes('/api/operations/jobs/cleanup-legacy-pending')) return json({ affected_count: 5, job_ids: [], message: '预览：5 个历史遗留待执行项' });
    return json({});
  });
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, requests };
}

function json(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }));
}

function jsonError(body: unknown, status: number) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
}
