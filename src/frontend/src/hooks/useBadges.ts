import { useState, useEffect, useCallback, createContext, useContext } from 'react';
import { api } from '../api/client';
import { useSSE } from './useSSE';
import type { AgentJob } from '../types';

export interface BadgeData {
  activeJobCount: number;
  unreadMailCount: number;
  pendingDecisions: number;
  focusTaskCount: number;
  refreshBadges: () => void;
}

const BadgeContext = createContext<BadgeData>({
  activeJobCount: 0,
  unreadMailCount: 0,
  pendingDecisions: 0,
  focusTaskCount: 0,
  refreshBadges: () => {},
});

export const BadgeProvider = BadgeContext.Provider;

export function useBadgeData(refreshKey: number): BadgeData {
  const [activeJobCount, setActiveJobCount] = useState(0);
  const [unreadMailCount, setUnreadMailCount] = useState(0);
  const [pendingDecisions, setPendingDecisions] = useState(0);
  const [focusTaskCount, setFocusTaskCount] = useState(0);

  const refreshBadges = useCallback(() => {
    api
      .get<AgentJob[]>('/api/agent-jobs')
      .then((jobs) => {
        const active = jobs.filter((j) =>
          ['queued', 'running', 'awaiting_approval'].includes(j.status),
        );
        setActiveJobCount(active.length);
        setPendingDecisions(active.filter((j) => j.status === 'awaiting_approval').length);
      })
      .catch(() => {});

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
  }, []);

  useEffect(() => {
    refreshBadges();
  }, [refreshKey, refreshBadges]);

  useSSE((event) => {
    if (event === 'agent_jobs_changed') {
      refreshBadges();
    } else if (event === 'email_triage_changed') {
      api
        .get<{ unread_count?: number }>('/api/emails/unread-count')
        .then((r) => setUnreadMailCount(r.unread_count ?? 0))
        .catch(() => {});
    } else if (event === 'tasks_changed') {
      api
        .get<{ columns: { position: number; tasks: unknown[] }[] }>('/api/pipeline')
        .then((data) => {
          const focusCol = data.columns?.find((c) => c.position === 0) || data.columns?.[0];
          setFocusTaskCount(focusCol?.tasks?.length ?? 0);
        })
        .catch(() => {});
    }
  });

  return { activeJobCount, unreadMailCount, pendingDecisions, focusTaskCount, refreshBadges };
}

export function useBadges(): BadgeData {
  return useContext(BadgeContext);
}
