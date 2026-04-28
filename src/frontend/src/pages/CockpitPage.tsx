import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { BackgroundPicker } from '../components/BackgroundPicker';
import { useSSE } from '../hooks/useSSE';
import type { AgentJob, TaskCard } from '../types';

interface DraftPreview {
  draft_id: string;
  subject: string | null;
  body_html: string | null;
  body_preview: string | null;
  to_recipients: string[];
  cc_recipients: string[];
  source_subject: string | null;
  source_from: string | null;
}

interface PendingReviewTask {
  id: string;
  title: string;
  project_id: string;
  project_name: string;
  source_email_subject: string | null;
  source_email_from: string | null;
  needs_review: boolean;
}

interface ProjectOption {
  id: string;
  name: string;
  color: string;
}

interface TriageStats {
  by_status: Record<string, number>;
  by_class: Record<string, number>;
  total_pending: number;
}

const JOB_TYPE_LABELS: Record<string, string> = {
  email_triage: 'E-Mail-Triage',
  draft_email_reply: 'Antwort-Entwurf',
  create_task_from_email: 'Aufgabe erstellen',
  quick_response: 'Schnellantwort',
};

function FormattedOutput({ output }: { output: string }) {
  try {
    const parsed = JSON.parse(output);
    if (parsed.body_html) {
      return <div className="prose prose-sm max-w-none dark:prose-invert" dangerouslySetInnerHTML={{ __html: parsed.body_html }} />;
    }
    if (parsed.body || parsed.text || parsed.message) {
      return <p className="whitespace-pre-wrap">{parsed.body || parsed.text || parsed.message}</p>;
    }
    if (parsed.draft_id || parsed.subject) {
      return (
        <div className="space-y-1">
          {parsed.subject && <p><span className="font-medium">Betreff:</span> {parsed.subject}</p>}
          {parsed.to && <p><span className="font-medium">An:</span> {Array.isArray(parsed.to) ? parsed.to.join(', ') : parsed.to}</p>}
          {parsed.body_preview && <p className="mt-2 whitespace-pre-wrap">{parsed.body_preview}</p>}
          {parsed.rationale && <p className="mt-2 italic">{parsed.rationale}</p>}
        </div>
      );
    }
    const relevantKeys = Object.entries(parsed).filter(([k]) => !['id', 'draft_id', 'conversation_id'].includes(k));
    if (relevantKeys.length > 0) {
      return (
        <div className="space-y-1">
          {relevantKeys.map(([key, val]) => (
            <p key={key}>
              <span className="font-medium capitalize">{key.replace(/_/g, ' ')}:</span>{' '}
              {typeof val === 'string' ? val : JSON.stringify(val)}
            </p>
          ))}
        </div>
      );
    }
  } catch {
    // not JSON
  }
  if (output.includes('<') && output.includes('>')) {
    return <div className="prose prose-sm max-w-none dark:prose-invert" dangerouslySetInnerHTML={{ __html: output }} />;
  }
  return <p className="whitespace-pre-wrap">{output}</p>;
}

export function CockpitPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [bgUrl, setBgUrl] = useState<string | null>(null);
  const [bgPickerOpen, setBgPickerOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [approvalJobs, setApprovalJobs] = useState<AgentJob[]>([]);
  const [activeJobs, setActiveJobs] = useState<AgentJob[]>([]);
  const [focusTasks, setFocusTasks] = useState<TaskCard[]>([]);
  const [pendingReview, setPendingReview] = useState<PendingReviewTask[]>([]);
  const [triageStats, setTriageStats] = useState<TriageStats | null>(null);

  const [previews, setPreviews] = useState<Record<string, DraftPreview>>({});
  const [loadingPreviews, setLoadingPreviews] = useState<Set<string>>(new Set());
  const [failedPreviews, setFailedPreviews] = useState<Set<string>>(new Set());
  const [processing, setProcessing] = useState<Set<string>>(new Set());

  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [editingProject, setEditingProject] = useState<Record<string, string>>({});

  const fetchData = useCallback(async () => {
    try {
      const [settingsData, jobsData, tasksData, reviewData, triageData, projectData] = await Promise.all([
        api.get<{ cockpit_background_url: string | null }>('/api/settings'),
        api.get<AgentJob[]>('/api/agent-jobs'),
        api.get<TaskCard[]>('/api/tasks/due-today').catch(() => [] as TaskCard[]),
        api.get<PendingReviewTask[]>('/api/tasks/pending-review').catch(() => [] as PendingReviewTask[]),
        api.get<TriageStats>('/api/triage/stats').catch(() => null),
        api.get<ProjectOption[]>('/api/projects'),
      ]);

      setBgUrl(settingsData.cockpit_background_url);
      setProjects(projectData);

      const awaitingApproval = jobsData.filter(j => j.status === 'awaiting_approval');
      const active = jobsData.filter(j => ['queued', 'running'].includes(j.status));
      setApprovalJobs(awaitingApproval);
      setActiveJobs(active);
      setFocusTasks(tasksData);
      setPendingReview(reviewData);
      setTriageStats(triageData);
    } catch { /* */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  useSSE('agent_jobs_changed', fetchData);

  useEffect(() => {
    for (const job of approvalJobs) {
      if (!previews[job.id] && !loadingPreviews.has(job.id) && !failedPreviews.has(job.id)) {
        setLoadingPreviews(prev => new Set(prev).add(job.id));
        api.get<DraftPreview>(`/api/agent-jobs/${job.id}/draft-preview`)
          .then(preview => {
            setPreviews(prev => ({ ...prev, [job.id]: preview }));
          })
          .catch(() => {
            setFailedPreviews(prev => new Set(prev).add(job.id));
          })
          .finally(() => {
            setLoadingPreviews(prev => {
              const next = new Set(prev);
              next.delete(job.id);
              return next;
            });
          });
      }
    }
  }, [approvalJobs, previews, loadingPreviews, failedPreviews]);

  useEffect(() => {
    if (!settingsOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setSettingsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [settingsOpen]);

  const handleBgSelect = async (url: string | null) => {
    await api.patch('/api/settings', { cockpit_background_url: url });
    setBgUrl(url);
  };

  const handleApprove = async (jobId: string) => {
    setProcessing(prev => new Set(prev).add(jobId));
    try {
      await api.patch(`/api/agent-jobs/${jobId}`, { status: 'completed' });
      fetchData();
    } catch { /* */ }
    finally { setProcessing(prev => { const n = new Set(prev); n.delete(jobId); return n; }); }
  };

  const handleReject = async (jobId: string) => {
    setProcessing(prev => new Set(prev).add(jobId));
    try {
      await api.patch(`/api/agent-jobs/${jobId}`, { status: 'failed', error_message: 'Vom Benutzer abgelehnt' });
      fetchData();
    } catch { /* */ }
    finally { setProcessing(prev => { const n = new Set(prev); n.delete(jobId); return n; }); }
  };

  const handleConfirmTask = async (task: PendingReviewTask) => {
    try {
      const newProjectId = editingProject[task.id];
      const body: Record<string, string> = {};
      if (newProjectId && newProjectId !== task.project_id) body.project_id = newProjectId;
      await api.post(`/api/tasks/${task.id}/confirm`, body);
      fetchData();
    } catch { /* */ }
  };

  const handleDismissTask = async (taskId: string) => {
    try {
      await api.delete(`/api/tasks/${taskId}`);
      fetchData();
    } catch { /* */ }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-3 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  const hasBg = !!bgUrl;
  const isGradient = bgUrl?.startsWith('gradient:') ?? false;
  const bgStyle = isGradient
    ? { background: bgUrl!.slice('gradient:'.length) }
    : hasBg
      ? { backgroundImage: `url(${bgUrl})`, backgroundSize: 'cover', backgroundPosition: 'center' }
      : undefined;

  const cardClass = hasBg
    ? 'bg-white/10 backdrop-blur-md border-white/20 text-white'
    : 'bg-white border-gray-200 dark:bg-gray-900 dark:border-gray-800';

  const textPrimary = hasBg ? 'text-white' : 'text-gray-900 dark:text-white';
  const textSecondary = hasBg ? 'text-white/70' : 'text-gray-500 dark:text-gray-400';
  const textMuted = hasBg ? 'text-white/50' : 'text-gray-400 dark:text-gray-500';

  const pendingDecisions = approvalJobs.length + pendingReview.length;

  return (
    <div className="relative flex h-full flex-col" style={bgStyle}>
      {hasBg && !isGradient && <div className="absolute inset-0 bg-black/10 dark:bg-black/30" />}
      {isGradient && <div className="absolute inset-0 bg-black/5 dark:bg-black/20" />}

      {/* Header */}
      <div className={`relative z-20 border-b px-6 py-4 ${hasBg ? 'border-white/10 bg-black/20 backdrop-blur-sm' : 'border-gray-200 dark:border-gray-800'}`}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className={`text-xl font-bold ${textPrimary}`}>Cockpit</h1>
            <p className={`mt-0.5 text-sm ${textSecondary}`}>
              Dein Überblick — Entscheidungen, Agenten und Fokus-Aufgaben
            </p>
          </div>
          <div className="relative" ref={settingsRef}>
            <button
              onClick={() => setSettingsOpen(!settingsOpen)}
              className={`rounded-lg p-2 transition-colors ${
                hasBg
                  ? 'text-white/70 hover:bg-white/10 hover:text-white'
                  : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300'
              }`}
              title="Cockpit-Einstellungen"
            >
              <SettingsGearIcon className="h-5 w-5" />
            </button>
            {settingsOpen && (
              <div className="absolute right-0 top-10 z-50 w-52 rounded-xl border border-gray-200 bg-white py-1 shadow-xl dark:border-gray-700 dark:bg-gray-900">
                <button
                  onClick={() => { setBgPickerOpen(true); setSettingsOpen(false); }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800"
                >
                  <ImageIcon className="h-4 w-4" />
                  Hintergrundbild ändern
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Inhalt */}
      <div className="relative z-10 flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-5xl space-y-6">

          {/* KPI-Übersicht */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <KpiCard
              label="Entscheidungen"
              value={pendingDecisions}
              accent="rose"
              hasBg={hasBg}
            />
            <KpiCard
              label="Aktive Agenten"
              value={activeJobs.length}
              accent="indigo"
              hasBg={hasBg}
            />
            <KpiCard
              label="Fokus-Aufgaben"
              value={focusTasks.length}
              accent="amber"
              hasBg={hasBg}
            />
            <KpiCard
              label="E-Mails in Triage"
              value={triageStats?.total_pending ?? 0}
              accent="emerald"
              hasBg={hasBg}
            />
          </div>

          {/* Freigaben (Approvals) */}
          {approvalJobs.length > 0 && (
            <section>
              <h2 className={`mb-3 text-sm font-semibold uppercase tracking-wider ${textSecondary}`}>
                Freigaben
              </h2>
              <div className="space-y-3">
                {approvalJobs.map(job => {
                  const meta = (job.metadata_json || {}) as Record<string, string>;
                  const preview = previews[job.id];
                  const isLoading = loadingPreviews.has(job.id);
                  const isProcessing = processing.has(job.id);
                  const hasFailed = failedPreviews.has(job.id);

                  return (
                    <div key={job.id} className={`rounded-xl border p-5 ${cardClass}`}>
                      <div className="flex items-center gap-3 mb-3">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-100/80 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                          <MailDraftIcon className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className={`text-base font-semibold truncate ${textPrimary}`}>
                              {preview?.subject || meta.subject || 'E-Mail-Entwurf'}
                            </span>
                            <span className="shrink-0 rounded-full bg-amber-100 px-2.5 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                              Freigabe nötig
                            </span>
                          </div>
                          <div className={`mt-0.5 text-sm ${textSecondary}`}>
                            An: {preview?.to_recipients?.join(', ') || meta.from_address || 'Unbekannt'}
                          </div>
                        </div>
                      </div>

                      {meta.subject && (
                        <div className={`mb-3 rounded-lg px-3 py-2 text-xs ${hasBg ? 'bg-white/10' : 'bg-gray-50 dark:bg-gray-800/50'} ${textMuted}`}>
                          <span className="font-medium">Antwort auf:</span> {meta.subject}
                          {(meta.from_address || meta.from_name) && (
                            <span> — von {meta.from_name || meta.from_address}</span>
                          )}
                        </div>
                      )}

                      {isLoading && (
                        <div className={`mb-3 flex items-center gap-2 text-sm ${textMuted}`}>
                          <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-transparent" />
                          Entwurf wird geladen…
                        </div>
                      )}

                      {preview?.body_html && (
                        <div className={`mb-3 rounded-lg border overflow-hidden ${hasBg ? 'border-white/20 bg-white/5' : 'border-gray-200 bg-white dark:border-gray-600 dark:bg-gray-800'}`}>
                          <div className={`border-b px-4 py-2 ${hasBg ? 'border-white/10' : 'border-gray-100 dark:border-gray-700'}`}>
                            <span className={`text-xs font-medium ${textMuted}`}>E-Mail-Entwurf</span>
                          </div>
                          <div className="max-h-56 overflow-y-auto px-4 py-3">
                            <div
                              className="prose prose-sm max-w-none dark:prose-invert"
                              dangerouslySetInnerHTML={{ __html: preview.body_html }}
                            />
                          </div>
                        </div>
                      )}

                      {!preview?.body_html && preview?.body_preview && (
                        <div className={`mb-3 rounded-lg border p-4 text-sm ${hasBg ? 'border-white/20 bg-white/5' : 'border-gray-200 bg-white dark:border-gray-600 dark:bg-gray-800'} ${textPrimary}`}>
                          <div className={`mb-1 text-xs font-medium ${textMuted}`}>E-Mail-Entwurf</div>
                          {preview.body_preview}
                        </div>
                      )}

                      {!preview && hasFailed && job.output && (
                        <div className={`mb-3 rounded-lg border p-3 ${hasBg ? 'border-white/20 bg-white/5' : 'border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800'}`}>
                          <div className={`mb-1 text-xs font-medium ${textMuted}`}>Agent-Output</div>
                          <div className={`text-sm max-h-40 overflow-y-auto ${textSecondary}`}>
                            <FormattedOutput output={job.output} />
                          </div>
                        </div>
                      )}

                      {!preview && !hasFailed && !isLoading && job.output && (
                        <div className={`mb-3 rounded-lg border p-3 ${hasBg ? 'border-white/20 bg-white/5' : 'border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800'}`}>
                          <div className={`mb-1 text-xs font-medium ${textMuted}`}>Entwurf-Vorschau</div>
                          <div className={`text-sm max-h-40 overflow-y-auto ${textSecondary}`}>
                            <FormattedOutput output={job.output} />
                          </div>
                        </div>
                      )}

                      <div className="flex gap-2">
                        <button
                          onClick={() => handleApprove(job.id)}
                          disabled={isProcessing}
                          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                        >
                          {isProcessing ? 'Wird gesendet…' : 'Freigeben & Senden'}
                        </button>
                        <button
                          onClick={() => handleReject(job.id)}
                          disabled={isProcessing}
                          className="rounded-lg border border-red-300 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20 disabled:opacity-50"
                        >
                          Ablehnen
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* Aufgaben-Vorschläge */}
          {pendingReview.length > 0 && (
            <section>
              <h2 className={`mb-3 text-sm font-semibold uppercase tracking-wider ${textSecondary}`}>
                Aufgaben-Vorschläge
              </h2>
              <div className="space-y-3">
                {pendingReview.map(task => (
                  <div key={task.id} className={`rounded-xl border p-4 ${cardClass}`}>
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-100/80 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                        <TaskIcon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className={`font-medium truncate ${textPrimary}`}>{task.title}</div>
                        {task.source_email_subject && (
                          <div className={`text-xs truncate ${textMuted}`}>
                            Aus E-Mail: {task.source_email_subject}
                          </div>
                        )}
                      </div>
                      <select
                        value={editingProject[task.id] || task.project_id}
                        onChange={e => setEditingProject(prev => ({ ...prev, [task.id]: e.target.value }))}
                        className="rounded-lg border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300"
                      >
                        {projects.map(p => (
                          <option key={p.id} value={p.id}>{p.name}</option>
                        ))}
                      </select>
                      <button
                        onClick={() => handleConfirmTask(task)}
                        className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700"
                      >
                        Übernehmen
                      </button>
                      <button
                        onClick={() => handleDismissTask(task.id)}
                        className="rounded-lg px-3 py-1.5 text-xs font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                      >
                        Verwerfen
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Aktive Agenten + Fokus-Aufgaben – nebeneinander */}
          {(activeJobs.length > 0 || focusTasks.length > 0) && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {/* Aktive Agenten */}
              {activeJobs.length > 0 && (
                <section>
                  <h2 className={`mb-3 text-sm font-semibold uppercase tracking-wider ${textSecondary}`}>
                    Aktive Agenten
                  </h2>
                  <div className="space-y-2">
                    {activeJobs.map(job => {
                      const meta = (job.metadata_json || {}) as Record<string, string>;
                      const jobLabel = JOB_TYPE_LABELS[job.job_type || ''] || job.job_type || 'Agent-Job';
                      const subject = meta.subject || job.task_title;
                      return (
                        <div
                          key={job.id}
                          className={`flex items-center gap-3 rounded-xl border p-3 cursor-pointer transition-colors hover:ring-1 hover:ring-indigo-300 ${cardClass}`}
                          onClick={() => navigate('/agenten')}
                        >
                          <div className={`h-2.5 w-2.5 rounded-full shrink-0 ${
                            job.status === 'running' ? 'bg-blue-500 animate-pulse' : 'bg-amber-500'
                          }`} />
                          <div className="min-w-0 flex-1">
                            <div className={`text-sm font-medium truncate ${textPrimary}`}>
                              {jobLabel}{subject ? `: ${subject}` : ''}
                            </div>
                            <div className={`text-xs ${textMuted}`}>
                              {job.status === 'running' ? 'Läuft' : 'Wartend'}
                              {job.started_at && ` — seit ${new Date(job.started_at).toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' })}`}
                            </div>
                          </div>
                          <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                            job.status === 'running'
                              ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                              : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
                          }`}>
                            {job.status === 'running' ? 'Läuft' : 'Wartend'}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {/* Fokus-Aufgaben */}
              {focusTasks.length > 0 && (
                <section>
                  <h2 className={`mb-3 text-sm font-semibold uppercase tracking-wider ${textSecondary}`}>
                    Heute fällige Aufgaben
                  </h2>
                  <div className="space-y-2">
                    {focusTasks.map(task => {
                      const overdue = task.due_date && new Date(task.due_date) < new Date();
                      const meta = (task as Record<string, unknown>);
                      const projectName = typeof meta.project_name === 'string' ? meta.project_name : '';
                      return (
                        <div
                          key={task.id}
                          className={`flex items-center gap-3 rounded-xl border p-3 ${cardClass}`}
                        >
                          <div className={`h-2.5 w-2.5 rounded-full shrink-0 ${overdue ? 'bg-red-500' : 'bg-amber-400'}`} />
                          <div className="min-w-0 flex-1">
                            <div className={`text-sm font-medium truncate ${textPrimary}`}>
                              {task.title}
                            </div>
                            {projectName && (
                              <div className={`text-xs truncate ${textMuted}`}>{projectName}</div>
                            )}
                          </div>
                          {task.due_date && (
                            <span className={`shrink-0 text-xs ${overdue ? 'text-red-500 font-medium' : textMuted}`}>
                              {overdue ? 'Überfällig' : 'Heute'}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}
            </div>
          )}

          {/* Alles erledigt */}
          {pendingDecisions === 0 && activeJobs.length === 0 && focusTasks.length === 0 && (
            <div className={`flex flex-col items-center justify-center rounded-xl border p-12 ${cardClass}`}>
              <CheckCircleIcon className={`h-12 w-12 mb-3 ${hasBg ? 'text-white/40' : 'text-emerald-300 dark:text-emerald-700'}`} />
              <p className={`text-lg font-medium ${textPrimary}`}>Alles erledigt</p>
              <p className={`mt-1 text-sm ${textSecondary}`}>
                Keine offenen Entscheidungen oder fälligen Aufgaben.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Background Picker */}
      <BackgroundPicker
        isOpen={bgPickerOpen}
        onClose={() => setBgPickerOpen(false)}
        currentUrl={bgUrl}
        onSelect={(url) => { handleBgSelect(url); setBgPickerOpen(false); }}
      />
    </div>
  );
}

/* ── KPI Card ── */

function KpiCard({
  label,
  value,
  accent,
  hasBg,
}: {
  label: string;
  value: number;
  accent: 'rose' | 'indigo' | 'amber' | 'emerald';
  hasBg: boolean;
}) {
  const accentMap = {
    rose: { text: 'text-rose-600 dark:text-rose-400', bg: 'bg-rose-100 dark:bg-rose-900/40' },
    indigo: { text: 'text-indigo-600 dark:text-indigo-400', bg: 'bg-indigo-100 dark:bg-indigo-900/40' },
    amber: { text: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-100 dark:bg-amber-900/40' },
    emerald: { text: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-100 dark:bg-emerald-900/40' },
  };

  const a = accentMap[accent];

  return (
    <div className={`rounded-xl border p-4 ${
      hasBg
        ? 'bg-white/10 backdrop-blur-md border-white/20'
        : 'bg-white border-gray-200 dark:bg-gray-900 dark:border-gray-800'
    }`}>
      <div className={`text-3xl font-bold ${hasBg ? 'text-white' : a.text}`}>
        {value}
      </div>
      <div className={`mt-1 text-xs font-medium ${hasBg ? 'text-white/60' : 'text-gray-500 dark:text-gray-400'}`}>
        {label}
      </div>
    </div>
  );
}

/* ── Icons ── */

function SettingsGearIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.431.992a7.723 7.723 0 0 1 0 .255c-.007.378.138.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
    </svg>
  );
}

function ImageIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5a2.25 2.25 0 0 0 2.25-2.25V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z" />
    </svg>
  );
}

function MailDraftIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  );
}

function TaskIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
    </svg>
  );
}

function CheckCircleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
    </svg>
  );
}
