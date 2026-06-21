import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { establishBridgeSession } from './bridge';
import { useToast } from './ui/ToastContext';
import type { CentralSession } from './types';
import { Workspace } from './workspace/Workspace';
import { CommentsPage } from './workspace/CommentsPage';
import { CentralLoginDialog } from './workspace/CentralLoginDialog';
import { AccountsPage } from './accounts/AccountsPage';

type Tab = 'workspace' | 'comments' | 'accounts';

export default function App() {
  const toast = useToast();
  const [tab, setTab] = useState<Tab>('workspace');
  const [centralSession, setCentralSession] = useState<CentralSession | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [statusText, setStatusText] = useState('本地数据');
  const loginSuccessCb = useRef<null | (() => void)>(null);

  const reloadCentral = useCallback(async () => {
    const session = await api<CentralSession>('/api/local/central-session');
    setCentralSession(session);
    return session;
  }, []);

  useEffect(() => {
    establishBridgeSession()
      .then(() => reloadCentral())
      .catch((error: Error) => toast(error.message));
  }, [reloadCentral, toast]);

  const openCentralLogin = useCallback((onSuccess?: () => void) => {
    loginSuccessCb.current = onSuccess || null;
    setLoginOpen(true);
  }, []);

  const handleCentralButton = useCallback(async () => {
    if (centralSession?.authenticated) {
      await api('/api/local/central-session/logout', { method: 'POST', body: '{}' });
      await reloadCentral();
      toast('已退出中央素材库');
    } else {
      openCentralLogin();
    }
  }, [centralSession, openCentralLogin, reloadCentral, toast]);

  const centralButtonLabel = centralSession?.authenticated
    ? centralSession.user?.display_name || centralSession.user?.username || '已登录'
    : '登录中央';

  return (
    <>
      <header className="topbar">
        <div>
          <h1>运营情报工作台</h1>
          <p>{statusText}</p>
        </div>
        <div className="top-actions">
          <button className="secondary" type="button" onClick={handleCentralButton}>
            {centralButtonLabel}
          </button>
          <button className="secondary" type="button" onClick={() => setRefreshSignal((value) => value + 1)}>
            刷新
          </button>
        </div>
      </header>

      <nav className="primary-nav">
        <button type="button" className={tab === 'workspace' ? 'active' : ''} onClick={() => setTab('workspace')}>
          工作台
        </button>
        <button type="button" className={tab === 'comments' ? 'active' : ''} onClick={() => setTab('comments')}>
          评论搜索
        </button>
        <button type="button" className={tab === 'accounts' ? 'active' : ''} onClick={() => setTab('accounts')}>
          账号管理
        </button>
      </nav>

      <main>
        <div hidden={tab !== 'workspace'}>
          <Workspace
            active={tab === 'workspace'}
            refreshSignal={refreshSignal}
            centralSession={centralSession}
            reloadCentralSession={reloadCentral}
            openCentralLogin={openCentralLogin}
            onStatusText={setStatusText}
          />
        </div>
        <div hidden={tab !== 'comments'}>
          <CommentsPage active={tab === 'comments'} refreshSignal={refreshSignal} />
        </div>
        {tab === 'accounts' && <AccountsPage refreshSignal={refreshSignal} />}
      </main>

      <CentralLoginDialog
        open={loginOpen}
        defaultCenterUrl={centralSession?.center_url || ''}
        onClose={() => setLoginOpen(false)}
        onSuccess={(session) => {
          setCentralSession(session);
          setLoginOpen(false);
          toast('中央素材库登录成功');
          const cb = loginSuccessCb.current;
          loginSuccessCb.current = null;
          if (cb) cb();
        }}
      />
    </>
  );
}
