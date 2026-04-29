import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { BackgroundPicker } from '../components/BackgroundPicker';
import { CrmBadge } from '../components/CrmBadge';
import { DraftEditor } from '../components/DraftEditor';
import { TaskDetailDialog } from '../components/TaskDetailDialog';
import { TracePanel } from '../components/TracePanel';
import { useSSE } from '../hooks/useSSE';
import type { AgentJob, TaskCard, PipelineData } from '../types';

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

interface CalendarEvent {
  id: string;
  subject: string | null;
  start: string | null;
  end: string | null;
  is_all_day: boolean;
  location: string | null;
  show_as: string | null;
  attendees_count: number;
  is_organizer: boolean;
  categories: string[];
}

interface FlaggedEmail {
  id: string;
  subject: string | null;
  from_address: string | null;
  from_name: string | null;
  received_at: string | null;
  body_preview: string | null;
  importance: string | null;
  has_attachments: boolean;
}

interface CockpitSettings {
  cockpit_background_url: string | null;
  cockpit_calendar_exclude_categories: string | null;
  cockpit_calendar_hide_private: boolean | null;
}

interface PipedriveLeadSummary {
  id: string;
  title: string;
  person_id: number | null;
  person_name: string | null;
  organization_id: number | null;
  org_name: string | null;
  expected_close_date: string | null;
  value: number | null;
  currency: string | null;
}

interface PipedriveDealSummary {
  id: number;
  title: string;
  status: string | null;
  value: number | null;
  currency: string | null;
  stage_id: number | null;
  person_name: string | null;
  org_name: string | null;
}

interface PipedriveActivitySummary {
  id: number;
  subject: string;
  type: string | null;
  done: boolean | null;
  due_date: string | null;
  deal_id: number | null;
  person_name: string | null;
}

const JOB_TYPE_LABELS: Record<string, string> = {
  email_triage: 'E-Mail-Triage',
  draft_email_reply: 'Antwort-Entwurf',
  create_task_from_email: 'Aufgabe erstellen',
  auto_reply: 'Auto-Antwort',
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

function formatTime(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z');
  return d.toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' });
}

function relativeDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'Gerade eben';
  if (diffMin < 60) return `Vor ${diffMin} Min.`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `Vor ${diffH} Std.`;
  const diffD = Math.floor(diffH / 24);
  return `Vor ${diffD} Tag${diffD > 1 ? 'en' : ''}`;
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
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [flaggedEmails, setFlaggedEmails] = useState<FlaggedEmail[]>([]);
  const [recentJobs, setRecentJobs] = useState<AgentJob[]>([]);

  const [pipedriveDeals, setPipedriveDeals] = useState<PipedriveDealSummary[]>([]);
  const [pipedriveLeads, setPipedriveLeads] = useState<PipedriveLeadSummary[]>([]);
  const [pipedriveActivities, setPipedriveActivities] = useState<PipedriveActivitySummary[]>([]);
  const [pipedriveConnected, setPipedriveConnected] = useState(false);

  const [previews, setPreviews] = useState<Record<string, DraftPreview>>({});
  const [loadingPreviews, setLoadingPreviews] = useState<Set<string>>(new Set());
  const [failedPreviews, setFailedPreviews] = useState<Set<string>>(new Set());
  const [processing, setProcessing] = useState<Set<string>>(new Set());
  const [editingJobId, setEditingJobId] = useState<string | null>(null);
  const [expandedApprovals, setExpandedApprovals] = useState<Set<string>>(new Set());

  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [editingProject, setEditingProject] = useState<Record<string, string>>({});
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [senderAvatars, setSenderAvatars] = useState<Record<string, { pic_url: string | null; person_id: number | null; name: string | null }>>({});

  const fetchData = useCallback(async () => {
    try {
      const now = new Date();
      const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
      const endOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59).toISOString();

      const settingsData = await api.get<CockpitSettings>('/api/settings');
      setBgUrl(settingsData.cockpit_background_url);

      const excludeCats = settingsData.cockpit_calendar_exclude_categories ?? 'Transfer, Privat';
      const hidePrivate = settingsData.cockpit_calendar_hide_private ?? true;

      const [jobsData, reviewData, triageData, projectData, pipelineData, calData, flaggedData, recentData] = await Promise.all([
        api.get<AgentJob[]>('/api/agent-jobs'),
        api.get<PendingReviewTask[]>('/api/tasks/pending-review').catch(() => [] as PendingReviewTask[]),
        api.get<TriageStats>('/api/triage/stats').catch(() => null),
        api.get<ProjectOption[]>('/api/projects'),
        api.get<PipelineData>('/api/pipeline').catch(() => null),
        api.get<CalendarEvent[]>(`/api/calendar/events?start=${encodeURIComponent(startOfDay)}&end=${encodeURIComponent(endOfDay)}&exclude_categories=${encodeURIComponent(excludeCats)}&hide_private=${hidePrivate}&hide_free=true`).catch(() => [] as CalendarEvent[]),
        api.get<FlaggedEmail[]>('/api/emails/flagged?top=10').catch(() => [] as FlaggedEmail[]),
        api.get<AgentJob[]>('/api/agent-jobs?status=completed&limit=8').catch(() => [] as AgentJob[]),
      ]);

      setProjects(projectData);

      const awaitingApproval = jobsData.filter(j => j.status === 'awaiting_approval');
      const active = jobsData.filter(j => ['queued', 'running'].includes(j.status));
      setApprovalJobs(awaitingApproval);
      setActiveJobs(active);
      setPendingReview(reviewData);
      setTriageStats(triageData);
      setCalendarEvents(calData.filter(ev => {
        if (ev.is_all_day) return true;
        if (!ev.end) return true;
        const endTime = new Date(ev.end.endsWith('Z') ? ev.end : ev.end + 'Z');
        return endTime > now;
      }));
      setFlaggedEmails(flaggedData);
      setRecentJobs(recentData.slice(0, 8));

      if (pipelineData?.columns) {
        const focusCol = pipelineData.columns.find(c => c.position === 0) || pipelineData.columns[0];
        setFocusTasks(focusCol?.tasks ?? []);
      }

      try {
        const [pdDeals, pdLeads, pdActs] = await Promise.allSettled([
          api.get<PipedriveDealSummary[]>('/api/pipedrive/deals?status=open&limit=20'),
          api.get<PipedriveLeadSummary[]>('/api/pipedrive/leads?limit=100'),
          api.get<PipedriveActivitySummary[]>('/api/pipedrive/activities?done=false&limit=8'),
        ]);
        let anyOk = false;
        if (pdDeals.status === 'fulfilled') { setPipedriveDeals(pdDeals.value); anyOk = true; }
        if (pdLeads.status === 'fulfilled') { setPipedriveLeads(pdLeads.value); anyOk = true; }
        if (pdActs.status === 'fulfilled') { setPipedriveActivities(pdActs.value); anyOk = true; }
        setPipedriveConnected(anyOk);
      } catch {
        setPipedriveConnected(false);
      }
    } catch { /* */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  useSSE((event) => {
    if (['agent_jobs_changed', 'tasks_changed', 'email_triage_changed'].includes(event)) {
      fetchData();
    }
  });

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
    for (const job of approvalJobs) {
      const meta = (job.metadata_json || {}) as Record<string, string>;
      const email = meta.from_address;
      if (email && !senderAvatars[email]) {
        setSenderAvatars(prev => ({ ...prev, [email]: { pic_url: null, person_id: null, name: null } }));
        api.get<{ id: number; name: string; pic_url: string | null } | null>(`/api/pipedrive/lookup-email?email=${encodeURIComponent(email)}`)
          .then(data => {
            if (data && data.id) {
              setSenderAvatars(prev => ({ ...prev, [email]: { pic_url: data.pic_url, person_id: data.id, name: data.name } }));
            }
          })
          .catch(() => {});
      }
    }
  }, [approvalJobs, senderAvatars]);

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
              Dein Überblick — Entscheidungen, Agenten, Termine und Fokus
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
              <div className="absolute right-0 top-10 z-50 w-56 rounded-xl border border-gray-200 bg-white py-1 shadow-xl dark:border-gray-700 dark:bg-gray-900">
                <button
                  onClick={() => { setBgPickerOpen(true); setSettingsOpen(false); }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800"
                >
                  <ImageIcon className="h-4 w-4" />
                  Hintergrundbild ändern
                </button>
                <button
                  onClick={() => { navigate('/settings?tab=cockpit'); setSettingsOpen(false); }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800"
                >
                  <FilterIcon className="h-4 w-4" />
                  Kalender-Filter anpassen
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Inhalt */}
      <div className="relative z-10 flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-6xl space-y-6">

          {/* ── Zone 1: KPI-Übersicht ── */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            <KpiCard label="Entscheidungen" value={pendingDecisions} accent="rose" hasBg={hasBg} />
            <KpiCard label="Aktive Agenten" value={activeJobs.length} accent="indigo" hasBg={hasBg} />
            <KpiCard label="Fokus-Aufgaben" value={focusTasks.length} accent="amber" hasBg={hasBg} />
            <KpiCard label="Markierte E-Mails" value={flaggedEmails.length} accent="sky" hasBg={hasBg} />
            <KpiCard label="E-Mails in Triage" value={triageStats?.total_pending ?? 0} accent="emerald" hasBg={hasBg} />
          </div>

          {/* ── Zone 2: Fokus | Kalender | Markierte E-Mails ── */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">

            {/* Spalte 1: Fokus-Aufgaben */}
            <section className={`rounded-xl border p-4 ${cardClass}`}>
              <div className="mb-3 flex items-center justify-between">
                <h2 className={`text-sm font-semibold uppercase tracking-wider ${textSecondary}`}>
                  Fokus-Aufgaben
                </h2>
                <button
                  onClick={() => navigate('/pipeline')}
                  className={`text-xs font-medium ${hasBg ? 'text-white/60 hover:text-white' : 'text-indigo-600 hover:text-indigo-800 dark:text-indigo-400'}`}
                >
                  Agenda öffnen →
                </button>
              </div>
              {focusTasks.length === 0 ? (
                <div className={`flex h-20 items-center justify-center rounded-lg text-sm ${textMuted}`}>
                  Keine Fokus-Aufgaben
                </div>
              ) : (
                <div className="space-y-2">
                  {focusTasks.map(task => {
                    const overdue = task.due_date && new Date(task.due_date) < new Date();
                    return (
                      <div
                        key={task.id}
                        className={`flex items-center gap-2.5 rounded-lg p-2.5 transition-colors cursor-pointer ${
                          hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                        }`}
                        onClick={() => setSelectedTaskId(task.id)}
                      >
                        <div className={`h-2 w-2 rounded-full shrink-0 ${overdue ? 'bg-red-500' : 'bg-amber-400'}`} />
                        <div className="min-w-0 flex-1">
                          <div className={`text-sm font-medium truncate ${textPrimary}`}>{task.title}</div>
                          {task.due_date && (
                            <div className={`text-[11px] ${overdue ? 'text-red-500 font-medium' : textMuted}`}>
                              {overdue ? 'Überfällig' : `Fällig: ${new Date(task.due_date).toLocaleDateString('de-CH')}`}
                            </div>
                          )}
                        </div>
                        {task.checklist_total > 0 && (
                          <span className={`shrink-0 text-[11px] ${textMuted}`}>
                            {task.checklist_done}/{task.checklist_total}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {/* Spalte 2: Kalender heute */}
            <section className={`rounded-xl border p-4 ${cardClass}`}>
              <div className="mb-3 flex items-center justify-between">
                <h2 className={`text-sm font-semibold uppercase tracking-wider ${textSecondary}`}>
                  Heute
                </h2>
                <span className={`text-xs ${textMuted}`}>
                  {new Date().toLocaleDateString('de-CH', { weekday: 'long', day: 'numeric', month: 'long' })}
                </span>
              </div>
              {calendarEvents.length === 0 ? (
                <div className={`flex h-20 items-center justify-center rounded-lg text-sm ${textMuted}`}>
                  Keine Termine heute
                </div>
              ) : (
                <div className="space-y-1.5">
                  {calendarEvents.map(ev => {
                    const isMeeting = ev.attendees_count > 1;
                    return (
                      <div
                        key={ev.id}
                        className={`flex items-start gap-2.5 rounded-lg p-2.5 ${
                          hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                        }`}
                      >
                        <div className="mt-0.5 shrink-0">
                          {ev.is_all_day ? (
                            <div className={`h-5 w-5 rounded text-center text-[10px] font-bold leading-5 ${
                              hasBg ? 'bg-white/20 text-white' : 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300'
                            }`}>∞</div>
                          ) : isMeeting ? (
                            <UsersIcon className={`h-4 w-4 ${hasBg ? 'text-white/60' : 'text-blue-500 dark:text-blue-400'}`} />
                          ) : (
                            <ClockIcon className={`h-4 w-4 ${hasBg ? 'text-white/40' : 'text-gray-400 dark:text-gray-500'}`} />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className={`text-sm font-medium truncate ${textPrimary}`}>{ev.subject || 'Ohne Titel'}</div>
                          <div className={`text-[11px] ${textMuted}`}>
                            {ev.is_all_day ? 'Ganztägig' : `${formatTime(ev.start)} – ${formatTime(ev.end)}`}
                            {ev.location && ` · ${ev.location}`}
                          </div>
                        </div>
                        {isMeeting && (
                          <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                            hasBg ? 'bg-blue-500/30 text-blue-200' : 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                          }`}>
                            {ev.attendees_count}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {/* Spalte 3: Markierte E-Mails */}
            <section className={`rounded-xl border p-4 ${cardClass}`}>
              <div className="mb-3 flex items-center justify-between">
                <h2 className={`text-sm font-semibold uppercase tracking-wider ${textSecondary}`}>
                  Markierte E-Mails
                </h2>
                <button
                  onClick={() => navigate('/inbox')}
                  className={`text-xs font-medium ${hasBg ? 'text-white/60 hover:text-white' : 'text-indigo-600 hover:text-indigo-800 dark:text-indigo-400'}`}
                >
                  Posteingang →
                </button>
              </div>
              {flaggedEmails.length === 0 ? (
                <div className={`flex h-20 items-center justify-center rounded-lg text-sm ${textMuted}`}>
                  Keine markierten E-Mails
                </div>
              ) : (
                <div className="space-y-1.5">
                  {flaggedEmails.map(email => (
                    <div
                      key={email.id}
                      className={`flex items-start gap-2.5 rounded-lg p-2.5 cursor-pointer transition-colors ${
                        hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                      }`}
                      onClick={() => navigate('/inbox')}
                    >
                      <FlagIcon className={`mt-0.5 h-4 w-4 shrink-0 ${hasBg ? 'text-orange-300' : 'text-orange-500 dark:text-orange-400'}`} />
                      <div className="min-w-0 flex-1">
                        <div className={`text-sm font-medium truncate ${textPrimary}`}>{email.subject || 'Kein Betreff'}</div>
                        <div className={`text-[11px] ${textMuted}`}>
                          {email.from_name || email.from_address}
                          {email.received_at && ` · ${relativeDate(email.received_at)}`}
                        </div>
                      </div>
                      {email.has_attachments && (
                        <PaperclipIcon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${textMuted}`} />
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          {/* ── Zone 3: Freigaben (kompakt, aufklappbar) ── */}
          {approvalJobs.length > 0 && (
            <section>
              <h2 className={`mb-3 text-sm font-semibold uppercase tracking-wider ${textSecondary}`}>
                Freigaben
                <span className={`ml-2 inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold ${
                  hasBg ? 'bg-amber-500/30 text-amber-200' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
                }`}>{approvalJobs.length}</span>
              </h2>
              <div className="space-y-2">
                {approvalJobs.map(job => {
                  const meta = (job.metadata_json || {}) as Record<string, string>;
                  const preview = previews[job.id];
                  const isProcessing = processing.has(job.id);
                  const hasFailed = failedPreviews.has(job.id);
                  const isExpanded = expandedApprovals.has(job.id) || editingJobId === job.id;

                  const toggleExpand = () => {
                    setExpandedApprovals(prev => {
                      const next = new Set(prev);
                      if (next.has(job.id)) next.delete(job.id); else next.add(job.id);
                      return next;
                    });
                  };

                  return (
                    <div key={job.id} className={`rounded-xl border ${cardClass} ${isExpanded ? 'p-5' : 'p-3'}`}>
                      {/* Kompakte Kopfzeile */}
                      <div
                        className={`flex items-center gap-3 ${!isExpanded ? 'cursor-pointer' : ''}`}
                        onClick={!isExpanded ? toggleExpand : undefined}
                      >
                        {(() => {
                          const avatar = meta.from_address ? senderAvatars[meta.from_address] : null;
                          if (avatar?.pic_url) {
                            return avatar.person_id ? (
                              <a
                                href={`https://innosmith.pipedrive.com/person/${avatar.person_id}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="shrink-0"
                                title={avatar.name || meta.from_name || ''}
                              >
                                <img src={avatar.pic_url} alt="" className="h-9 w-9 rounded-full object-cover ring-2 ring-green-400/50" />
                              </a>
                            ) : (
                              <img src={avatar.pic_url} alt="" className="h-9 w-9 shrink-0 rounded-full object-cover" />
                            );
                          }
                          return (
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-100/80 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                              <MailDraftIcon className="h-4.5 w-4.5" />
                            </div>
                          );
                        })()}
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className={`text-sm font-semibold truncate ${textPrimary}`}>
                              {preview?.subject || meta.subject || 'E-Mail-Entwurf'}
                            </span>
                          </div>
                          <div className={`text-xs ${textMuted}`}>
                            An: {preview?.to_recipients?.join(', ') || meta.from_address || 'Unbekannt'}
                            {meta.from_name && (() => {
                              const avatar = meta.from_address ? senderAvatars[meta.from_address] : null;
                              if (avatar?.person_id) {
                                return (
                                  <>
                                    {' — von '}
                                    <a
                                      href={`https://innosmith.pipedrive.com/person/${avatar.person_id}`}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      onClick={(e) => e.stopPropagation()}
                                      className="font-medium text-green-600 hover:underline dark:text-green-400"
                                    >
                                      {avatar.name || meta.from_name}
                                    </a>
                                  </>
                                );
                              }
                              return ` — von ${meta.from_name}`;
                            })()}
                          </div>
                        </div>
                        {!isExpanded && (
                          <div className="flex shrink-0 items-center gap-1.5">
                            <button
                              onClick={(e) => { e.stopPropagation(); handleApprove(job.id); }}
                              disabled={isProcessing}
                              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                                hasBg
                                  ? 'bg-emerald-600/90 text-white hover:bg-emerald-600'
                                  : 'bg-emerald-600 text-white hover:bg-emerald-700'
                              }`}
                            >
                              {isProcessing ? '…' : 'Senden'}
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); handleReject(job.id); }}
                              disabled={isProcessing}
                              className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                                hasBg
                                  ? 'text-red-300 hover:bg-red-500/20'
                                  : 'text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20'
                              }`}
                            >
                              ✕
                            </button>
                            <ChevronDownIcon className={`h-4 w-4 ${textMuted}`} />
                          </div>
                        )}
                        {isExpanded && (
                          <button onClick={toggleExpand} className={`shrink-0 p-1 rounded ${hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-100 dark:hover:bg-gray-800'}`}>
                            <ChevronUpIcon className={`h-4 w-4 ${textMuted}`} />
                          </button>
                        )}
                      </div>

                      {/* Aufgeklappter Inhalt */}
                      {isExpanded && (
                        <div className="mt-4">
                          {meta.subject && (
                            <div className={`mb-3 rounded-lg px-3 py-2 text-xs ${hasBg ? 'bg-white/10' : 'bg-gray-50 dark:bg-gray-800/50'} ${textMuted}`}>
                              <span className="font-medium">Antwort auf:</span> {meta.subject}
                              {(meta.from_address || meta.from_name) && (
                                <span> — von {meta.from_name || meta.from_address}</span>
                              )}
                            </div>
                          )}

                          {meta.from_address && (
                            <div className="mb-3 sm:hidden">
                              <CrmBadge emailAddress={meta.from_address} senderName={meta.from_name} glassBg={hasBg} onCreateContact={() => {}} />
                            </div>
                          )}

                          {!preview && !hasFailed && (
                            <div className={`mb-3 flex items-center gap-2 text-sm ${textMuted}`}>
                              <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-transparent" />
                              Entwurf wird geladen…
                            </div>
                          )}

                          {editingJobId === job.id && preview ? (
                            <DraftEditor
                              jobId={job.id}
                              subject={preview.subject || ''}
                              bodyHtml={preview.body_html || ''}
                              toRecipients={preview.to_recipients || []}
                              ccRecipients={preview.cc_recipients || []}
                              glassBg={hasBg}
                              onSaved={() => {
                                setEditingJobId(null);
                                setPreviews(prev => { const n = { ...prev }; delete n[job.id]; return n; });
                                setFailedPreviews(prev => { const n = new Set(prev); n.delete(job.id); return n; });
                              }}
                              onSentAfterEdit={() => {
                                setEditingJobId(null);
                                fetchData();
                              }}
                              onCancel={() => setEditingJobId(null)}
                            />
                          ) : (
                            <>
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

                              <div className="flex gap-2">
                                <button
                                  onClick={() => handleApprove(job.id)}
                                  disabled={isProcessing}
                                  className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
                                    hasBg
                                      ? 'bg-emerald-600/90 text-white hover:bg-emerald-600 shadow-sm'
                                      : 'bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm'
                                  }`}
                                >
                                  {isProcessing ? 'Wird gesendet…' : 'Freigeben & Senden'}
                                </button>
                                {preview && (
                                  <button
                                    onClick={() => setEditingJobId(job.id)}
                                    className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                                      hasBg
                                        ? 'bg-white/10 text-white hover:bg-white/20 border border-white/20'
                                        : 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-900/20 dark:text-indigo-300 dark:hover:bg-indigo-900/40'
                                    }`}
                                  >
                                    <span className="flex items-center gap-1.5">
                                      <PencilIcon className="h-3.5 w-3.5" />
                                      Bearbeiten
                                    </span>
                                  </button>
                                )}
                                <button
                                  onClick={() => handleReject(job.id)}
                                  disabled={isProcessing}
                                  className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
                                    hasBg
                                      ? 'bg-red-500/20 text-red-200 hover:bg-red-500/30 border border-red-400/30'
                                      : 'border border-red-300 text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20'
                                  }`}
                                >
                                  Ablehnen
                                </button>
                              </div>
                            </>
                          )}

                          <TracePanel jobId={job.id} compact />
                        </div>
                      )}
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

          {/* ── Zone 4: CRM / Pipedrive ── */}
          {pipedriveConnected && (
            <section>
              <div className="mb-3 flex items-center justify-between">
                <h2 className={`text-sm font-semibold uppercase tracking-wider ${textSecondary}`}>
                  <span className="inline-flex items-center gap-1.5">
                    <CrmIcon className={`h-4 w-4 ${hasBg ? 'text-green-300' : 'text-green-600 dark:text-green-400'}`} />
                    Pipedrive CRM
                  </span>
                </h2>
                <a
                  href="https://innosmith.pipedrive.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`text-xs font-medium ${hasBg ? 'text-white/60 hover:text-white' : 'text-green-600 hover:text-green-800 dark:text-green-400'}`}
                >
                  Pipedrive öffnen →
                </a>
              </div>
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                {/* Leads (links) */}
                <div className={`rounded-xl border p-4 ${cardClass}`}>
                  <div className="mb-2 flex items-center justify-between">
                    <span className={`text-xs font-semibold uppercase tracking-wider ${textMuted}`}>Leads</span>
                    <span className={`text-[11px] ${textMuted}`}>{pipedriveLeads.length}</span>
                  </div>
                  {pipedriveLeads.length === 0 ? (
                    <div className={`flex h-14 items-center justify-center rounded-lg text-xs ${textMuted}`}>
                      Keine offenen Leads
                    </div>
                  ) : (
                    <div className="max-h-64 space-y-1 overflow-y-auto">
                      {pipedriveLeads.map(lead => (
                        <a
                          key={lead.id}
                          href={`https://innosmith.pipedrive.com/leads/inbox/${lead.id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`flex items-center gap-2 rounded-lg p-2 transition-colors ${
                            hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                          }`}
                        >
                          <div className="h-1.5 w-1.5 rounded-full shrink-0 bg-amber-400" />
                          <div className="min-w-0 flex-1">
                            <div className={`text-sm font-medium truncate ${textPrimary}`}>{lead.title}</div>
                            <div className={`text-[11px] ${textMuted}`}>
                              {lead.person_name || lead.org_name || ''}
                            </div>
                          </div>
                          {lead.value != null && lead.value > 0 && (
                            <span className={`shrink-0 text-[11px] font-medium ${textMuted}`}>
                              {lead.currency || 'CHF'} {lead.value.toLocaleString('de-CH')}
                            </span>
                          )}
                        </a>
                      ))}
                    </div>
                  )}
                </div>

                {/* Offene Deals (Mitte) */}
                <div className={`rounded-xl border p-4 ${cardClass}`}>
                  <div className="mb-2 flex items-center justify-between">
                    <span className={`text-xs font-semibold uppercase tracking-wider ${textMuted}`}>Deals</span>
                    <span className={`text-[11px] ${textMuted}`}>{pipedriveDeals.length}</span>
                  </div>
                  {pipedriveDeals.length === 0 ? (
                    <div className={`flex h-14 items-center justify-center rounded-lg text-xs ${textMuted}`}>
                      Keine offenen Deals
                    </div>
                  ) : (
                    <div className="max-h-64 space-y-1 overflow-y-auto">
                      {pipedriveDeals.map(deal => (
                        <a
                          key={deal.id}
                          href={`https://innosmith.pipedrive.com/deal/${deal.id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`flex items-center gap-2 rounded-lg p-2 transition-colors ${
                            hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                          }`}
                        >
                          <div className="h-1.5 w-1.5 rounded-full shrink-0 bg-green-500" />
                          <div className="min-w-0 flex-1">
                            <div className={`text-sm font-medium truncate ${textPrimary}`}>{deal.title}</div>
                            <div className={`text-[11px] ${textMuted}`}>
                              {deal.person_name || deal.org_name || ''}
                            </div>
                          </div>
                          {deal.value != null && deal.value > 0 && (
                            <span className={`shrink-0 text-[11px] font-semibold ${hasBg ? 'text-green-300' : 'text-green-600 dark:text-green-400'}`}>
                              {deal.currency || 'CHF'} {deal.value.toLocaleString('de-CH')}
                            </span>
                          )}
                        </a>
                      ))}
                    </div>
                  )}
                </div>

                {/* CRM-Aktivitäten (rechts) */}
                <div className={`rounded-xl border p-4 ${cardClass}`}>
                  <div className="mb-2 flex items-center justify-between">
                    <span className={`text-xs font-semibold uppercase tracking-wider ${textMuted}`}>Aufgaben</span>
                    <span className={`text-[11px] ${textMuted}`}>{pipedriveActivities.length}</span>
                  </div>
                  {pipedriveActivities.length === 0 ? (
                    <div className={`flex h-14 items-center justify-center rounded-lg text-xs ${textMuted}`}>
                      Keine offenen CRM-Aufgaben
                    </div>
                  ) : (
                    <div className="max-h-64 space-y-1 overflow-y-auto">
                      {pipedriveActivities.map(act => {
                        const isOverdue = act.due_date && new Date(act.due_date) < new Date();
                        return (
                          <a
                            key={act.id}
                            href={`https://innosmith.pipedrive.com/activities/${act.id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className={`flex items-center gap-2 rounded-lg p-2 transition-colors ${
                              hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                            }`}
                          >
                            <div className={`h-1.5 w-1.5 rounded-full shrink-0 ${isOverdue ? 'bg-red-500' : 'bg-orange-400'}`} />
                            <div className="min-w-0 flex-1">
                              <div className={`text-sm font-medium truncate ${textPrimary}`}>{act.subject}</div>
                              <div className={`text-[11px] ${isOverdue ? 'text-red-500 font-medium' : textMuted}`}>
                                {act.type || 'Aufgabe'}
                                {act.due_date && ` · ${isOverdue ? 'Überfällig' : new Date(act.due_date).toLocaleDateString('de-CH')}`}
                                {act.person_name && ` · ${act.person_name}`}
                              </div>
                            </div>
                          </a>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </section>
          )}

          {/* ── Zone 5: Aktive Agenten + Letzte Aktivitäten ── */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {/* Aktive Agenten */}
            <section className={`rounded-xl border p-4 ${cardClass}`}>
              <h2 className={`mb-3 text-sm font-semibold uppercase tracking-wider ${textSecondary}`}>
                Aktive Agenten
              </h2>
              {activeJobs.length === 0 ? (
                <div className={`flex h-16 items-center justify-center rounded-lg text-sm ${textMuted}`}>
                  Keine aktiven Agenten
                </div>
              ) : (
                <div className="space-y-2">
                  {activeJobs.map(job => {
                    const meta = (job.metadata_json || {}) as Record<string, string>;
                    const jobLabel = JOB_TYPE_LABELS[job.job_type || ''] || job.job_type || 'Agent-Job';
                    const subject = meta.subject || job.task_title;
                    return (
                      <div
                        key={job.id}
                        className={`flex items-center gap-3 rounded-lg p-2.5 cursor-pointer transition-colors ${
                          hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                        }`}
                        onClick={() => navigate('/agenten')}
                      >
                        <div className={`h-2.5 w-2.5 rounded-full shrink-0 ${
                          job.status === 'running' ? 'bg-blue-500 animate-pulse' : 'bg-amber-500'
                        }`} />
                        <div className="min-w-0 flex-1">
                          <div className={`text-sm font-medium truncate ${textPrimary}`}>
                            {jobLabel}{subject ? `: ${subject}` : ''}
                          </div>
                          <div className={`text-[11px] ${textMuted}`}>
                            {job.status === 'running' ? 'Läuft' : 'Wartend'}
                            {job.started_at && ` — seit ${new Date(job.started_at).toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' })}`}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {/* Letzte Aktivitäten */}
            <section className={`rounded-xl border p-4 ${cardClass}`}>
              <h2 className={`mb-3 text-sm font-semibold uppercase tracking-wider ${textSecondary}`}>
                Letzte Aktivitäten
              </h2>
              {recentJobs.length === 0 ? (
                <div className={`flex h-16 items-center justify-center rounded-lg text-sm ${textMuted}`}>
                  Noch keine Aktivitäten
                </div>
              ) : (
                <div className="space-y-1.5">
                  {recentJobs.map(job => {
                    const jobLabel = JOB_TYPE_LABELS[job.job_type || ''] || job.job_type || 'Agent';
                    const meta = (job.metadata_json || {}) as Record<string, string>;
                    const detail = meta.subject || job.task_title || '';
                    return (
                      <div
                        key={job.id}
                        className={`flex items-center gap-2.5 rounded-lg p-2 ${
                          hasBg ? 'hover:bg-white/10' : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                        }`}
                      >
                        <div className={`h-1.5 w-1.5 rounded-full shrink-0 ${
                          job.status === 'completed' ? 'bg-emerald-500' : 'bg-red-500'
                        }`} />
                        <div className="min-w-0 flex-1">
                          <div className={`text-xs truncate ${textPrimary}`}>
                            <span className="font-medium">{jobLabel}</span>
                            {detail && <span className={` ${textMuted}`}> — {detail}</span>}
                          </div>
                        </div>
                        <span className={`shrink-0 text-[10px] ${textMuted}`}>
                          {relativeDate(job.completed_at || job.created_at)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          </div>

          {/* Alles erledigt */}
          {pendingDecisions === 0 && activeJobs.length === 0 && focusTasks.length === 0 && flaggedEmails.length === 0 && calendarEvents.length === 0 && (
            <div className={`flex flex-col items-center justify-center rounded-xl border p-12 ${cardClass}`}>
              <CheckCircleIcon className={`h-12 w-12 mb-3 ${hasBg ? 'text-white/40' : 'text-emerald-300 dark:text-emerald-700'}`} />
              <p className={`text-lg font-medium ${textPrimary}`}>Alles erledigt</p>
              <p className={`mt-1 text-sm ${textSecondary}`}>
                Keine offenen Entscheidungen, Termine oder markierten E-Mails.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Task-Detail Modal */}
      {selectedTaskId && (
        <TaskDetailDialog
          taskId={selectedTaskId}
          onClose={() => setSelectedTaskId(null)}
          onUpdated={() => { setSelectedTaskId(null); fetchData(); }}
        />
      )}

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
  accent: 'rose' | 'indigo' | 'amber' | 'emerald' | 'sky';
  hasBg: boolean;
}) {
  const accentMap = {
    rose: { text: 'text-rose-600 dark:text-rose-400', bg: 'bg-rose-100 dark:bg-rose-900/40' },
    indigo: { text: 'text-indigo-600 dark:text-indigo-400', bg: 'bg-indigo-100 dark:bg-indigo-900/40' },
    amber: { text: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-100 dark:bg-amber-900/40' },
    emerald: { text: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-100 dark:bg-emerald-900/40' },
    sky: { text: 'text-sky-600 dark:text-sky-400', bg: 'bg-sky-100 dark:bg-sky-900/40' },
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

function FilterIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c2.755 0 5.455.232 8.083.678.533.09.917.556.917 1.096v1.044a2.25 2.25 0 0 1-.659 1.591l-5.432 5.432a2.25 2.25 0 0 0-.659 1.591v2.927a2.25 2.25 0 0 1-1.244 2.013L9.75 21v-6.568a2.25 2.25 0 0 0-.659-1.591L3.659 7.409A2.25 2.25 0 0 1 3 5.818V4.774c0-.54.384-1.006.917-1.096A48.32 48.32 0 0 1 12 3Z" />
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

function PencilIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
    </svg>
  );
}

function UsersIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z" />
    </svg>
  );
}

function ClockIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
    </svg>
  );
}

function FlagIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v1.5M3 21v-6m0 0 2.77-.693a9 9 0 0 1 6.208.682l.108.054a9 9 0 0 0 6.086.71l3.114-.732a48.524 48.524 0 0 1-.005-10.499l-3.11.732a9 9 0 0 1-6.085-.711l-.108-.054a9 9 0 0 0-6.208-.682L3 4.5M3 15V4.5" />
    </svg>
  );
}

function PaperclipIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m18.375 12.739-7.693 7.693a4.5 4.5 0 0 1-6.364-6.364l10.94-10.94A3 3 0 1 1 19.5 7.372L8.552 18.32m.009-.01-.01.01m5.699-9.941-7.81 7.81a1.5 1.5 0 0 0 2.112 2.13" />
    </svg>
  );
}

function CrmIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18.75a60.07 60.07 0 0 1 15.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 0 1 3 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 0 0-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 0 1-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 0 0 3 15h-.75M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm3 0h.008v.008H18V10.5Zm-12 0h.008v.008H6V10.5Z" />
    </svg>
  );
}

function ChevronDownIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
    </svg>
  );
}

function ChevronUpIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 15.75 7.5-7.5 7.5 7.5" />
    </svg>
  );
}
