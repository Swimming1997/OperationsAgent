import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { fetchQueueSummary, listOpsTaskRuns } from '../api/operations';
import type { Role } from '../types/api';
import { myRunsCreatedAfterIso } from '../utils/myRunsSort';
import {
  buildTrackedActiveRunIds,
  filterRelevantTaskRuns,
  findNewlyCompletedRunIds,
  hasGlobalActiveWork,
  isManagerRole,
  isTaskRunWatcherRole,
  type TaskRunViewer,
} from './taskRunRefresh';

const FAST_POLL_MS = 2000;
const IDLE_POLL_MS = 15000;

type TaskRunRefreshContextValue = {
  refreshGeneration: number;
  lastCompletedRunIds: string[];
  trackTaskRun: (taskRunId: string) => void;
};

const TaskRunRefreshContext = createContext<TaskRunRefreshContextValue | null>(null);

type Props = {
  role: Role;
  userId: string;
  employeeId: string | null;
  children: ReactNode;
};

export function TaskRunRefreshProvider({ role, userId, employeeId, children }: Props) {
  const [refreshGeneration, setRefreshGeneration] = useState(0);
  const [lastCompletedRunIds, setLastCompletedRunIds] = useState<string[]>([]);
  const trackedRunIdsRef = useRef<Set<string>>(new Set());
  const manualTrackedRef = useRef<Set<string>>(new Set());
  const globalActiveRef = useRef(false);

  const viewer = useMemo<TaskRunViewer>(
    () => ({ role, userId, employeeId }),
    [role, userId, employeeId],
  );

  const trackTaskRun = useCallback((taskRunId: string) => {
    if (!taskRunId) return;
    manualTrackedRef.current.add(taskRunId);
    trackedRunIdsRef.current.add(taskRunId);
  }, []);

  useEffect(() => {
    if (!isTaskRunWatcherRole(role)) return;

    let cancelled = false;
    let timer: number | undefined;

    const schedule = (delayMs: number) => {
      if (cancelled) return;
      timer = window.setTimeout(() => {
        void tick();
      }, delayMs);
    };

    const tick = async () => {
      if (cancelled) return;
      let nextDelay = IDLE_POLL_MS;
      try {
        if (isManagerRole(role)) {
          const summary = await fetchQueueSummary(role, userId);
          if (cancelled) return;
          globalActiveRef.current = hasGlobalActiveWork(summary) > 0;
        } else {
          globalActiveRef.current = false;
        }

        const activeRunsResponse = await listOpsTaskRuns(
          role,
          {
            has_active_jobs: true,
            page: 1,
            page_size: 100,
            created_after: isManagerRole(role) ? undefined : myRunsCreatedAfterIso(7),
          },
          userId,
        );
        if (cancelled) return;

        const relevantActive = isManagerRole(role)
          ? filterRelevantTaskRuns(activeRunsResponse.items, viewer)
          : activeRunsResponse.items;
        if (!isManagerRole(role) && relevantActive.length > 0) {
          globalActiveRef.current = true;
        }
        const previouslyTracked = trackedRunIdsRef.current;
        const completed = findNewlyCompletedRunIds(previouslyTracked, relevantActive);
        if (completed.length > 0) {
          for (const runId of completed) {
            manualTrackedRef.current.delete(runId);
          }
          trackedRunIdsRef.current = buildTrackedActiveRunIds(relevantActive, manualTrackedRef.current);
          setLastCompletedRunIds(completed);
          setRefreshGeneration((value) => value + 1);
        } else {
          trackedRunIdsRef.current = buildTrackedActiveRunIds(relevantActive, manualTrackedRef.current);
        }

        const shouldPollFast =
          globalActiveRef.current
          || trackedRunIdsRef.current.size > 0
          || manualTrackedRef.current.size > 0;
        nextDelay = shouldPollFast ? FAST_POLL_MS : IDLE_POLL_MS;
      } catch {
        nextDelay = IDLE_POLL_MS;
      }
      schedule(nextDelay);
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [role, userId, viewer]);

  const value = useMemo(
    () => ({
      refreshGeneration,
      lastCompletedRunIds,
      trackTaskRun,
    }),
    [refreshGeneration, lastCompletedRunIds, trackTaskRun],
  );

  return <TaskRunRefreshContext.Provider value={value}>{children}</TaskRunRefreshContext.Provider>;
}

export function useTaskRunRefresh() {
  return useContext(TaskRunRefreshContext);
}

export function useTaskRunRefreshEffect(
  effect: () => void | Promise<void>,
  deps: ReadonlyArray<unknown> = [],
) {
  const ctx = useTaskRunRefresh();
  const generation = ctx?.refreshGeneration ?? 0;

  useEffect(() => {
    if (generation <= 0) return;
    void effect();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- generation drives refresh; caller supplies other deps
  }, [generation, ...deps]);
}

export function useTrackTaskRunOnMount(taskRunId: string | null | undefined) {
  const ctx = useTaskRunRefresh();
  useEffect(() => {
    if (!taskRunId || !ctx) return;
    ctx.trackTaskRun(taskRunId);
  }, [taskRunId, ctx]);
}
