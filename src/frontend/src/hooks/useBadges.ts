import { useState, useEffect, useCallback, useRef, createContext, useContext } from 'react';
import { api } from '../api/client';
import { useSSE } from './useSSE';
import type { AgentJob } from '../types';

export interface BadgeData {
  activeJobCount: number;
  unreadMailCount: number;
  pendingDecisions: number;
  focusTaskCount: number;
  unreadNotificationCount: number;
  refreshBadges: () => void;
}

const BadgeContext = createContext<BadgeData>({
  activeJobCount: 0,
  unreadMailCount: 0,
  pendingDecisions: 0,
  focusTaskCount: 0,
  unreadNotificationCount: 0,
  refreshBadges: () => {},
});

export const BadgeProvider = BadgeContext.Provider;

function updateAppBadge(count: number) {
  if ('setAppBadge' in navigator) {
    if (count > 0) {
      (navigator as any).setAppBadge(count).catch(() => {});
    } else {
      (navigator as any).clearAppBadge?.().catch(() => {});
    }
  }
}

export function useBadgeData(refreshKey: number): BadgeData {
  const [activeJobCount, setActiveJobCount] = useState(0);
  const [unreadMailCount, setUnreadMailCount] = useState(0);
  const [pendingDecisions, setPendingDecisions] = useState(0);
  const [focusTaskCount, setFocusTaskCount] = useState(0);
  const [unreadNotificationCount, setUnreadNotificationCount] = useState(0);

  const pendingRef = useRef(0);
  const notifRef = useRef(0);

  const refreshBadges = useCallback(() => {
    Promise.all([
      api.get<AgentJob[]>('/api/agent-jobs'),
      api.get<{ id: string }[]>('/api/tasks/pending-review').catch(() => [] as { id: string }[]),
    ]).then(([jobs, reviewTasks]) => {
      const active = jobs.filter((j) =>
        ['queued', 'running', 'awaiting_approval'].includes(j.status),
      );
      setActiveJobCount(active.length);
      const approvals = active.filter((j) => j.status === 'awaiting_approval').length;
      const total = approvals + reviewTasks.length;
      setPendingDecisions(total);
      pendingRef.current = total;
      updateAppBadge(total + notifRef.current);
    }).catch(() => {});

    api
      .get<{ unread_count?: number }>('/api/emails/unread-count')
      .then((r) => setUnreadMailCount(r.unread_count ?? 0))
      .catch(() => {});

    api
      .get<{ columns: { position: number; tasks: unknown[] }[] }>('/api/pipeline')
      .then((data) => {
        const focusCol = data.columns?.find((c) => c.position === 0) || data.columns?.[0];
        setFocusTaskCount(focusCol?.tasks?.length ?? 0);
      })
      .catch(() => {});

    api
      .get<{ count: number }>('/api/notifications/unread-count')
      .then((r) => {
        setUnreadNotificationCount(r.count);
        notifRef.current = r.count;
        updateAppBadge(pendingRef.current + r.count);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshBadges();
  }, [refreshKey, refreshBadges]);

  useSSE((event) => {
    if (event === 'agent_jobs_changed' || event === 'tasks_changed') {
      refreshBadges();
    } else if (event === 'email_triage_changed') {
      api
        .get<{ unread_count?: number }>('/api/emails/unread-count')
        .then((r) => setUnreadMailCount(r.unread_count ?? 0))
        .catch(() => {});
    } else if (event === 'notifications_changed') {
      api
        .get<{ count: number }>('/api/notifications/unread-count')
        .then((r) => {
          setUnreadNotificationCount(r.count);
          notifRef.current = r.count;
          updateAppBadge(pendingRef.current + r.count);
        })
        .catch(() => {});
    }
  });

  return { activeJobCount, unreadMailCount, pendingDecisions, focusTaskCount, unreadNotificationCount, refreshBadges };
}

export function useBadges(): BadgeData {
  return useContext(BadgeContext);
}
