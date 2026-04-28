import { useState, useEffect, useCallback, useRef } from 'react';
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
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [cleanupOpen, setCleanupOpen] = useState(false);
  const cleanupRef = useRef<HTMLDivElement>(null);

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

  const handleDelete = async (jobId: string) => {
    await api.delete(`/api/agent-jobs/${jobId}`);
    setConfirmDeleteId(null);
    fetchJobs();
  };

  const handleCancel = async (jobId: string) => {
    await api.patch(`/api/agent-jobs/${jobId}`, { status: 'failed', error_message: 'Manuell abgebrochen' });
    setConfirmDeleteId(null);
    fetchJobs();
  };

  const handleBulkDelete = async (status: string, olderThanDays?: number) => {
    const params = new URLSearchParams({ status });
    if (olderThanDays != null) params.set('older_than_days', String(olderThanDays));
    await api.delete(`/api/agent-jobs/bulk?${params}`);
    setCleanupOpen(false);
    fetchJobs();
  };

  useEffect(() => {
    if (!cleanupOpen) return;
    const handle = (e: MouseEvent) => {
      if (cleanupRef.current && !cleanupRef.current.contains(e.target as Node)) setCleanupOpen(false);
    };
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [cleanupOpen]);

  const filtered = jobs.filter((j) => {
    if (filter === 'all') return true;
    if (filter === 'active') return ['queued', 'running', 'awaiting_approval'].includes(j.status);
    if (filter === 'completed') return j.status === 'completed';
    if (filter === 'failed') return j.status === 'failed';
    return true;
  });

  const activeCount = jobs.filter((j) => ['queued', 'running', 'awaiting_approval'].includes(j.status)).length;
  const runningCount = jobs.filter((j) => j.status === 'running').length;
  const completedCount = jobs.filter((j) => j.status === 'completed').length;
  const failedCount = jobs.filter((j) => j.status === 'failed').length;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-3 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-white/40 bg-white/50 px-6 py-4 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/50">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">
            Agenten
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

      <div className="border-b border-white/40 bg-white/50 px-6 py-3 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/50">
        <div className="flex items-center justify-between">
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
          {(completedCount > 0 || failedCount > 0 || runningCount > 0) && (
            <div className="relative" ref={cleanupRef}>
              <button
                onClick={() => setCleanupOpen(!cleanupOpen)}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
              >
                <TrashIcon className="h-3.5 w-3.5" />
                Aufräumen
              </button>
              {cleanupOpen && (
                <div className="absolute right-0 top-9 z-30 w-72 rounded-xl border border-gray-200 bg-white py-1 shadow-xl dark:border-gray-700 dark:bg-gray-900">
                  {runningCount > 0 && (
                    <>
                      <button
                        onClick={() => handleBulkDelete('stale')}
                        className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm text-amber-700 transition-colors hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-950/30"
                      >
                        <span>Hängende Jobs abbrechen</span>
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                          {runningCount}
                        </span>
                      </button>
                      <div className="mx-3 my-1 border-t border-gray-100 dark:border-gray-800" />
                    </>
                  )}
                  {completedCount > 0 && (
                    <button
                      onClick={() => handleBulkDelete('completed')}
                      className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800"
                    >
                      <span>Alle erledigten löschen</span>
                      <span className="rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-900/40 dark:text-green-300">
                        {completedCount}
                      </span>
                    </button>
                  )}
                  {failedCount > 0 && (
                    <button
                      onClick={() => handleBulkDelete('failed')}
                      className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800"
                    >
                      <span>Alle fehlgeschlagenen löschen</span>
                      <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-medium text-red-700 dark:bg-red-900/40 dark:text-red-300">
                        {failedCount}
                      </span>
                    </button>
                  )}
                  {completedCount > 0 && (
                    <button
                      onClick={() => handleBulkDelete('completed', 7)}
                      className="flex w-full items-center px-4 py-2.5 text-left text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800"
                    >
                      Erledigte älter als 7 Tage
                    </button>
                  )}
                  {(completedCount > 0 || failedCount > 0) && (
                    <>
                      <div className="mx-3 my-1 border-t border-gray-100 dark:border-gray-800" />
                      <button
                        onClick={() => handleBulkDelete('both')}
                        className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm text-red-600 transition-colors hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/30"
                      >
                        <span>Alles aufräumen</span>
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                          {completedCount + failedCount}
                        </span>
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
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
              const meta = (job.metadata_json ?? {}) as Record<string, string>;
              const jobTitle = _jobDisplayTitle(job, meta);
              const jobSubtitle = _jobSubtitle(job, meta);
              const jobTypeBadge = _jobTypeBadge(job);
              return (
                <div
                  key={job.id}
                  className="rounded-xl border border-white/60 bg-white/70 p-4 shadow-sm backdrop-blur-sm transition-shadow hover:shadow-md dark:border-gray-800 dark:bg-gray-900/70"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <button
                        onClick={() => setExpandedJobId(isExpanded ? null : job.id)}
                        className="text-left"
                      >
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                          {jobTitle}
                        </h3>
                      </button>
                      {jobSubtitle && (
                        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                          {jobSubtitle}
                        </p>
                      )}
                      <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
                        {new Date(job.created_at).toLocaleString('de-DE')}
                        {job.llm_model && ` · ${job.llm_model}`}
                        {job.tokens_used != null && ` · ${job.tokens_used} Tokens`}
                        {job.cost_usd != null && ` · $${job.cost_usd.toFixed(4)}`}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {jobTypeBadge && (
                        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${jobTypeBadge.classes}`}>
                          {jobTypeBadge.label}
                        </span>
                      )}
                      <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${cfg.bg}`}>
                        {cfg.label}
                      </span>
                      {(job.status === 'completed' || job.status === 'failed') && (
                        confirmDeleteId === job.id ? (
                          <span className="flex items-center gap-1">
                            <button
                              onClick={() => handleDelete(job.id)}
                              className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
                              title="Bestätigen"
                            >
                              Ja
                            </button>
                            <button
                              onClick={() => setConfirmDeleteId(null)}
                              className="rounded px-1.5 py-0.5 text-[10px] font-medium text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                            >
                              Nein
                            </button>
                          </span>
                        ) : (
                          <button
                            onClick={() => setConfirmDeleteId(job.id)}
                            className="rounded-lg p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-red-500 dark:hover:bg-gray-800 dark:hover:text-red-400"
                            title="Job löschen"
                          >
                            <TrashIcon className="h-3.5 w-3.5" />
                          </button>
                        )
                      )}
                      {(job.status === 'running' || job.status === 'queued') && (
                        confirmDeleteId === job.id ? (
                          <span className="flex items-center gap-1">
                            <button
                              onClick={() => handleCancel(job.id)}
                              className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
                              title="Abbrechen bestätigen"
                            >
                              Ja
                            </button>
                            <button
                              onClick={() => setConfirmDeleteId(null)}
                              className="rounded px-1.5 py-0.5 text-[10px] font-medium text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                            >
                              Nein
                            </button>
                          </span>
                        ) : (
                          <button
                            onClick={() => setConfirmDeleteId(job.id)}
                            className="rounded-lg p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-amber-600 dark:hover:bg-gray-800 dark:hover:text-amber-400"
                            title="Job abbrechen"
                          >
                            <StopIcon className="h-3.5 w-3.5" />
                          </button>
                        )
                      )}
                    </div>
                  </div>

                  {job.status === 'awaiting_approval' && (
                    <DraftPreviewInline
                      jobId={job.id}
                      meta={meta}
                      onApprove={() => handleApprove(job.id)}
                      onReject={() => handleReject(job.id)}
                    />
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

function _jobDisplayTitle(job: AgentJob, meta: Record<string, string>): string {
  if (job.job_type === 'email_triage') {
    const subject = meta.subject;
    if (subject) return subject;
    return 'E-Mail-Triage';
  }
  if (job.job_type === 'send_email') {
    return `E-Mail senden: ${meta.subject || '(kein Betreff)'}`;
  }
  return job.task_title || meta.subject || `Agent-Job: ${job.job_type || 'unbekannt'}`;
}

function _jobSubtitle(job: AgentJob, meta: Record<string, string>): string | null {
  if (job.job_type === 'email_triage') {
    const parts: string[] = [];
    if (meta.from_name || meta.from_address) {
      parts.push(`Von: ${meta.from_name || ''} ${meta.from_address ? `<${meta.from_address}>` : ''}`.trim());
    }
    if (meta.body_preview) {
      const preview = meta.body_preview.length > 120 ? meta.body_preview.slice(0, 120) + '…' : meta.body_preview;
      parts.push(preview);
    }
    return parts.join(' · ') || null;
  }
  if (job.job_type === 'send_email' && meta.to_recipients) {
    return `An: ${meta.to_recipients}`;
  }
  return null;
}

function _jobTypeBadge(job: AgentJob): { label: string; classes: string } | null {
  switch (job.job_type) {
    case 'email_triage':
      return { label: 'E-Mail Triage', classes: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300' };
    case 'send_email':
      return { label: 'E-Mail', classes: 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300' };
    case 'recurring':
      return { label: 'Recurring', classes: 'bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300' };
    default:
      return job.job_type
        ? { label: job.job_type, classes: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300' }
        : null;
  }
}

function TrashIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
    </svg>
  );
}

function StopIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 7.5A2.25 2.25 0 0 1 7.5 5.25h9a2.25 2.25 0 0 1 2.25 2.25v9a2.25 2.25 0 0 1-2.25 2.25h-9a2.25 2.25 0 0 1-2.25-2.25v-9Z" />
    </svg>
  );
}

interface DraftPreviewData {
  draft_id: string;
  subject: string | null;
  body_html: string | null;
  body_preview: string | null;
  to_recipients: string[];
  cc_recipients: string[];
  source_subject: string | null;
  source_from: string | null;
}

function DraftPreviewInline({
  jobId,
  meta,
  onApprove,
  onReject,
}: {
  jobId: string;
  meta: Record<string, string>;
  onApprove: () => void;
  onReject: () => void;
}) {
  const [preview, setPreview] = useState<DraftPreviewData | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [processing, setProcessing] = useState(false);
  const hasDraft = !!meta.draft_id;

  useEffect(() => {
    if (!hasDraft) return;
    setLoadingPreview(true);
    api.get<DraftPreviewData>(`/api/agent-jobs/${jobId}/draft-preview`)
      .then(setPreview)
      .catch(() => {})
      .finally(() => setLoadingPreview(false));
  }, [jobId, hasDraft]);

  const doApprove = async () => {
    setProcessing(true);
    try { await onApprove(); } finally { setProcessing(false); }
  };
  const doReject = async () => {
    setProcessing(true);
    try { await onReject(); } finally { setProcessing(false); }
  };

  return (
    <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800">
      {loadingPreview && (
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <div className="h-3 w-3 animate-spin rounded-full border border-gray-400 border-t-transparent" />
          Entwurf wird geladen...
        </div>
      )}

      {preview && (
        <div className="space-y-1.5">
          <div className="text-xs">
            <span className="font-medium text-gray-500 dark:text-gray-400">An: </span>
            <span className="text-gray-700 dark:text-gray-300">{preview.to_recipients.join(', ') || 'Unbekannt'}</span>
          </div>
          <div className="text-xs">
            <span className="font-medium text-gray-500 dark:text-gray-400">Betreff: </span>
            <span className="text-gray-700 dark:text-gray-300">{preview.subject || '(kein Betreff)'}</span>
          </div>
          {preview.body_html ? (
            <div className="mt-1 max-h-40 overflow-y-auto rounded border border-gray-200 bg-white p-2 dark:border-gray-600 dark:bg-gray-900">
              <div
                className="prose prose-sm max-w-none dark:prose-invert"
                dangerouslySetInnerHTML={{ __html: preview.body_html }}
              />
            </div>
          ) : preview.body_preview ? (
            <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">{preview.body_preview}</p>
          ) : null}
        </div>
      )}

      {!preview && !loadingPreview && !hasDraft && (
        <p className="text-xs text-gray-400 italic">Kein Entwurf verfügbar</p>
      )}

      <div className="mt-3 flex gap-2">
        <button
          onClick={doApprove}
          disabled={processing}
          className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-50"
        >
          {processing ? 'Wird gesendet...' : 'Freigeben & Senden'}
        </button>
        <button
          onClick={doReject}
          disabled={processing}
          className="rounded-lg border border-red-300 px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20 disabled:opacity-50"
        >
          Ablehnen & Löschen
        </button>
      </div>
    </div>
  );
}
