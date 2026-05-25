import { useEffect, useState } from 'react';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { Shell } from './components/Shell';
import { LoadingState } from './components/Status';
import { AccountsPage } from './pages/AccountsPage';
import { AgentsPage } from './pages/AgentsPage';
import { BenchmarksPage } from './pages/BenchmarksPage';
import { BootstrapAdminPage } from './pages/BootstrapAdminPage';
import { IntelligencePage } from './pages/IntelligencePage';
import { LoginPage } from './pages/LoginPage';
import { OrganizationPage } from './pages/OrganizationPage';
import { RulesPage } from './pages/RulesPage';
import { OperationsPage } from './pages/OperationsPage';
import { TasksPage } from './pages/TasksPage';
import { canAccessRoute } from './utils/roleLabels';
import './styles.css';

const routes = ['intelligence', 'tasks', 'operations', 'accounts', 'benchmarks', 'rules', 'agents', 'organization'];

function routeFromPath() {
  const segment = window.location.pathname.replace(/^\//, '').split('/')[0];
  return routes.includes(segment) ? segment : 'intelligence';
}

function taskRunIdFromSearch() {
  return new URLSearchParams(window.location.search).get('task_run') || undefined;
}

function AuthenticatedApp() {
  const auth = useAuth();
  const [route, setRoute] = useState(routeFromPath);
  const [opsTaskRunId, setOpsTaskRunId] = useState<string | undefined>(taskRunIdFromSearch);

  useEffect(() => {
    const onPop = () => {
      setRoute(routeFromPath());
      setOpsTaskRunId(taskRunIdFromSearch());
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  useEffect(() => {
    if (!canAccessRoute(route, auth.roles)) {
      setRoute('intelligence');
      window.history.replaceState({}, '', '/intelligence');
    }
  }, [route, auth.roles]);

  function changeRoute(nextRoute: string, params?: URLSearchParams) {
    if (!canAccessRoute(nextRoute, auth.roles)) return;
    setRoute(nextRoute);
    const path = params && params.toString() ? `/${nextRoute}?${params}` : `/${nextRoute}`;
    window.history.pushState({}, '', path);
    if (nextRoute === 'operations') {
      setOpsTaskRunId(params?.get('task_run') || undefined);
    }
  }

  const { role, userId } = auth;

  return (
    <Shell activeRoute={route} onRouteChange={changeRoute}>
      {route === 'tasks' && (
        <TasksPage
          role={role}
          userId={userId}
          onOpenOperations={(taskRunId) => {
            const params = new URLSearchParams();
            if (taskRunId) params.set('task_run', taskRunId);
            changeRoute('operations', params);
          }}
        />
      )}
      {route === 'operations' && (
        <OperationsPage
          role={role}
          userId={userId}
          initialTaskRunId={opsTaskRunId}
          onOpenTasks={() => changeRoute('tasks')}
        />
      )}
      {route === 'accounts' && <AccountsPage role={role} userId={userId} />}
      {route === 'benchmarks' && <BenchmarksPage role={role} userId={userId} />}
      {route === 'rules' && <RulesPage role={role} userId={userId} />}
      {route === 'agents' && <AgentsPage role={role} userId={userId} />}
      {route === 'organization' && <OrganizationPage role={role} userId={userId} />}
      {route === 'intelligence' && <IntelligencePage role={role} userId={userId} />}
    </Shell>
  );
}

function AppGate() {
  const auth = useAuth();

  if (auth.phase === 'loading') {
    return <LoadingState text="系统加载中" />;
  }
  if (auth.phase === 'bootstrap') {
    return <BootstrapAdminPage />;
  }
  if (auth.phase === 'login') {
    return <LoginPage />;
  }
  return <AuthenticatedApp />;
}

export function App() {
  return (
    <AuthProvider>
      <AppGate />
    </AuthProvider>
  );
}
