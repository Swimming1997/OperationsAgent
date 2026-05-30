import { useEffect, useState } from 'react';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { TaskRunRefreshProvider } from './context/TaskRunRefreshContext';
import { Shell } from './components/Shell';
import { LoadingState } from './components/Status';
import { AccountsPage } from './pages/AccountsPage';
import { AgentsPage } from './pages/AgentsPage';
import { BenchmarksPage } from './pages/BenchmarksPage';
import { BootstrapAdminPage } from './pages/BootstrapAdminPage';
import { BenchmarkLibraryPage } from './pages/BenchmarkLibraryPage';
import { IntelligencePage } from './pages/IntelligencePage';
import { LoginPage } from './pages/LoginPage';
import { OrganizationPage } from './pages/OrganizationPage';
import { RulesPage } from './pages/RulesPage';
import { MyRunsPage } from './pages/MyRunsPage';
import { OperationsPage } from './pages/OperationsPage';
import { TasksPage } from './pages/TasksPage';
import { canAccessRoute } from './utils/roleLabels';
import './styles.css';

const routes = ['intelligence', 'reference-library', 'tasks', 'my-runs', 'operations', 'accounts', 'benchmarks', 'rules', 'agents', 'organization'];

function routeFromPath() {
  const segment = window.location.pathname.replace(/^\//, '').split('/')[0];
  return routes.includes(segment) ? segment : 'intelligence';
}

function taskRunIdFromSearch() {
  return new URLSearchParams(window.location.search).get('task_run') || undefined;
}

function jobIdFromSearch() {
  return new URLSearchParams(window.location.search).get('job_id') || undefined;
}

function intelligenceContentIdFromSearch() {
  return new URLSearchParams(window.location.search).get('content_id') || undefined;
}

function AuthenticatedApp() {
  const auth = useAuth();
  const [route, setRoute] = useState(routeFromPath);
  const [opsTaskRunId, setOpsTaskRunId] = useState<string | undefined>(taskRunIdFromSearch);
  const [opsJobId, setOpsJobId] = useState<string | undefined>(jobIdFromSearch);
  const [intelligenceContentId, setIntelligenceContentId] = useState<string | undefined>(intelligenceContentIdFromSearch);

  useEffect(() => {
    const onPop = () => {
      setRoute(routeFromPath());
      setOpsTaskRunId(taskRunIdFromSearch());
      setOpsJobId(jobIdFromSearch());
      setIntelligenceContentId(intelligenceContentIdFromSearch());
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
    if (nextRoute === 'operations' || nextRoute === 'my-runs') {
      setOpsTaskRunId(params?.get('task_run') || undefined);
      setOpsJobId(params?.get('job_id') || undefined);
    }
  }

  const { role, userId, employeeId } = auth;

  return (
    <TaskRunRefreshProvider role={role} userId={userId} employeeId={employeeId}>
    <Shell activeRoute={route} onRouteChange={changeRoute}>
      {route === 'tasks' && (
        <TasksPage
          role={role}
          userId={userId}
          onOpenOperations={(taskRunId) => {
            const params = new URLSearchParams();
            if (taskRunId) params.set('task_run', taskRunId);
            changeRoute(role === 'operator' ? 'my-runs' : 'operations', params);
          }}
        />
      )}
      {route === 'my-runs' && (
        <MyRunsPage role={role} userId={userId} initialTaskRunId={opsTaskRunId} />
      )}
      {route === 'operations' && (
        <OperationsPage
          role={role}
          userId={userId}
          initialTaskRunId={opsTaskRunId}
          initialJobId={opsJobId}
          onOpenTasks={() => changeRoute('tasks')}
        />
      )}
      {route === 'accounts' && <AccountsPage role={role} userId={userId} />}
      {route === 'benchmarks' && <BenchmarksPage role={role} userId={userId} />}
      {route === 'rules' && <RulesPage role={role} userId={userId} />}
      {route === 'agents' && <AgentsPage role={role} userId={userId} />}
      {route === 'organization' && <OrganizationPage role={role} userId={userId} />}
      {route === 'intelligence' && (
        <IntelligencePage
          role={role}
          userId={userId}
          initialContentId={intelligenceContentId}
          onOpenReferenceLibrary={(contentId, itemId) => {
            const params = new URLSearchParams();
            if (itemId) params.set('item_id', itemId);
            else params.set('content_id', contentId);
            changeRoute('reference-library', params);
          }}
          onOpenOperationsJob={(jobId) => {
            const params = new URLSearchParams();
            params.set('job_id', jobId);
            changeRoute('operations', params);
          }}
          onOpenRules={() => changeRoute('rules')}
        />
      )}
      {route === 'reference-library' && (
        <BenchmarkLibraryPage
          role={role}
          userId={userId}
          onOpenIntelligencePool={(contentId) => {
            const params = new URLSearchParams();
            if (contentId) params.set('content_id', contentId);
            changeRoute('intelligence', params);
          }}
          onOpenRules={() => changeRoute('rules')}
        />
      )}
    </Shell>
    </TaskRunRefreshProvider>
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
