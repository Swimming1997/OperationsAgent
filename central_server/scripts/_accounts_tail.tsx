  return (
    <section className="page-grid resource-grid">
      <aside className="filter-panel">
        <div className="panel-title">账号筛选</div>
        <label>平台</label>
        <select disabled><option>全部</option>{options?.platforms.map((item) => <option key={item.value}>{item.label}</option>)}</select>
        <button className="secondary" onClick={() => void reload()}><RefreshCw size={14} />刷新</button>
      </aside>
      <section className="list-panel">
        <div className="section-head">
          <div>
            <h1>账号管理</h1>
            <p className="ops-intro">添加运营账号并由本地 Agent 拉起浏览器完成平台登录，无需手工填写平台 ID。</p>
            <span>{accounts.length} 个运营账号</span>
          </div>
          <button type="button" onClick={openCreate}><Plus size={14} />添加运营账号</button>
        </div>
        {error && <ErrorState text={error} />}
        {loading ? <LoadingState text="账号加载中" /> : accounts.length === 0 ? <EmptyState text="暂无运营账号，点击右上角添加" /> : (
          <div className="data-table">
            <div className="table-row table-head account-row account-row-v2">
              <span>备注名</span><span>平台</span><span>登录态</span><span>运营态</span><span>Agent</span><span>验证时间</span>
            </div>
            {accounts.map((account) => (
              <button key={account.id} type="button" className={`table-row account-row account-row-v2 ${selected?.id === account.id ? 'selected' : ''}`} onClick={() => chooseAccount(account)}>
                <span className="strong">{account.display_name}</span>
                <span>{account.platform}</span>
                <span><span className={`auth-pill auth-${account.auth_status}`}>{labelAuthStatus(account.auth_status)}</span></span>
                <span>{account.status}</span>
                <span>{account.default_agent_device_name || '—'}</span>
                <span>{account.last_verified_at ? new Date(account.last_verified_at).toLocaleString('zh-CN') : '—'}</span>
              </button>
            ))}
          </div>
        )}
      </section>
      <aside className="detail-panel">
        <div className="panel-title">{selected ? '账号详情' : '添加运营账号'}</div>
        <div className="form-stack">
          <label>账号备注名</label>
          <input value={accountForm.display_name || ''} onChange={(event) => setAccountForm({ ...accountForm, display_name: event.target.value })} placeholder="如：XHS-账号A" />
          <label>平台</label>
          <select value={accountForm.platform || 'xhs'} onChange={(event) => setAccountForm({ ...accountForm, platform: event.target.value })}>{options?.platforms.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
          <ResourceSelect label="绑定员工" value={accountForm.employee_id} options={employeeOptions} onChange={(value) => setAccountForm({ ...accountForm, employee_id: value })} />
          <ResourceSelect label="绑定 Agent" value={accountForm.default_agent_id} options={agentOptions} onChange={(value) => setAccountForm({ ...accountForm, default_agent_id: value })} />
          <label>运营状态</label>
          <select value={accountForm.status || 'active'} onChange={(event) => setAccountForm({ ...accountForm, status: event.target.value })}>{options?.account_statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
          {selected ? (
            <div className="detail-section">
              <b>登录信息</b>
              <span>登录态：{labelAuthStatus(selected.auth_status)}</span>
              <span>Profile：{selected.profile_key || '—'}</span>
              <span>CDP 端口：{selected.login_cdp_port ?? '—'}</span>
              {selected.platform_nickname ? <span>平台昵称：{selected.platform_nickname}</span> : null}
            </div>
          ) : null}
          <button type="button" onClick={() => void saveAccount()} disabled={readonly || !accountForm.display_name}><Save size={14} />{selected ? '保存账号' : '创建账号'}</button>
        </div>
        {selected ? (
          <div className="login-session-panel">
            <div className="panel-title">平台登录</div>
            {showLoginPanel ? (
              <div className="login-session-card">
                <span className={`auth-pill auth-${selected.auth_status}`}>{labelAuthStatus(selected.auth_status)}</span>
                {loginSession ? <span>{labelLoginSessionStatus(loginSession.status)}</span> : null}
                {loginMessage ? <p className="login-hint">{loginMessage}</p> : null}
                {loginSession?.error_message ? <p className="inline-error">{loginSession.error_message}</p> : null}
                {loginSession?.status === 'waiting_agent' ? <p className="login-hint">等待本地 Agent 上线后将自动打开浏览器，请保持 Agent 运行。</p> : null}
                {loginSession?.status === 'waiting_user_login' ? <p className="login-hint">请在 Agent 打开的 Chrome 窗口完成小红书登录（扫码/验证码）。</p> : null}
              </div>
            ) : (
              <p className="login-hint">保存账号后，可发起登录由本地 Agent 创建独立 Profile 并打开浏览器。</p>
            )}
            <div className="detail-actions">
              <button type="button" disabled={loginBusy || selected.auth_status === 'active'} onClick={() => void handleStartLogin()}>
                <LogIn size={14} />
                {selected.auth_status === 'active' ? '已登录' : '发起登录'}
              </button>
              <button type="button" className="secondary" onClick={() => void reload()}><RefreshCw size={14} />刷新状态</button>
            </div>
          </div>
        ) : null}
        {role !== 'operator' ? (
          <div className="detail-section">
            <b>业务账号类型</b>
            <div className="mini-list">
              {types.map((item) => <button key={item.id} type="button" className="mini-row" onClick={() => setTypeForm(item)}>{item.name}<span>规则 {item.rule_set_count} / 对标组 {item.benchmark_group_count}</span></button>)}
            </div>
            <label>类型名称</label><input value={typeForm.name || ''} onChange={(event) => setTypeForm({ ...typeForm, name: event.target.value })} />
            <button type="button" onClick={() => void saveType()}><Save size={14} />保存类型</button>
          </div>
        ) : null}
      </aside>
    </section>
  );
}
