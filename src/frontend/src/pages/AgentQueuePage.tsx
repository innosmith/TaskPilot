import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useSSE } from '../hooks/useSSE';
import type { AgentJob } from '../types';

type FilterStatus = 'all' | 'active' | 'completed' | 'failed';

const STATUS_CONFIG: Record<
  AgentJob['status'],
  { label: string; color: string; bg: string }
> = {
  queued: { label: 'Wartend', color: 'text-amber-700', bg: 'bg-amber-100 dark:bg-amber-900/40 dark:text-amber-300' },
  running: { label: 'Läuft', color: 'text-blue-700', bg: 'bg-blue-100 dark:bg-blue-900/40 dark:text-blue-300' },
  awaiting_approval: { label: 'Prüfung', color: 'text-purple-700', bg: 'bg-purple-100 dark:bg-purple-900/40 dark:text-purple-300' },
  completed: { label: 'Erledigt', color: 'text-green-700', bg: 'bg-green-100 dark:bg-green-900/40 dark:text-green-300' },
  failed: { label: 'Fehler', color: 'text-red-700', bg: 'bg-red-100 dark:bg-red-900/40 dark:text-red-300' },
};

export function AgentQueuePage() {
  const [jobs, setJobs] = useState<AgentJob[]>([]);
  const [filter, setFilter] = useState<FilterStatus>('all');
  const [loading, setLoading] = useState(true);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    try {
      const data = await api.get<AgentJob[]>('/api/agent-jobs');
      setJobs(data);
    } catch { /* handled */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  useSSE((event) => {
    if (event === 'agent_jobs_changed') fetchJobs();
  });

  const handleApprove = async (jobId: string) => {
    await api.patch(`/api/agent-jobs/${jobId}`, { status: 'completed' });
    fetchJobs();
  };

  const handleReject = async (jobId: string) => {
    await api.patch(`/api/agent-jobs/${jobId}`, { status: 'failed', error_message: 'Vom Benutzer abgelehnt' });
    fetchJobs();
  };

  const filtered = jobs.filter((j) => {
    if (filter === 'all') return true;
    if (filter === 'active') return ['queued', 'running', 'awaiting_approval'].includes(j.status);
    if (filter === 'completed') return j.status === 'completed';
    if (filter === 'failed') return j.status === 'failed';
    return true;
  });

  const activeCount = jobs.filter((j) => ['queued', 'running', 'awaiting_approval'].includes(j.status)).length;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-3 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-gray-200 px-6 py-4 dark:border-gray-800">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">
            Agent Queue
          </h1>
          {activeCount > 0 && (
            <span className="flex items-center gap-1.5 rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
              <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
              {activeCount} aktiv
            </span>
          )}
        </div>
        <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
          Alle Agent-Aufträge und deren Status
        </p>
      </div>

      <div className="border-b border-gray-200 px-6 py-3 dark:border-gray-800">
        <div className="flex gap-2">
          {(['all', 'active', 'completed', 'failed'] as FilterStatus[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                filter === f
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'
              }`}
            >
              {{ all: 'Alle', active: 'Aktiv', completed: 'Erledigt', failed: 'Fehler' }[f]}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {filtered.length === 0 ? (
          <div className="flex h-48 items-center justify-center text-gray-400 dark:text-gray-600">
            <p>Keine Jobs gefunden</p>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((job) => {
              const cfg = STATUS_CONFIG[job.status];
              const isExpanded = expandedJobId === job.id;
              return (
                <div
                  key={job.id}
                  className="rounded-xl border border-gray-200 bg-white p-4 transition-shadow hover:shadow-md dark:border-gray-800 dark:bg-gray-900"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <button
                        onClick={() => setExpandedJobId(isExpanded ? null : job.id)}
                        className="text-left"
                      >
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                          {job.task_title || 'Unbenannter Task'}
                        </h3>
                      </button>
                      <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                        {new Date(job.created_at).toLocaleString('de-DE')}
                        {job.llm_model && ` · ${job.llm_model}`}
                        {job.tokens_used != null && ` · ${job.tokens_used} Tokens`}
                        {job.cost_usd != null && ` · $${job.cost_usd.toFixed(4)}`}
                      </p>
                    </div>
                    <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${cfg.bg}`}>
                      {cfg.label}
                    </span>
                  </div>

                  {job.status === 'awaiting_approval' && (
                    <div className="mt-3 flex gap-2">
                      <button
                        onClick={() => handleApprove(job.id)}
                        className="rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-green-700"
                      >
                        Akzeptieren
                      </button>
                      <button
                        onClick={() => handleReject(job.id)}
                        className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-red-700"
                      >
                        Ablehnen
                      </button>
                    </div>
                  )}

                  {isExpanded && (
                    <div className="mt-3 space-y-2 border-t border-gray-100 pt-3 dark:border-gray-800">
                      {job.output && (
                        <div>
                          <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400">Output</h4>
                          <div className="mt-1 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-sm text-gray-800 dark:bg-gray-800 dark:text-gray-200">
                            {job.output}
                          </div>
                        </div>
                      )}
                      {job.error_message && (
                        <div>
                          <h4 className="text-xs font-medium text-red-500">Fehler</h4>
                          <p className="mt-1 text-sm text-red-600 dark:text-red-400">{job.error_message}</p>
                        </div>
                      )}
                      {!job.output && !job.error_message && (
                        <p className="text-xs text-gray-400 italic">Noch kein Output vorhanden</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
