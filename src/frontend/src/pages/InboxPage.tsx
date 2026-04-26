import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api/client';

/* ---------- Typen ---------- */

interface CalendarEvent {
  id: string;
  subject: string | null;
  start: string | null;
  end: string | null;
  is_all_day: boolean;
  location: string | null;
  show_as: string | null;
}

interface EmailSummary {
  id: string;
  subject: string | null;
  from_address: string | null;
  from_name: string | null;
  received_at: string | null;
  is_read: boolean;
  body_preview: string | null;
  categories: string[];
  inference_classification: string | null;
  importance: string | null;
  has_attachments: boolean;
}

interface EmailDetail {
  id: string;
  subject: string | null;
  from_address: string | null;
  from_name: string | null;
  to_recipients: string[];
  cc_recipients: string[];
  received_at: string | null;
  body_html: string | null;
  body_preview: string | null;
  categories: string[];
  inference_classification: string | null;
  importance: string | null;
  has_attachments: boolean;
  is_read: boolean;
}

interface FolderInfo {
  id: string;
  display_name: string;
  total_count: number;
}

interface EmailListResponse {
  emails: EmailSummary[];
  total: number | null;
}

interface TriageItem {
  id: string;
  message_id: string;
  subject: string | null;
  from_address: string | null;
  from_name: string | null;
  received_at: string | null;
  inference_class: string | null;
  triage_class: string | null;
  confidence: number | null;
  suggested_action: {
    triage_class?: string;
    confidence?: number;
    rationale?: string;
    suggested_action?: { type?: string; detail?: string };
    type?: string;
    detail?: string;
  } | null;
  agent_job_id: string | null;
  status: string;
  created_at: string;
}

interface TriageStats {
  by_status: Record<string, number>;
  by_class: Record<string, number>;
  total_pending: number;
}

interface ActivityItem {
  id: string;
  job_type: string;
  status: string;
  subject: string;
  from_address: string;
  output: string | null;
  created_at: string | null;
  completed_at: string | null;
}

interface ApprovalJob {
  id: string;
  job_type: string;
  status: string;
  output: string | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
}

interface PendingReviewTask {
  id: string;
  title: string;
  description: string | null;
  project_id: string;
  project_name: string;
  board_column_id: string;
  pipeline_column_id: string | null;
  due_date: string | null;
  email_message_id: string | null;
  created_at: string;
}

interface ProjectOption {
  id: string;
  name: string;
  board_columns?: { id: string; name: string; position: number }[];
}

/* ---------- Triage-Farben & Labels ---------- */

const TRIAGE_CONFIG: Record<string, { label: string; bg: string; text: string; dot: string }> = {
  quick_response: {
    label: 'Schnellantwort',
    bg: 'bg-emerald-100 dark:bg-emerald-900/40',
    text: 'text-emerald-700 dark:text-emerald-300',
    dot: 'bg-emerald-500',
  },
  board_task: {
    label: 'Aufgabe',
    bg: 'bg-blue-100 dark:bg-blue-900/40',
    text: 'text-blue-700 dark:text-blue-300',
    dot: 'bg-blue-500',
  },
  bedenkzeit: {
    label: 'Prüfen',
    bg: 'bg-amber-100 dark:bg-amber-900/40',
    text: 'text-amber-700 dark:text-amber-300',
    dot: 'bg-amber-500',
  },
  fyi: {
    label: 'Zur Kenntnis',
    bg: 'bg-gray-100 dark:bg-gray-800',
    text: 'text-gray-600 dark:text-gray-400',
    dot: 'bg-gray-400',
  },
};

function TriageBadge({ triageClass }: { triageClass: string | null | undefined }) {
  if (!triageClass) return null;
  const cfg = TRIAGE_CONFIG[triageClass];
  if (!cfg) return null;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${cfg.bg} ${cfg.text}`}>
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

const CATEGORY_COLORS: Record<string, string> = {
  wichtig: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  important: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  finanzen: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  finance: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  newsletter: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
};

function getCategoryClass(cat: string): string {
  return CATEGORY_COLORS[cat.toLowerCase()] || 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400';
}

/* ---------- Haupt-Komponente ---------- */

export function InboxPage() {
  const [emails, setEmails] = useState<EmailSummary[]>([]);
  const [folders, setFolders] = useState<FolderInfo[]>([]);
  const [selectedEmail, setSelectedEmail] = useState<EmailDetail | null>(null);
  const [activeFolder, setActiveFolder] = useState('inbox');
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCompose, setShowCompose] = useState(false);
  const [composeReplyTo, setComposeReplyTo] = useState<string | undefined>();
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'inbox' | 'approvals'>('dashboard');

  const [triageMap, setTriageMap] = useState<Record<string, TriageItem>>({});
  const [triageStats, setTriageStats] = useState<TriageStats | null>(null);
  const [activityFeed, setActivityFeed] = useState<{activities: ActivityItem[]; summary: {drafts_pending: number; classified_today: number}} | null>(null);
  const [approvalJobs, setApprovalJobs] = useState<ApprovalJob[]>([]);
  const [pendingReviewTasks, setPendingReviewTasks] = useState<PendingReviewTask[]>([]);
  const sseRef = useRef<EventSource | null>(null);

  /* -- E-Mails laden -- */
  const fetchEmails = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        folder: activeFolder,
        top: '30',
        ...(unreadOnly ? { unread_only: 'true' } : {}),
      });
      const data = await api.get<EmailListResponse>(`/api/emails?${params}`);
      setEmails(data.emails);
      setError(null);
    } catch (e) {
      if (e instanceof Error && e.message.includes('503')) {
        setError('Graph API nicht konfiguriert. Bitte TP_GRAPH_* Umgebungsvariablen setzen.');
      } else {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden');
      }
    } finally {
      setLoading(false);
    }
  }, [activeFolder, unreadOnly]);

  /* -- Triage-Daten laden -- */
  const fetchTriage = useCallback(async () => {
    try {
      const [items, stats] = await Promise.all([
        api.get<TriageItem[]>('/api/triage?limit=200'),
        api.get<TriageStats>('/api/triage/stats'),
      ]);
      const map: Record<string, TriageItem> = {};
      for (const item of items) {
        map[item.message_id] = item;
      }
      setTriageMap(map);
      setTriageStats(stats);
    } catch {
      /* triage optional */
    }
  }, []);

  /* -- Activity-Feed laden -- */
  const fetchActivity = useCallback(async () => {
    try {
      const data = await api.get<{activities: ActivityItem[]; summary: {drafts_pending: number; classified_today: number}}>('/api/triage/activity/feed?limit=30');
      setActivityFeed(data);
    } catch {
      /* optional */
    }
  }, []);

  /* -- Approval-Jobs laden -- */
  const fetchApprovals = useCallback(async () => {
    try {
      const jobs = await api.get<ApprovalJob[]>('/api/agent-jobs?status=awaiting_approval');
      setApprovalJobs(jobs);
    } catch {
      /* optional */
    }
  }, []);

  /* -- Pending Review Tasks laden -- */
  const fetchPendingReview = useCallback(async () => {
    try {
      const tasks = await api.get<PendingReviewTask[]>('/api/tasks/pending-review');
      setPendingReviewTasks(tasks);
    } catch {
      /* optional */
    }
  }, []);

  /* -- Initiales Laden -- */
  useEffect(() => {
    fetchEmails();
  }, [fetchEmails]);

  useEffect(() => {
    fetchTriage();
    fetchActivity();
    fetchApprovals();
    fetchPendingReview();
    api.get<FolderInfo[]>('/api/emails/folders').then(setFolders).catch(() => {});
  }, [fetchTriage, fetchActivity, fetchApprovals, fetchPendingReview]);

  /* -- SSE für Live-Updates -- */
  useEffect(() => {
    const token = localStorage.getItem('taskpilot_token');
    if (!token) return;
    const es = new EventSource(`/api/sse/events?token=${token}`);
    sseRef.current = es;
    es.addEventListener('email_triage_changed', () => {
      fetchTriage();
    });
    es.onerror = () => {
      es.close();
    };
    return () => es.close();
  }, [fetchTriage]);

  /* -- E-Mail öffnen -- */
  const openEmail = async (email: EmailSummary) => {
    setDetailLoading(true);
    try {
      const detail = await api.get<EmailDetail>(`/api/emails/${email.id}`);
      setSelectedEmail(detail);
      if (!email.is_read) {
        await api.patch(`/api/emails/${email.id}/read`);
        setEmails((prev) => prev.map((e) => (e.id === email.id ? { ...e, is_read: true } : e)));
      }
    } catch {
      /* ignore */
    } finally {
      setDetailLoading(false);
    }
  };

  /* -- Triage-Aktionen -- */
  const dismissTriage = async (triageId: string) => {
    try {
      await api.post(`/api/triage/${triageId}/dismiss`);
      await fetchTriage();
    } catch {
      /* ignore */
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    return d.toLocaleDateString('de-DE', { day: 'numeric', month: 'short' });
  };

  const selectedTriage = selectedEmail ? triageMap[selectedEmail.id] : null;

  return (
    <div className="flex h-full flex-col">
      {/* Header mit Tab-Navigation */}
      <div className="border-b border-gray-200 px-6 pt-4 dark:border-gray-800">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">E-Mail Intelligence</h1>
            <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
              {activeTab === 'dashboard' ? 'Steuerungszentrale' : activeTab === 'inbox' ? 'Posteingang' : 'Agent-Entwürfe prüfen'}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {activeTab === 'inbox' && (
              <>
                <label className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <input
                    type="checkbox"
                    checked={unreadOnly}
                    onChange={(e) => setUnreadOnly(e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-gray-300 text-indigo-600"
                  />
                  Nur ungelesen
                </label>
                <button
                  onClick={fetchEmails}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-700"
                >
                  Aktualisieren
                </button>
                <button
                  onClick={() => { setComposeReplyTo(undefined); setShowCompose(true); }}
                  className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-700"
                >
                  Entwurf schreiben
                </button>
              </>
            )}
          </div>
        </div>
        {/* Tab-Leiste */}
        <div className="flex gap-1">
          {([
            { id: 'dashboard' as const, label: 'Dashboard', count: activityFeed?.summary.drafts_pending },
            { id: 'inbox' as const, label: 'Inbox', count: triageStats?.total_pending },
            { id: 'approvals' as const, label: 'Freigaben', count: approvalJobs.length || undefined },
          ]).map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`relative rounded-t-lg px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-white text-indigo-700 dark:bg-gray-900 dark:text-indigo-400'
                  : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              {tab.label}
              {(tab.count ?? 0) > 0 && (
                <span className="ml-1.5 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-indigo-100 px-1.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300">
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab-Inhalt */}
      {activeTab === 'dashboard' && (
        <div className="flex-1 overflow-y-auto p-6">
          {/* Zusammenfassung */}
          <div className="mb-6 grid grid-cols-3 gap-4">
            <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
              <div className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                {activityFeed?.summary.classified_today || 0}
              </div>
              <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">Heute klassifiziert</div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
              <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                {activityFeed?.summary.drafts_pending || 0}
              </div>
              <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">Entwürfe zur Freigabe</div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
              <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                {triageStats ? Object.values(triageStats.by_class).reduce((a, b) => a + b, 0) : 0}
              </div>
              <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">E-Mails in Triage</div>
            </div>
          </div>

          {/* Triage-Klassen-Übersicht */}
          {triageStats && triageStats.total_pending > 0 && (
            <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
              <h3 className="mb-3 text-sm font-semibold text-gray-700 dark:text-gray-300">Triage-Übersicht</h3>
              <div className="flex gap-4">
                {Object.entries(triageStats.by_class).map(([cls, count]) => {
                  const cfg = TRIAGE_CONFIG[cls];
                  return (
                    <div key={cls} className="flex items-center gap-2 text-sm">
                      {cfg && <span className={`inline-block h-3 w-3 rounded-full ${cfg.dot}`} />}
                      <span className="font-medium text-gray-700 dark:text-gray-300">{count}</span>
                      <span className="text-gray-500 dark:text-gray-400">{cfg?.label || cls}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Aufgaben-Vorschläge */}
          {pendingReviewTasks.length > 0 && (
            <TaskSuggestionsSection
              tasks={pendingReviewTasks}
              onAction={() => { fetchPendingReview(); fetchActivity(); }}
            />
          )}

          {/* Activity-Feed */}
          <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
            <h3 className="border-b border-gray-200 px-4 py-3 text-sm font-semibold text-gray-700 dark:border-gray-700 dark:text-gray-300">
              Agent-Aktivitäten
            </h3>
            {activityFeed && activityFeed.activities.length > 0 ? (
              <div className="divide-y divide-gray-100 dark:divide-gray-800">
                {activityFeed.activities.map(act => (
                  <div key={act.id} className="flex items-center gap-3 px-4 py-3">
                    <div className={`h-2 w-2 rounded-full shrink-0 ${
                      act.status === 'awaiting_approval' ? 'bg-amber-500' :
                      act.status === 'completed' ? 'bg-emerald-500' :
                      act.status === 'queued' ? 'bg-blue-500' :
                      'bg-gray-400'
                    }`} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-gray-700 dark:text-gray-300 truncate">
                        {act.job_type === 'email_triage' && 'Triage: '}
                        {act.job_type === 'draft_email_reply' && 'Entwurf: '}
                        {act.job_type === 'create_task_from_email' && 'Task: '}
                        {act.subject || 'Unbekannt'}
                      </div>
                      {act.output && (
                        <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{act.output}</div>
                      )}
                    </div>
                    <div className="shrink-0 text-xs text-gray-400 dark:text-gray-500">
                      {act.created_at ? new Date(act.created_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) : ''}
                    </div>
                    {act.status === 'awaiting_approval' && (
                      <button
                        onClick={() => setActiveTab('approvals')}
                        className="shrink-0 rounded bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                      >
                        Prüfen
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-8 text-center text-sm text-gray-400 dark:text-gray-600">
                Der Agent prüft automatisch alle 2 Minuten auf neue E-Mails. Aktivitäten erscheinen hier, sobald nanobot E-Mails verarbeitet hat.
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'approvals' && (
        <ApprovalsTab
          approvalJobs={approvalJobs}
          onAction={() => { fetchApprovals(); fetchActivity(); }}
        />
      )}

      {activeTab === 'inbox' && (<>
      {/* Triage-Statistik-Leiste */}
      {triageStats && triageStats.total_pending > 0 && (
        <div className="flex items-center gap-4 border-b border-gray-200 bg-gray-50 px-6 py-2 text-xs dark:border-gray-800 dark:bg-gray-900/50">
          <span className="font-medium text-gray-700 dark:text-gray-300">Triage:</span>
          {Object.entries(triageStats.by_class).map(([cls, count]) => {
            const cfg = TRIAGE_CONFIG[cls];
            return (
              <span key={cls} className="flex items-center gap-1 text-gray-600 dark:text-gray-400">
                {cfg && <span className={`inline-block h-2 w-2 rounded-full ${cfg.dot}`} />}
                <span className="font-medium">{count}</span> {cfg?.label || cls}
              </span>
            );
          })}
          <span className="ml-auto text-gray-400 dark:text-gray-500">
            {triageStats.total_pending} offen
          </span>
        </div>
      )}

      {error && (
        <div className="mx-6 mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
          {error}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Folder sidebar */}
        <div className="hidden w-48 shrink-0 border-r border-gray-200 p-3 dark:border-gray-800 md:block">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
            Ordner
          </h3>
          <div className="space-y-0.5">
            {[
              { id: 'inbox', name: 'Posteingang' },
              { id: 'drafts', name: 'Entwürfe' },
              { id: 'sentitems', name: 'Gesendet' },
              ...(folders
                .filter((f) => !['Inbox', 'Drafts', 'Sent Items', 'Deleted Items', 'Junk Email'].includes(f.display_name))
                .map((f) => ({ id: f.id, name: f.display_name }))),
            ].map((folder) => (
              <button
                key={folder.id}
                onClick={() => { setActiveFolder(folder.id); setSelectedEmail(null); }}
                className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors ${
                  activeFolder === folder.id
                    ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
                    : 'text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                {folder.name}
              </button>
            ))}
          </div>
        </div>

        {/* Email list */}
        <div className={`${selectedEmail ? 'hidden md:block md:w-1/3' : 'w-full'} shrink-0 overflow-y-auto border-r border-gray-200 dark:border-gray-800`}>
          {loading ? (
            <div className="flex h-full items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
            </div>
          ) : emails.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-gray-400 dark:text-gray-600">
              Keine E-Mails
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              {emails.map((email) => {
                const triage = triageMap[email.id];
                return (
                  <button
                    key={email.id}
                    onClick={() => openEmail(email)}
                    className={`flex w-full flex-col gap-1 px-4 py-3 text-left transition-colors hover:bg-gray-50 dark:hover:bg-gray-900 ${
                      selectedEmail?.id === email.id ? 'bg-indigo-50/50 dark:bg-indigo-950/20' : ''
                    } ${!email.is_read ? 'bg-white dark:bg-gray-950' : 'bg-gray-50/50 dark:bg-gray-900/50'}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={`text-sm ${!email.is_read ? 'font-semibold text-gray-900 dark:text-white' : 'text-gray-700 dark:text-gray-300'}`}>
                        {email.from_name || email.from_address || 'Unbekannt'}
                      </span>
                      <span className="shrink-0 text-[10px] text-gray-400 dark:text-gray-500">
                        {formatDate(email.received_at)}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <p className={`flex-1 truncate text-sm ${!email.is_read ? 'font-medium text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-400'}`}>
                        {email.subject || '(Kein Betreff)'}
                      </p>
                      {triage && triage.status === 'pending' && (
                        <TriageBadge triageClass={triage.triage_class} />
                      )}
                    </div>
                    <p className="truncate text-xs text-gray-400 dark:text-gray-500">
                      {email.body_preview}
                    </p>
                    {email.categories.length > 0 && (
                      <div className="mt-0.5 flex gap-1">
                        {email.categories.map((cat) => (
                          <span key={cat} className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${getCategoryClass(cat)}`}>
                            {cat}
                          </span>
                        ))}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Detail pane */}
        <div className={`${selectedEmail ? 'flex-1' : 'hidden md:flex md:flex-1'} overflow-y-auto`}>
          {detailLoading ? (
            <div className="flex h-full items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
            </div>
          ) : selectedEmail ? (
            <div className="p-6">
              {/* Aktionsleiste */}
              <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900/60">
                {selectedTriage && selectedTriage.status === 'pending' && (
                  <TriageBadge triageClass={selectedTriage.triage_class} />
                )}
                {selectedTriage?.suggested_action?.rationale && (
                  <span className="text-xs text-gray-500 dark:text-gray-400 italic">
                    {selectedTriage.suggested_action.rationale}
                  </span>
                )}
                <div className="ml-auto flex items-center gap-2">
                  <button
                    onClick={() => {
                      setComposeReplyTo(selectedEmail.id);
                      setShowCompose(true);
                    }}
                    className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-700"
                  >
                    Antwort entwerfen
                  </button>
                  <button
                    onClick={() => {
                      const event = new CustomEvent('open-create-task-from-email', {
                        detail: {
                          emailId: selectedEmail.id,
                          subject: selectedEmail.subject,
                          bodyPreview: selectedEmail.body_preview,
                          fromAddress: selectedEmail.from_address,
                          triageId: selectedTriage?.id,
                        },
                      });
                      window.dispatchEvent(event);
                    }}
                    className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700"
                  >
                    Task erstellen
                  </button>
                  {selectedTriage && selectedTriage.status === 'pending' && (
                    <button
                      onClick={() => dismissTriage(selectedTriage.id)}
                      className="rounded-lg bg-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                    >
                      Archivieren / FYI
                    </button>
                  )}
                </div>
              </div>

              {/* Kalender-Kontext */}
              <CalendarContext selectedTriage={selectedTriage} emailSubject={selectedEmail.subject} />

              {/* E-Mail Header */}
              <div className="mb-4 flex items-start justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                    {selectedEmail.subject || '(Kein Betreff)'}
                  </h2>
                  <div className="mt-1 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                    <span className="font-medium text-gray-700 dark:text-gray-300">
                      {selectedEmail.from_name || selectedEmail.from_address}
                    </span>
                    {selectedEmail.from_name && (
                      <span className="text-xs">&lt;{selectedEmail.from_address}&gt;</span>
                    )}
                  </div>
                  {selectedEmail.to_recipients.length > 0 && (
                    <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
                      An: {selectedEmail.to_recipients.join(', ')}
                    </p>
                  )}
                  <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
                    {selectedEmail.received_at ? new Date(selectedEmail.received_at).toLocaleString('de-DE') : ''}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setSelectedEmail(null)}
                    className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 md:hidden"
                  >
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>

              {/* Kategorien */}
              {selectedEmail.categories.length > 0 && (
                <div className="mb-4 flex gap-1.5">
                  {selectedEmail.categories.map((cat) => (
                    <span key={cat} className={`rounded-full px-2 py-0.5 text-xs font-medium ${getCategoryClass(cat)}`}>
                      {cat}
                    </span>
                  ))}
                  {selectedEmail.inference_classification && (
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                      {selectedEmail.inference_classification === 'focused' ? 'Relevant' : 'Sonstige'}
                    </span>
                  )}
                </div>
              )}

              {/* Body */}
              {selectedEmail.body_html ? (
                <div
                  className="prose prose-sm max-w-none dark:prose-invert"
                  dangerouslySetInnerHTML={{ __html: selectedEmail.body_html }}
                />
              ) : (
                <p className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300">
                  {selectedEmail.body_preview}
                </p>
              )}
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-gray-400 dark:text-gray-600">
              E-Mail auswählen
            </div>
          )}
        </div>
      </div>

      {/* Compose dialog */}
      {showCompose && (
        <ComposeDialog
          replyToId={composeReplyTo}
          onClose={() => setShowCompose(false)}
          onSent={() => { setShowCompose(false); fetchEmails(); }}
        />
      )}

      {/* CreateTaskFromEmail dialog */}
      <CreateTaskFromEmailListener onTaskCreated={fetchTriage} />
      </>)}
    </div>
  );
}

/* ---------- Compose Dialog ---------- */

function ComposeDialog({
  replyToId,
  onClose,
  onSent,
}: {
  replyToId?: string;
  onClose: () => void;
  onSent: () => void;
}) {
  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [saving, setSaving] = useState(false);
  const [draftId, setDraftId] = useState<string | null>(null);

  useEffect(() => {
    if (replyToId) {
      api.get<EmailDetail>(`/api/emails/${replyToId}`).then((detail) => {
        setTo(detail.from_address || '');
        setSubject(detail.subject ? `Re: ${detail.subject.replace(/^Re:\s*/i, '')}` : '');
      }).catch(() => {});
    }
  }, [replyToId]);

  const saveDraft = async () => {
    if (!to.trim() || !subject.trim()) return;
    setSaving(true);
    try {
      const res = await api.post<{ id: string }>('/api/emails/drafts', {
        subject,
        body_html: `<p>${body.replace(/\n/g, '<br/>')}</p>`,
        to_recipients: to.split(',').map((s) => s.trim()).filter(Boolean),
      });
      setDraftId(res.id);
    } catch {
      /* ignore */
    } finally {
      setSaving(false);
    }
  };

  const sendDraft = async () => {
    if (!draftId) return;
    try {
      await api.post(`/api/emails/${draftId}/send`);
      onSent();
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-gray-950">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            {replyToId ? 'Antwort entwerfen' : 'Neuer Entwurf'}
          </h3>
          <button onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-3">
          <input
            value={to}
            onChange={(e) => setTo(e.target.value)}
            placeholder="An (kommagetrennt)..."
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-indigo-300 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
          />
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Betreff..."
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-indigo-300 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
          />
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={8}
            placeholder="Nachricht..."
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-indigo-300 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
          />
        </div>

        <div className="mt-4 flex items-center justify-between">
          {draftId ? (
            <span className="text-xs text-green-600 dark:text-green-400">
              Entwurf gespeichert (ID: {draftId.slice(0, 8)}...)
            </span>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <button
              onClick={saveDraft}
              disabled={saving || !to.trim() || !subject.trim()}
              className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-40 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
            >
              {saving ? 'Speichert...' : 'Als Entwurf speichern'}
            </button>
            {draftId && (
              <button
                onClick={sendDraft}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                Senden
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------- CreateTaskFromEmail Listener ---------- */

interface CreateTaskEvent {
  emailId: string;
  subject: string | null;
  bodyPreview: string | null;
  fromAddress: string | null;
  triageId?: string;
}

interface ProjectListItem {
  id: string;
  name: string;
  board_columns?: { id: string; name: string; position: number }[];
}

/* ---------- Kalender-Kontext ---------- */

function CalendarContext({
  selectedTriage,
  emailSubject,
}: {
  selectedTriage: TriageItem | null | undefined;
  emailSubject: string | null;
}) {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59).toISOString();
    api.get<CalendarEvent[]>(`/api/calendar/events?start=${start}&end=${end}&top=10`)
      .then((data) => { setEvents(data); setLoaded(true); })
      .catch(() => setLoaded(true));
  }, []);

  const createTimeBlocker = async () => {
    setCreating(true);
    try {
      const now = new Date();
      const start = new Date(now.getTime() + 60 * 60 * 1000);
      start.setMinutes(0, 0, 0);
      const endTime = new Date(start.getTime() + 60 * 60 * 1000);
      await api.post('/api/calendar/events', {
        subject: `Zeitblocker: ${emailSubject || 'Aufgabe'}`,
        start: start.toISOString(),
        end: endTime.toISOString(),
        show_as: 'busy',
      });
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
      const todayEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59).toISOString();
      const updated = await api.get<CalendarEvent[]>(`/api/calendar/events?start=${todayStart}&end=${todayEnd}&top=10`);
      setEvents(updated);
    } catch {
      /* ignore */
    } finally {
      setCreating(false);
    }
  };

  if (!loaded) return null;

  const upcomingEvents = events
    .filter((e) => e.start && new Date(e.start) > new Date())
    .sort((a, b) => new Date(a.start!).getTime() - new Date(b.start!).getTime())
    .slice(0, 3);

  const formatTime = (iso: string | null) => {
    if (!iso) return '';
    return new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="mb-4 rounded-xl border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900/60">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
          Heutige Termine
        </h4>
        {selectedTriage?.triage_class === 'board_task' && (
          <button
            onClick={createTimeBlocker}
            disabled={creating}
            className="rounded-lg bg-violet-600 px-2.5 py-1 text-[10px] font-medium text-white transition-colors hover:bg-violet-700 disabled:opacity-50"
          >
            {creating ? 'Erstellt...' : 'Zeitblocker erstellen'}
          </button>
        )}
      </div>
      {upcomingEvents.length === 0 ? (
        <p className="text-xs text-gray-400 dark:text-gray-500 italic">Keine weiteren Termine heute</p>
      ) : (
        <div className="space-y-1">
          {upcomingEvents.map((ev) => (
            <div key={ev.id} className="flex items-center gap-2 text-xs">
              <span className="shrink-0 font-medium text-gray-700 dark:text-gray-300">
                {formatTime(ev.start)}
              </span>
              <span className="truncate text-gray-600 dark:text-gray-400">{ev.subject}</span>
              {ev.location && (
                <span className="shrink-0 text-gray-400 dark:text-gray-500">({ev.location})</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- CreateTaskFromEmail Listener ---------- */

function CreateTaskFromEmailListener({ onTaskCreated }: { onTaskCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [eventData, setEventData] = useState<CreateTaskEvent | null>(null);
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [selectedProject, setSelectedProject] = useState('');
  const [selectedColumn, setSelectedColumn] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<CreateTaskEvent>).detail;
      setEventData(detail);
      setTitle(detail.subject || '');
      setDescription(
        `Erstellt aus E-Mail von ${detail.fromAddress || 'unbekannt'}\n\n${detail.bodyPreview || ''}`.trim(),
      );
      setOpen(true);

      api.get<ProjectListItem[]>('/api/projects').then((data) => {
        setProjects(data);
        if (data.length > 0) {
          setSelectedProject(data[0].id);
          const cols = data[0].board_columns || [];
          if (cols.length > 0) {
            const sorted = [...cols].sort((a, b) => a.position - b.position);
            setSelectedColumn(sorted[0].id);
          }
        }
      }).catch(() => {});
    };
    window.addEventListener('open-create-task-from-email', handler);
    return () => window.removeEventListener('open-create-task-from-email', handler);
  }, []);

  const currentProject = projects.find((p) => p.id === selectedProject);
  const columns = (currentProject?.board_columns || []).sort((a, b) => a.position - b.position);

  useEffect(() => {
    if (columns.length > 0 && !columns.find((c) => c.id === selectedColumn)) {
      setSelectedColumn(columns[0].id);
    }
  }, [selectedProject, columns, selectedColumn]);

  const create = async () => {
    if (!title.trim() || !selectedProject || !selectedColumn) return;
    setCreating(true);
    try {
      await api.post('/api/tasks', {
        title,
        description,
        project_id: selectedProject,
        board_column_id: selectedColumn,
        board_position: 0,
        email_message_id: eventData?.emailId || null,
      });
      if (eventData?.triageId) {
        await api.post(`/api/triage/${eventData.triageId}/act`).catch(() => {});
      }
      onTaskCreated();
      setOpen(false);
    } catch {
      /* ignore */
    } finally {
      setCreating(false);
    }
  };

  if (!open || !eventData) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-gray-950">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Task aus E-Mail erstellen</h3>
          <button
            onClick={() => setOpen(false)}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Titel</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-indigo-300 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Beschreibung</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-indigo-300 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Projekt</label>
              <select
                value={selectedProject}
                onChange={(e) => setSelectedProject(e.target.value)}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-white"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Spalte</label>
              <select
                value={selectedColumn}
                onChange={(e) => setSelectedColumn(e.target.value)}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-white"
              >
                {columns.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={() => setOpen(false)}
            className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            Abbrechen
          </button>
          <button
            onClick={create}
            disabled={creating || !title.trim() || !selectedProject}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {creating ? 'Erstellt...' : 'Task erstellen'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------- Approvals Tab ---------- */

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

function ApprovalsTab({
  approvalJobs,
  onAction,
}: {
  approvalJobs: ApprovalJob[];
  onAction: () => void;
}) {
  const [previews, setPreviews] = useState<Record<string, DraftPreview>>({});
  const [loadingPreviews, setLoadingPreviews] = useState<Set<string>>(new Set());
  const [processing, setProcessing] = useState<Set<string>>(new Set());
  const [failedPreviews, setFailedPreviews] = useState<Set<string>>(new Set());

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

  const handleApprove = async (jobId: string) => {
    setProcessing(prev => new Set(prev).add(jobId));
    try {
      await api.patch(`/api/agent-jobs/${jobId}`, { status: 'completed' });
      onAction();
    } catch { /* ignore */ }
    finally { setProcessing(prev => { const n = new Set(prev); n.delete(jobId); return n; }); }
  };

  const handleReject = async (jobId: string) => {
    setProcessing(prev => new Set(prev).add(jobId));
    try {
      await api.patch(`/api/agent-jobs/${jobId}`, { status: 'failed', error_message: 'Vom Benutzer abgelehnt' });
      onAction();
    } catch { /* ignore */ }
    finally { setProcessing(prev => { const n = new Set(prev); n.delete(jobId); return n; }); }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        <h3 className="border-b border-gray-200 px-4 py-3 text-sm font-semibold text-gray-700 dark:border-gray-700 dark:text-gray-300">
          Entwürfe zur Freigabe
        </h3>
        {approvalJobs.length > 0 ? (
          <div className="divide-y divide-gray-100 dark:divide-gray-800">
            {approvalJobs.map(job => {
              const meta = (job.metadata_json || {}) as Record<string, string>;
              const preview = previews[job.id];
              const isLoading = loadingPreviews.has(job.id);
              const isProcessing = processing.has(job.id);
              const hasFailed = failedPreviews.has(job.id);

              return (
                <div key={job.id} className="px-5 py-5">
                  {/* Header: Betreff + Badge */}
                  <div className="flex items-center gap-3 mb-3">
                    <div className="h-9 w-9 shrink-0 rounded-full bg-amber-100 flex items-center justify-center text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                      <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                      </svg>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-base font-semibold text-gray-900 dark:text-white truncate">
                          {preview?.subject || meta.subject || 'E-Mail-Entwurf'}
                        </span>
                        <span className="shrink-0 rounded-full bg-amber-100 px-2.5 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                          Freigabe nötig
                        </span>
                      </div>
                      <div className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
                        An: {preview?.to_recipients?.join(', ') || meta.from_address || 'Unbekannt'}
                      </div>
                    </div>
                  </div>

                  {/* Quell-E-Mail-Info */}
                  {meta.subject && (
                    <div className="mb-3 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-500 dark:bg-gray-800/50 dark:text-gray-400">
                      <span className="font-medium">Antwort auf:</span> {meta.subject}
                      {(meta.from_address || meta.from_name) && (
                        <span> — von {meta.from_name || meta.from_address}</span>
                      )}
                    </div>
                  )}

                  {/* Lade-Indikator */}
                  {isLoading && (
                    <div className="mb-3 flex items-center gap-2 text-sm text-gray-400">
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-transparent" />
                      Entwurf wird aus Outlook geladen…
                    </div>
                  )}

                  {/* Draft-Vorschau: der eigentliche E-Mail-Entwurf */}
                  {preview?.body_html && (
                    <div className="mb-3 rounded-lg border border-gray-200 bg-white dark:border-gray-600 dark:bg-gray-800">
                      <div className="border-b border-gray-100 px-4 py-2 dark:border-gray-700">
                        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">E-Mail-Entwurf</span>
                      </div>
                      <div className="max-h-72 overflow-y-auto px-4 py-3">
                        <div
                          className="prose prose-sm max-w-none dark:prose-invert"
                          dangerouslySetInnerHTML={{ __html: preview.body_html }}
                        />
                      </div>
                    </div>
                  )}

                  {!preview?.body_html && preview?.body_preview && (
                    <div className="mb-3 rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-700 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300">
                      <div className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">E-Mail-Entwurf</div>
                      {preview.body_preview}
                    </div>
                  )}

                  {/* Fallback: LLM-Output wenn kein Draft geladen werden konnte */}
                  {!preview && hasFailed && job.output && (
                    <div className="mb-3 rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800">
                      <div className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Agent-Output (Entwurf konnte nicht geladen werden)</div>
                      <div className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap max-h-40 overflow-y-auto">
                        {job.output}
                      </div>
                    </div>
                  )}

                  {/* Aktions-Buttons */}
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
                      Ablehnen & Löschen
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="p-8 text-center text-sm text-gray-400 dark:text-gray-600">
            Keine Entwürfe zur Freigabe. Der Agent hat noch keine Antwort-Entwürfe erstellt.
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------- Task Suggestions Section ---------- */

function TaskSuggestionsSection({
  tasks,
  onAction,
}: {
  tasks: PendingReviewTask[];
  onAction: () => void;
}) {
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [editingProject, setEditingProject] = useState<Record<string, string>>({});
  const [processing, setProcessing] = useState<Set<string>>(new Set());

  useEffect(() => {
    api.get<ProjectOption[]>('/api/projects').then(setProjects).catch(() => {});
  }, []);

  const handleConfirm = async (task: PendingReviewTask) => {
    setProcessing(prev => new Set(prev).add(task.id));
    try {
      const newProjectId = editingProject[task.id];
      const body: Record<string, string> = {};
      if (newProjectId && newProjectId !== task.project_id) {
        body.project_id = newProjectId;
      }
      await api.post(`/api/tasks/${task.id}/confirm`, body);
      onAction();
    } catch { /* ignore */ }
    finally { setProcessing(prev => { const n = new Set(prev); n.delete(task.id); return n; }); }
  };

  const handleDismiss = async (taskId: string) => {
    setProcessing(prev => new Set(prev).add(taskId));
    try {
      await api.post(`/api/tasks/${taskId}/dismiss-review`);
      onAction();
    } catch { /* ignore */ }
    finally { setProcessing(prev => { const n = new Set(prev); n.delete(taskId); return n; }); }
  };

  return (
    <div className="mb-6 rounded-xl border border-blue-200 bg-white dark:border-blue-800 dark:bg-gray-900">
      <h3 className="flex items-center gap-2 border-b border-blue-200 px-4 py-3 text-sm font-semibold text-blue-700 dark:border-blue-800 dark:text-blue-300">
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
        </svg>
        Aufgaben-Vorschläge ({tasks.length})
      </h3>
      <div className="divide-y divide-gray-100 dark:divide-gray-800">
        {tasks.map(task => {
          const isProcessing = processing.has(task.id);
          const selectedProject = editingProject[task.id] || task.project_id;

          return (
            <div key={task.id} className="px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-gray-900 dark:text-white">
                    {task.title}
                  </div>
                  {task.description && (
                    <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
                      {task.description}
                    </p>
                  )}
                  <div className="mt-1.5 flex items-center gap-3 text-xs text-gray-400 dark:text-gray-500">
                    {task.due_date && (
                      <span className="flex items-center gap-1">
                        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
                        </svg>
                        {new Date(task.due_date).toLocaleDateString('de-DE')}
                      </span>
                    )}
                    <span>{new Date(task.created_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <select
                    value={selectedProject}
                    onChange={(e) => setEditingProject(prev => ({ ...prev, [task.id]: e.target.value }))}
                    className="rounded-lg border border-gray-200 px-2 py-1 text-xs outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                  >
                    {projects.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => handleConfirm(task)}
                    disabled={isProcessing}
                    className="rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                  >
                    Bestätigen
                  </button>
                  <button
                    onClick={() => handleDismiss(task.id)}
                    disabled={isProcessing}
                    className="rounded-lg border border-red-300 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20 disabled:opacity-50"
                  >
                    Verwerfen
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
