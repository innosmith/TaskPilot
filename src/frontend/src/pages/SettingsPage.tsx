import { useState, useEffect, useCallback, useRef } from 'react';
import { useOutletContext, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { TaskDetailMode } from '../types';

interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  role: string;
  avatar_url: string | null;
}

interface UserSettingsData {
  agenda_background_url?: string | null;
  task_detail_mode?: TaskDetailMode | null;
  sidebar_collapsed?: boolean | null;
  app_logo_url?: string | null;
  sidebar_color?: string | null;
  show_column_count?: boolean | null;
  cockpit_background_url?: string | null;
  cockpit_calendar_exclude_categories?: string | null;
  cockpit_calendar_hide_private?: boolean | null;
}

interface ManagedUser {
  id: string;
  email: string;
  display_name: string;
  role: string;
  avatar_url: string | null;
}

interface TriageSettingsData {
  triage_prompt: string | null;
  triage_interval_seconds: number | null;
  triage_enabled: boolean | null;
  inbox_hidden_folders: string[] | null;
}

interface TriageTestResult {
  id: string;
  message_id: string;
  subject: string | null;
  from_address: string | null;
  triage_class: string | null;
}

interface MemoryFile {
  name: string;
  content: string;
  size: number;
}

interface HeartbeatStatus {
  content: string;
  skills: string[];
  agents_md: string;
}

interface SenderProfile {
  email: string;
  name: string | null;
  total_emails: number;
  auto_reply_count: number;
  task_count: number;
  fyi_count: number;
  reply_rate: number;
  last_seen: string | null;
}

interface TriageStatsData {
  total: number;
  auto_reply: number;
  task: number;
  fyi: number;
  reply_expected_count: number;
  avg_per_day: number;
  period_days: number;
}

interface AgentSkillData {
  name: string;
  description: string;
  content: string;
}

type SettingsTab = 'profile' | 'display' | 'cockpit' | 'llm' | 'integrations' | 'triage' | 'team' | 'intelligence';

export function SettingsPage() {
  const [searchParams] = useSearchParams();
  const initialTab = (searchParams.get('tab') as SettingsTab) || 'profile';
  const [tab, setTab] = useState<SettingsTab>(initialTab);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [settings, setSettings] = useState<UserSettingsData>({});
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(true);
  const { refreshAppSettings } = useOutletContext<{ refreshAppSettings: () => void }>();

  const [displayName, setDisplayName] = useState('');
  const [profileEmail, setProfileEmail] = useState('');
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [pwMsg, setPwMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [profileMsg, setProfileMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const avatarInput = useRef<HTMLInputElement>(null);
  const logoInput = useRef<HTMLInputElement>(null);

  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [inviteRole, setInviteRole] = useState('member');

  const [triagePrompt, setTriagePrompt] = useState('');
  const [triageInterval, setTriageInterval] = useState(2);
  const [triageEnabled, setTriageEnabled] = useState(true);
  const [triageMsg, setTriageMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [triageTestResults, setTriageTestResults] = useState<TriageTestResult[] | null>(null);
  const [triageTesting, setTriageTesting] = useState(false);
  const [hiddenFolders, setHiddenFolders] = useState<string[]>(['ArchivSorted', 'Conversation History', 'Outbox']);
  const [hiddenFolderInput, setHiddenFolderInput] = useState('');

  const [memFiles, setMemFiles] = useState<MemoryFile[]>([]);
  const [heartbeat, setHeartbeat] = useState<HeartbeatStatus | null>(null);
  const [memExpanded, setMemExpanded] = useState<Set<string>>(new Set());
  const [memLoading, setMemLoading] = useState(false);
  const [senderProfiles, setSenderProfiles] = useState<SenderProfile[]>([]);
  const [triageStats, setTriageStats] = useState<TriageStatsData | null>(null);
  const [agentSkills, setAgentSkills] = useState<AgentSkillData[]>([]);
  const [totalSenders, setTotalSenders] = useState(0);

  const [pdToken, setPdToken] = useState('');
  const [pdDomain, setPdDomain] = useState('innosmith');
  const [pdMsg, setPdMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [pdTesting, setPdTesting] = useState(false);

  const [togglToken, setTogglToken] = useState('');
  const [togglWsId, setTogglWsId] = useState('');
  const [togglMsg, setTogglMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [togglTesting, setTogglTesting] = useState(false);

  const [bexioToken, setBexioToken] = useState('');
  const [bexioMsg, setBexioMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [bexioTesting, setBexioTesting] = useState(false);

  const [extApiKey, setExtApiKey] = useState('');
  const [extKeyCreatedAt, setExtKeyCreatedAt] = useState<string | null>(null);
  const [extHasKey, setExtHasKey] = useState(false);
  const [extLoading, setExtLoading] = useState(false);
  const [extMsg, setExtMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [extCopied, setExtCopied] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [p, s] = await Promise.all([
        api.get<UserProfile>('/api/auth/me'),
        api.get<UserSettingsData>('/api/settings'),
      ]);
      setProfile(p);
      setSettings(s);
      setDisplayName(p.display_name);
      setProfileEmail(p.email);
      if (p.role === 'owner') {
        const [u, ts] = await Promise.all([
          api.get<ManagedUser[]>('/api/auth/users'),
          api.get<TriageSettingsData>('/api/settings/triage'),
        ]);
        setUsers(u);
        if (ts.triage_prompt) setTriagePrompt(ts.triage_prompt);
        if (ts.triage_interval_seconds) setTriageInterval(Math.round(ts.triage_interval_seconds / 60));
        if (ts.triage_enabled !== null && ts.triage_enabled !== undefined) setTriageEnabled(ts.triage_enabled);
        if (ts.inbox_hidden_folders) setHiddenFolders(ts.inbox_hidden_folders);
      }
    } catch { /* */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    if (tab !== 'intelligence') return;
    setMemLoading(true);
    Promise.all([
      api.get<HeartbeatStatus>('/api/memory/status/heartbeat').catch(() => null),
      api.get<MemoryFile[]>('/api/memory').catch(() => []),
      api.get<{ profiles: SenderProfile[]; total_senders: number }>('/api/intelligence/sender-profiles?limit=20').catch(() => ({ profiles: [], total_senders: 0 })),
      api.get<TriageStatsData>('/api/intelligence/triage-stats?days=30').catch(() => null),
      api.get<{ skills: AgentSkillData[] }>('/api/intelligence/skills').catch(() => ({ skills: [] })),
    ]).then(([hb, files, sp, ts, sk]) => {
      setHeartbeat(hb);
      setMemFiles(files ?? []);
      setSenderProfiles(sp?.profiles ?? []);
      setTotalSenders(sp?.total_senders ?? 0);
      setTriageStats(ts);
      setAgentSkills(sk?.skills ?? []);
    }).finally(() => setMemLoading(false));
  }, [tab]);

  useEffect(() => {
    if (tab !== 'integrations') return;
    api.get<{ pipedrive_api_token: string | null; pipedrive_domain: string | null; toggl_api_token: string | null; toggl_workspace_id: number | null; bexio_api_token: string | null }>('/api/settings/integrations')
      .then((data) => {
        setPdToken(data.pipedrive_api_token || '');
        setPdDomain(data.pipedrive_domain || 'innosmith');
        setTogglToken(data.toggl_api_token || '');
        setTogglWsId(data.toggl_workspace_id ? String(data.toggl_workspace_id) : '');
        setBexioToken(data.bexio_api_token || '');
      })
      .catch(() => {});
    api.get<{ has_key: boolean; created_at: string | null }>('/api/settings/extension-api-key')
      .then((data) => {
        setExtHasKey(data.has_key);
        setExtKeyCreatedAt(data.created_at);
      })
      .catch(() => {});
  }, [tab]);

  const saveProfile = async () => {
    if (!displayName.trim() || !profileEmail.trim()) return;
    try {
      const body: Record<string, string> = { display_name: displayName.trim() };
      if (profileEmail.trim() !== profile?.email) body.email = profileEmail.trim();
      const updated = await api.patch<UserProfile>('/api/auth/me', body);
      setProfile(updated);
      setProfileEmail(updated.email);
      setProfileMsg({ type: 'ok', text: 'Profil gespeichert' });
      setTimeout(() => setProfileMsg(null), 3000);
    } catch {
      setProfileMsg({ type: 'err', text: 'Fehler beim Speichern' });
    }
  };

  const uploadAvatar = async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch('/api/uploads/avatars', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('taskpilot_token')}` },
        body: form,
      });
      if (!res.ok) throw new Error();
      const { url } = await res.json();
      const updated = await api.patch<UserProfile>('/api/auth/me', { avatar_url: url });
      setProfile(updated);
    } catch { /* */ }
  };

  const changePassword = async () => {
    setPwMsg(null);
    if (newPw !== confirmPw) { setPwMsg({ type: 'err', text: 'Passwörter stimmen nicht überein' }); return; }
    if (newPw.length < 8) { setPwMsg({ type: 'err', text: 'Mindestens 8 Zeichen' }); return; }
    try {
      await api.post('/api/auth/change-password', { current_password: currentPw, new_password: newPw });
      setPwMsg({ type: 'ok', text: 'Passwort geändert' });
      setCurrentPw(''); setNewPw(''); setConfirmPw('');
      setTimeout(() => setPwMsg(null), 3000);
    } catch {
      setPwMsg({ type: 'err', text: 'Aktuelles Passwort ist falsch' });
    }
  };

  const updateSetting = async (key: string, value: string | boolean | null) => {
    const updated = await api.patch<UserSettingsData>('/api/settings', { [key]: value });
    setSettings(updated);
    if (key === 'app_logo_url' || key === 'sidebar_color') {
      refreshAppSettings();
    }
  };

  const createUser = async () => {
    if (!inviteEmail.trim() || !inviteName.trim()) return;
    try {
      await api.post('/api/auth/users', { email: inviteEmail.trim(), display_name: inviteName.trim(), role: inviteRole });
      setInviteEmail(''); setInviteName(''); setInviteRole('member');
      const u = await api.get<ManagedUser[]>('/api/auth/users');
      setUsers(u);
    } catch { /* */ }
  };

  const toggleUserActive = async (userId: string, currentlyActive: boolean) => {
    await api.patch(`/api/auth/users/${userId}`, { is_active: !currentlyActive });
    const u = await api.get<ManagedUser[]>('/api/auth/users');
    setUsers(u);
  };

  const saveTriageSettings = async () => {
    try {
      await api.put<TriageSettingsData>('/api/settings/triage', {
        triage_prompt: triagePrompt || null,
        triage_interval_seconds: triageInterval * 60,
        triage_enabled: triageEnabled,
        inbox_hidden_folders: hiddenFolders.length > 0 ? hiddenFolders : null,
      });
      setTriageMsg({ type: 'ok', text: 'Triage-Einstellungen gespeichert' });
      setTimeout(() => setTriageMsg(null), 3000);
    } catch {
      setTriageMsg({ type: 'err', text: 'Fehler beim Speichern' });
    }
  };

  const testTriage = async () => {
    setTriageTesting(true);
    setTriageTestResults(null);
    try {
      const result = await api.post<{ classified: number }>('/api/triage/run?top=5');
      const items = await api.get<TriageTestResult[]>('/api/triage?limit=5');
      setTriageTestResults(items);
      setTriageMsg({ type: 'ok', text: `${result.classified} E-Mails klassifiziert` });
      setTimeout(() => setTriageMsg(null), 5000);
    } catch {
      setTriageMsg({ type: 'err', text: 'Test-Triage fehlgeschlagen' });
    } finally {
      setTriageTesting(false);
    }
  };

  const toggleMemFile = (name: string) => {
    setMemExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const saveIntegrations = async () => {
    setPdMsg(null); setTogglMsg(null); setBexioMsg(null);
    try {
      const payload: Record<string, string | number> = { pipedrive_domain: pdDomain };
      if (pdToken && !pdToken.startsWith('****')) payload.pipedrive_api_token = pdToken;
      if (togglToken && !togglToken.startsWith('****')) payload.toggl_api_token = togglToken;
      if (togglWsId) payload.toggl_workspace_id = parseInt(togglWsId) || 0;
      if (bexioToken && !bexioToken.startsWith('****')) payload.bexio_api_token = bexioToken;
      const data = await api.put<{ pipedrive_api_token: string | null; pipedrive_domain: string | null; toggl_api_token: string | null; toggl_workspace_id: number | null; bexio_api_token: string | null }>('/api/settings/integrations', payload);
      setPdToken(data.pipedrive_api_token || '');
      setPdDomain(data.pipedrive_domain || 'innosmith');
      setTogglToken(data.toggl_api_token || '');
      setTogglWsId(data.toggl_workspace_id ? String(data.toggl_workspace_id) : '');
      setBexioToken(data.bexio_api_token || '');
      setPdMsg({ type: 'ok', text: 'Einstellungen gespeichert' });
      setTimeout(() => setPdMsg(null), 3000);
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      setPdMsg({ type: 'err', text: `Fehler beim Speichern: ${detail}` });
    }
  };

  const testPipedrive = async () => {
    setPdTesting(true);
    setPdMsg(null);
    try {
      const result = await api.get<{ ok: boolean; name: string; company: string }>('/api/pipedrive/test-connection');
      if (result.ok) {
        setPdMsg({ type: 'ok', text: `Verbunden als ${result.name} (${result.company})` });
      } else {
        setPdMsg({ type: 'err', text: 'Verbindung fehlgeschlagen' });
      }
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      setPdMsg({ type: 'err', text: `Verbindungstest fehlgeschlagen: ${detail}` });
    } finally {
      setPdTesting(false);
    }
  };

  const testToggl = async () => {
    setTogglTesting(true);
    setTogglMsg(null);
    try {
      const result = await api.get<{ ok: boolean; name: string; email: string; default_workspace_id: number }>('/api/toggl/test-connection');
      if (result.ok) {
        setTogglMsg({ type: 'ok', text: `Verbunden als ${result.name} (${result.email})` });
        if (result.default_workspace_id && !togglWsId) {
          setTogglWsId(String(result.default_workspace_id));
        }
      } else {
        setTogglMsg({ type: 'err', text: 'Verbindung fehlgeschlagen' });
      }
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      setTogglMsg({ type: 'err', text: `Verbindungstest fehlgeschlagen: ${detail}` });
    } finally {
      setTogglTesting(false);
    }
  };

  const testBexio = async () => {
    setBexioTesting(true);
    setBexioMsg(null);
    try {
      const result = await api.get<{ ok: boolean; name: string; email: string }>('/api/bexio/test-connection');
      if (result.ok) {
        setBexioMsg({ type: 'ok', text: `Verbunden als ${result.name} (${result.email})` });
      } else {
        setBexioMsg({ type: 'err', text: 'Verbindung fehlgeschlagen' });
      }
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      setBexioMsg({ type: 'err', text: `Verbindungstest fehlgeschlagen: ${detail}` });
    } finally {
      setBexioTesting(false);
    }
  };

  const generateExtApiKey = async () => {
    setExtLoading(true);
    setExtMsg(null);
    setExtApiKey('');
    setExtCopied(false);
    try {
      const data = await api.post<{ api_key: string; created_at: string }>('/api/settings/extension-api-key', {});
      setExtApiKey(data.api_key);
      setExtHasKey(true);
      setExtKeyCreatedAt(data.created_at);
      setExtMsg({ type: 'ok', text: 'API-Key generiert — jetzt kopieren und in der Extension einfuegen!' });
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      setExtMsg({ type: 'err', text: `Fehler: ${detail}` });
    } finally {
      setExtLoading(false);
    }
  };

  const revokeExtApiKey = async () => {
    setExtLoading(true);
    setExtMsg(null);
    try {
      await api.delete('/api/settings/extension-api-key');
      setExtHasKey(false);
      setExtKeyCreatedAt(null);
      setExtApiKey('');
      setExtMsg({ type: 'ok', text: 'API-Key widerrufen' });
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      setExtMsg({ type: 'err', text: `Fehler: ${detail}` });
    } finally {
      setExtLoading(false);
    }
  };

  const copyExtApiKey = () => {
    if (!extApiKey) return;
    navigator.clipboard.writeText(extApiKey);
    setExtCopied(true);
    setTimeout(() => setExtCopied(false), 3000);
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-3 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  const isOwner = profile?.role === 'owner';
  const tabs: { id: SettingsTab; label: string }[] = [
    { id: 'profile', label: 'Profil' },
    { id: 'display', label: 'Erscheinungsbild' },
    { id: 'cockpit', label: 'Cockpit' },
    { id: 'llm', label: 'LLM-Modelle' },
    ...(isOwner ? [{ id: 'integrations' as const, label: 'Integrationen' }] : []),
    ...(isOwner ? [{ id: 'triage' as const, label: 'E-Mail-Triage' }] : []),
    ...(isOwner ? [{ id: 'team' as const, label: 'Team' }] : []),
    { id: 'intelligence', label: 'Intelligenz' },
  ];

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-white/40 bg-white/50 px-4 py-4 sm:px-6 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/50">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Einstellungen</h1>
      </div>

      <div className="border-b border-white/40 bg-white/50 px-4 sm:px-6 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/50">
        <div className="scrollbar-hide flex gap-4 overflow-x-auto">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`shrink-0 whitespace-nowrap border-b-2 px-1 py-3 text-sm font-medium transition-colors ${
                tab === t.id
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto overflow-x-hidden overscroll-x-none p-4 sm:p-6">
        <div className="mx-auto max-w-2xl space-y-8 rounded-2xl border border-white/40 bg-white/60 p-6 shadow-sm backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/60">

          {/* ── Profil ── */}
          {tab === 'profile' && profile && (
            <>
              <section>
                <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Profil</h2>
                <div className="space-y-4">
                  <div className="flex items-center gap-4">
                    <div
                      className="group relative h-16 w-16 cursor-pointer overflow-hidden rounded-full bg-gray-200 dark:bg-gray-800"
                      onClick={() => avatarInput.current?.click()}
                    >
                      {profile.avatar_url ? (
                        <img src={profile.avatar_url} alt="" className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-xl font-bold text-gray-500 dark:text-gray-400">
                          {profile.display_name.charAt(0).toUpperCase()}
                        </div>
                      )}
                      <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
                        <CameraIcon className="h-5 w-5 text-white" />
                      </div>
                    </div>
                    <input ref={avatarInput} type="file" accept="image/*" className="hidden" onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) uploadAvatar(f);
                    }} />
                    <div>
                      <p className="font-medium text-gray-900 dark:text-white">{profile.display_name}</p>
                      <p className="text-sm text-gray-500 dark:text-gray-400">{profile.email}</p>
                    </div>
                  </div>

                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Anzeigename</label>
                    <div className="flex gap-2">
                      <input
                        value={displayName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        className="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                      />
                      <button
                        onClick={saveProfile}
                        disabled={!displayName.trim() || !profileEmail.trim() || (displayName === profile.display_name && profileEmail === profile.email)}
                        className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-40"
                      >
                        Speichern
                      </button>
                    </div>
                    {profileMsg && (
                      <p className={`mt-1 text-xs ${profileMsg.type === 'ok' ? 'text-green-600' : 'text-red-600'}`}>{profileMsg.text}</p>
                    )}
                  </div>

                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">E-Mail</label>
                    <input
                      value={profileEmail}
                      onChange={e => setProfileEmail(e.target.value)}
                      type="email"
                      className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                    />
                  </div>
                </div>
              </section>

              <section>
                <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Passwort ändern</h2>
                <div className="space-y-3">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Aktuelles Passwort</label>
                    <input
                      type="password"
                      value={currentPw}
                      onChange={(e) => setCurrentPw(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Neues Passwort</label>
                    <input
                      type="password"
                      value={newPw}
                      onChange={(e) => setNewPw(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Passwort bestätigen</label>
                    <input
                      type="password"
                      value={confirmPw}
                      onChange={(e) => setConfirmPw(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                    />
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={changePassword}
                      disabled={!currentPw || !newPw || !confirmPw}
                      className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-40"
                    >
                      Passwort ändern
                    </button>
                    {pwMsg && (
                      <p className={`text-sm ${pwMsg.type === 'ok' ? 'text-green-600' : 'text-red-600'}`}>{pwMsg.text}</p>
                    )}
                  </div>
                </div>
              </section>
            </>
          )}

          {/* ── Erscheinungsbild ── */}
          {tab === 'display' && (
            <section>
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Erscheinungsbild</h2>
              <div className="space-y-6">

                {/* Firmenlogo - jetzt prominenter */}
                <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-4 dark:border-indigo-900 dark:bg-indigo-950/30">
                  <label className="mb-1 block text-sm font-semibold text-gray-900 dark:text-white">Firmenlogo / App-Icon</label>
                  <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
                    Wird oben links in der Sidebar als App-Logo angezeigt. Ideal: quadratisches Bild (z.B. 128×128 px).
                  </p>
                  <div className="flex items-center gap-3">
                    <div
                      className="group relative flex h-14 w-14 cursor-pointer items-center justify-center overflow-hidden rounded-xl border-2 border-dashed border-indigo-300 bg-white dark:border-indigo-700 dark:bg-gray-800"
                      onClick={() => logoInput.current?.click()}
                    >
                      {settings.app_logo_url ? (
                        <img src={settings.app_logo_url} alt="" className="h-full w-full object-cover" />
                      ) : (
                        <span className="text-2xl font-bold text-gray-300 dark:text-gray-600">T</span>
                      )}
                      <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
                        <CameraIcon className="h-5 w-5 text-white" />
                      </div>
                    </div>
                    <input ref={logoInput} type="file" accept="image/*" className="hidden" onChange={async (e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      const form = new FormData();
                      form.append('file', file);
                      try {
                        const res = await fetch('/api/uploads/icons', {
                          method: 'POST',
                          headers: { Authorization: `Bearer ${localStorage.getItem('taskpilot_token')}` },
                          body: form,
                        });
                        if (!res.ok) return;
                        const { url } = await res.json();
                        await updateSetting('app_logo_url', url);
                      } catch { /* */ }
                    }} />
                    <div className="flex flex-col gap-1">
                      <button
                        onClick={() => logoInput.current?.click()}
                        className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-700"
                      >
                        Logo hochladen
                      </button>
                      {settings.app_logo_url && (
                        <button
                          onClick={() => updateSetting('app_logo_url', null)}
                          className="rounded-lg px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
                        >
                          Entfernen
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {/* Task-Anzahl in Spalten */}
                <div className="flex items-center justify-between rounded-lg border border-gray-200 p-4 dark:border-gray-700">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">Task-Anzahl in Spalten</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Zeigt die Anzahl Aufgaben pro Spalte in Agenda und Projekt-Boards an
                    </p>
                  </div>
                  <button
                    onClick={() => updateSetting('show_column_count', !(settings.show_column_count ?? false))}
                    className={`relative h-6 w-11 rounded-full transition-colors ${(settings.show_column_count ?? false) ? 'bg-indigo-600' : 'bg-gray-300 dark:bg-gray-600'}`}
                  >
                    <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${(settings.show_column_count ?? false) ? 'left-[22px]' : 'left-0.5'}`} />
                  </button>
                </div>

                <div>
                  <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">Task-Detail Ansicht</label>
                  <div className="flex gap-2">
                    {([
                      { value: 'modal', label: 'Modal', icon: <ModalIcon className="h-4 w-4" /> },
                      { value: 'panel', label: 'Seitenpanel', icon: <PanelIcon className="h-4 w-4" /> },
                      { value: 'fullscreen', label: 'Vollbild', icon: <FullscreenIcon className="h-4 w-4" /> },
                    ] as const).map((opt) => (
                      <button
                        key={opt.value}
                        onClick={() => updateSetting('task_detail_mode', opt.value)}
                        className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                          (settings.task_detail_mode || 'modal') === opt.value
                            ? 'bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200 dark:bg-indigo-950 dark:text-indigo-300 dark:ring-indigo-800'
                            : 'bg-gray-50 text-gray-600 hover:bg-gray-100 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'
                        }`}
                      >
                        {opt.icon}
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">Sidebar-Farbe</label>
                  <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                    Hintergrundfarbe für die Sidebar (passt sich an Light/Dark an).
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {SIDEBAR_PALETTE.map((c) => (
                      <button
                        key={c.key}
                        onClick={() => updateSetting('sidebar_color', c.key === 'default' ? null : c.key)}
                        className={`flex h-10 w-10 items-center justify-center rounded-lg border-2 transition-all ${
                          (settings.sidebar_color || 'default') === c.key
                            ? 'border-indigo-500 ring-2 ring-indigo-200 dark:ring-indigo-800'
                            : 'border-gray-200 dark:border-gray-700'
                        }`}
                        title={c.label}
                      >
                        <span className={`h-6 w-6 rounded-md ${c.swatch}`} />
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">Agenda-Hintergrund</label>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {settings.agenda_background_url ? 'Hintergrund gesetzt' : 'Kein Hintergrund gesetzt'} — kann in der Agenda-Ansicht geändert werden.
                  </p>
                  {settings.agenda_background_url && (
                    <button
                      onClick={() => updateSetting('agenda_background_url', null)}
                      className="mt-2 rounded-lg px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
                    >
                      Hintergrund entfernen
                    </button>
                  )}
                </div>
              </div>
            </section>
          )}

          {/* ── Cockpit ── */}
          {tab === 'cockpit' && (
            <section>
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Cockpit-Einstellungen</h2>
              <div className="space-y-6">

                <div>
                  <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">Cockpit-Hintergrund</label>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {settings.cockpit_background_url ? 'Hintergrund gesetzt' : 'Kein Hintergrund gesetzt'} — kann auch in der Cockpit-Ansicht geändert werden.
                  </p>
                  {settings.cockpit_background_url && (
                    <button
                      onClick={() => updateSetting('cockpit_background_url', null)}
                      className="mt-2 rounded-lg px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
                    >
                      Hintergrund entfernen
                    </button>
                  )}
                </div>

                <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-4 dark:border-indigo-900 dark:bg-indigo-950/30">
                  <label className="mb-1 block text-sm font-semibold text-gray-900 dark:text-white">Kalender-Kategorien ausblenden</label>
                  <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
                    Termine mit diesen Kategorien werden im Cockpit nicht angezeigt. Mehrere Kategorien mit Komma trennen (z.B. «Transfer, Privat, Lunch»).
                  </p>
                  <input
                    value={settings.cockpit_calendar_exclude_categories ?? 'Transfer, Privat'}
                    onChange={(e) => updateSetting('cockpit_calendar_exclude_categories', e.target.value || null)}
                    placeholder="z.B. Transfer, Privat, Lunch"
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                  />
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {(settings.cockpit_calendar_exclude_categories ?? 'Transfer, Privat').split(',').map((cat, i) => {
                      const trimmed = cat.trim();
                      if (!trimmed) return null;
                      return (
                        <span key={i} className="inline-flex items-center gap-1 rounded-full bg-gray-200 px-2.5 py-0.5 text-xs font-medium text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                          {trimmed}
                          <button
                            onClick={() => {
                              const cats = (settings.cockpit_calendar_exclude_categories ?? 'Transfer, Privat')
                                .split(',').map(c => c.trim()).filter(c => c && c !== trimmed);
                              updateSetting('cockpit_calendar_exclude_categories', cats.join(', ') || null);
                            }}
                            className="ml-0.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                          >×</button>
                        </span>
                      );
                    })}
                  </div>
                </div>

                <div className="flex items-center justify-between rounded-lg border border-gray-200 p-4 dark:border-gray-700">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">Private Termine ausblenden</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Termine mit Vertraulichkeit «Privat» (sensitivity) im Cockpit verbergen
                    </p>
                  </div>
                  <button
                    onClick={() => updateSetting('cockpit_calendar_hide_private', !(settings.cockpit_calendar_hide_private ?? true))}
                    className={`relative h-6 w-11 rounded-full transition-colors ${(settings.cockpit_calendar_hide_private ?? true) ? 'bg-indigo-600' : 'bg-gray-300 dark:bg-gray-600'}`}
                  >
                    <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${(settings.cockpit_calendar_hide_private ?? true) ? 'left-[22px]' : 'left-0.5'}`} />
                  </button>
                </div>

              </div>
            </section>
          )}

          {/* ── Integrationen ── */}
          {tab === 'integrations' && isOwner && (
            <section>
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Integrationen</h2>
              <div className="space-y-6">

                <div className="rounded-xl border border-orange-200 bg-orange-50/50 p-5 dark:border-orange-900 dark:bg-orange-950/30">
                  <div className="mb-3 flex items-center gap-3">
                    <PipedriveIcon className="h-8 w-8" />
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Pipedrive CRM</h3>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        Deals, Leads, Kontakte und Aktivitäten synchronisieren
                      </p>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">API-Token</label>
                      <input
                        type="password"
                        value={pdToken}
                        onChange={(e) => setPdToken(e.target.value)}
                        placeholder="Pipedrive API-Token eingeben"
                        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                      />
                      <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                        Zu finden unter: Pipedrive → Einstellungen → Persönliche Einstellungen → API
                      </p>
                    </div>

                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Firmen-Domain</label>
                      <div className="flex items-center gap-0">
                        <input
                          value={pdDomain}
                          onChange={(e) => setPdDomain(e.target.value)}
                          className="rounded-l-lg border border-r-0 border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                        />
                        <span className="rounded-r-lg border border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
                          .pipedrive.com
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 flex items-center gap-3">
                    <button
                      onClick={saveIntegrations}
                      className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700"
                    >
                      Speichern
                    </button>
                    <button
                      onClick={testPipedrive}
                      disabled={pdTesting}
                      className="rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-700 disabled:opacity-50"
                    >
                      {pdTesting ? 'Teste...' : 'Verbindung testen'}
                    </button>
                    {pdMsg && (
                      <span className={`text-sm ${pdMsg.type === 'ok' ? 'text-green-600' : 'text-red-600'}`}>
                        {pdMsg.text}
                      </span>
                    )}
                  </div>
                </div>

              </div>

              {/* ── Toggl Track ── */}
              <div className="mt-6 rounded-xl border border-gray-200 p-5 dark:border-gray-700">
                <div className="mb-4 flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-pink-100 dark:bg-pink-900/30">
                    <svg className="h-5 w-5 text-pink-600 dark:text-pink-400" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Toggl Track</h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400">Zeiterfassung, Kunden und Projekte</p>
                  </div>
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">API-Token</label>
                    <input type="password" className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white" value={togglToken} onChange={(e) => setTogglToken(e.target.value)} placeholder="Toggl API-Token eingeben" />
                    <p className="mt-1 text-[10px] text-gray-400">Zu finden unter: Toggl Track → Profile Settings → API Token</p>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Workspace-ID</label>
                    <input type="text" className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white" value={togglWsId} onChange={(e) => setTogglWsId(e.target.value)} placeholder="Wird nach Test automatisch gesetzt" />
                  </div>
                  <div className="flex items-center gap-3 pt-2">
                    <button onClick={saveIntegrations} className="rounded-lg bg-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600">Speichern</button>
                    <button onClick={testToggl} disabled={togglTesting} className="rounded-lg bg-pink-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-pink-700 disabled:opacity-50">
                      {togglTesting ? 'Teste...' : 'Verbindung testen'}
                    </button>
                    {togglMsg && (
                      <span className={`text-sm ${togglMsg.type === 'ok' ? 'text-green-600' : 'text-red-600'}`}>{togglMsg.text}</span>
                    )}
                  </div>
                </div>
              </div>

              {/* ── Bexio ── */}
              <div className="mt-6 rounded-xl border border-gray-200 p-5 dark:border-gray-700">
                <div className="mb-4 flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-100 dark:bg-blue-900/30">
                    <svg className="h-5 w-5 text-blue-600 dark:text-blue-400" fill="currentColor" viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 3c1.93 0 3.5 1.57 3.5 3.5S13.93 13 12 13s-3.5-1.57-3.5-3.5S10.07 6 12 6zm7 13H5v-.23c0-.62.28-1.2.76-1.58C7.47 15.82 9.64 15 12 15s4.53.82 6.24 2.19c.48.38.76.97.76 1.58V19z"/></svg>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Bexio</h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400">Buchhaltung, Kontakte und Aufträge</p>
                  </div>
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">API-Token</label>
                    <input type="password" className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white" value={bexioToken} onChange={(e) => setBexioToken(e.target.value)} placeholder="Bexio API-Token eingeben" />
                    <p className="mt-1 text-[10px] text-gray-400">Zu finden unter: Bexio → Einstellungen → Sicherheit → API-Zugänge</p>
                  </div>
                  <div className="flex items-center gap-3 pt-2">
                    <button onClick={saveIntegrations} className="rounded-lg bg-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600">Speichern</button>
                    <button onClick={testBexio} disabled={bexioTesting} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50">
                      {bexioTesting ? 'Teste...' : 'Verbindung testen'}
                    </button>
                    {bexioMsg && (
                      <span className={`text-sm ${bexioMsg.type === 'ok' ? 'text-green-600' : 'text-red-600'}`}>{bexioMsg.text}</span>
                    )}
                  </div>
                </div>
              </div>

              {/* ── Browser Extension (LinkedIn Sync) ── */}
              <div className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50/50 p-5 dark:border-emerald-900 dark:bg-emerald-950/30">
                <div className="mb-3 flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-100 dark:bg-emerald-900/30">
                    <svg className="h-5 w-5 text-emerald-600 dark:text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Browser-Extension (LinkedIn Sync)</h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      API-Key fuer die Chrome-Extension zur LinkedIn-Pipedrive-Synchronisation
                    </p>
                  </div>
                </div>

                <div className="space-y-3">
                  {extHasKey && !extApiKey && (
                    <div className="flex items-center gap-2 rounded-lg bg-emerald-100 p-3 dark:bg-emerald-900/40">
                      <svg className="h-4 w-4 text-emerald-600 dark:text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span className="text-sm text-emerald-700 dark:text-emerald-300">
                        API-Key aktiv{extKeyCreatedAt ? ` (erstellt: ${new Date(extKeyCreatedAt).toLocaleDateString('de-CH')})` : ''}
                      </span>
                    </div>
                  )}

                  {extApiKey && (
                    <div className="space-y-2">
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Dein API-Key (nur jetzt sichtbar!)
                      </label>
                      <div className="flex items-center gap-2">
                        <code className="flex-1 break-all rounded-lg border border-gray-300 bg-gray-50 p-2.5 font-mono text-xs text-gray-800 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200">
                          {extApiKey}
                        </code>
                        <button
                          onClick={copyExtApiKey}
                          className="shrink-0 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700"
                        >
                          {extCopied ? 'Kopiert!' : 'Kopieren'}
                        </button>
                      </div>
                      <p className="text-xs text-amber-600 dark:text-amber-400">
                        Dieser Key wird nur einmal angezeigt. Kopiere ihn jetzt in die Extension-Einstellungen.
                      </p>
                    </div>
                  )}

                  <div className="flex flex-wrap items-center gap-3 pt-1">
                    <button
                      onClick={generateExtApiKey}
                      disabled={extLoading}
                      className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-50"
                    >
                      {extLoading ? 'Generiere...' : extHasKey ? 'Neuen Key generieren' : 'API-Key generieren'}
                    </button>
                    {extHasKey && (
                      <button
                        onClick={revokeExtApiKey}
                        disabled={extLoading}
                        className="rounded-lg bg-red-100 px-4 py-2 text-sm font-medium text-red-700 transition-colors hover:bg-red-200 disabled:opacity-50 dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50"
                      >
                        Key widerrufen
                      </button>
                    )}
                  </div>

                  {extMsg && (
                    <p className={`text-sm ${extMsg.type === 'ok' ? 'text-green-600' : 'text-red-600'}`}>
                      {extMsg.text}
                    </p>
                  )}

                  <p className="text-[10px] text-gray-400 dark:text-gray-500">
                    Der Key beginnt mit <code className="rounded bg-gray-100 px-1 dark:bg-gray-800">tpk_</code> und laeuft nicht ab.
                    Beim Generieren eines neuen Keys wird der vorherige automatisch ungueltig.
                  </p>
                </div>
              </div>

            </section>
          )}

          {/* ── E-Mail-Triage ── */}
          {tab === 'triage' && isOwner && (
            <section>
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">E-Mail-Triage</h2>
              <div className="space-y-6">

                <div className="flex items-center justify-between rounded-lg border border-gray-200 p-4 dark:border-gray-700">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">Automatische Triage aktiv</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Neue E-Mails werden automatisch klassifiziert
                    </p>
                  </div>
                  <button
                    onClick={() => setTriageEnabled(!triageEnabled)}
                    className={`relative h-6 w-11 rounded-full transition-colors ${triageEnabled ? 'bg-indigo-600' : 'bg-gray-300 dark:bg-gray-600'}`}
                  >
                    <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${triageEnabled ? 'left-[22px]' : 'left-0.5'}`} />
                  </button>
                </div>

                <div>
                  <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Triage-Intervall: {triageInterval} Min.
                  </label>
                  <input
                    type="range"
                    min={1}
                    max={10}
                    value={triageInterval}
                    onChange={(e) => setTriageInterval(Number(e.target.value))}
                    className="w-full accent-indigo-600"
                  />
                  <div className="flex justify-between text-xs text-gray-400">
                    <span>1 Min.</span>
                    <span>10 Min.</span>
                  </div>
                </div>

                <div>
                  <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Triage-Prompt (System-Prompt für die Klassifikation)
                  </label>
                  <textarea
                    value={triagePrompt}
                    onChange={(e) => setTriagePrompt(e.target.value)}
                    rows={12}
                    placeholder="Standard-Prompt wird verwendet wenn leer..."
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white font-mono"
                  />
                </div>

                <div>
                  <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Ausgeblendete Posteingangs-Ordner
                  </label>
                  <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                    Diese Ordner werden im Posteingang nicht angezeigt.
                  </p>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {hiddenFolders.map(f => (
                      <span key={f} className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                        {f}
                        <button
                          onClick={() => setHiddenFolders(prev => prev.filter(x => x !== f))}
                          className="ml-0.5 text-gray-400 hover:text-red-500"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={hiddenFolderInput}
                      onChange={e => setHiddenFolderInput(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter' && hiddenFolderInput.trim()) {
                          const name = hiddenFolderInput.trim();
                          if (!hiddenFolders.includes(name)) setHiddenFolders(prev => [...prev, name]);
                          setHiddenFolderInput('');
                        }
                      }}
                      placeholder="Ordnername eingeben..."
                      className="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                    />
                    <button
                      onClick={() => {
                        const name = hiddenFolderInput.trim();
                        if (name && !hiddenFolders.includes(name)) setHiddenFolders(prev => [...prev, name]);
                        setHiddenFolderInput('');
                      }}
                      className="shrink-0 rounded-lg bg-gray-200 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
                    >
                      Hinzufügen
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    onClick={saveTriageSettings}
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700"
                  >
                    Einstellungen speichern
                  </button>
                  <button
                    onClick={testTriage}
                    disabled={triageTesting}
                    className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-700 disabled:opacity-50"
                  >
                    {triageTesting ? 'Teste...' : 'Test-Triage (5 E-Mails)'}
                  </button>
                  {triageMsg && (
                    <span className={`text-sm ${triageMsg.type === 'ok' ? 'text-green-600' : 'text-red-600'}`}>
                      {triageMsg.text}
                    </span>
                  )}
                </div>

                {triageTestResults && triageTestResults.length > 0 && (
                  <div className="rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
                    <h3 className="px-4 py-2 text-sm font-semibold text-gray-700 bg-gray-50 dark:bg-gray-900 dark:text-gray-300">
                      Test-Ergebnisse
                    </h3>
                    <div className="divide-y divide-gray-200 dark:divide-gray-700">
                      {triageTestResults.map((r) => (
                        <div key={r.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                            r.triage_class === 'auto_reply' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' :
                            r.triage_class === 'task' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300' :
                            'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                          }`}>
                            {r.triage_class}
                          </span>
                          <span className="flex-1 truncate text-gray-700 dark:text-gray-300">{r.subject}</span>
                          <span className="shrink-0 text-xs text-gray-400">{r.from_address}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* ── Team (ehemals Admin) ── */}
          {tab === 'team' && isOwner && (
            <section>
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Team & Benutzerverwaltung</h2>

              <div className="mb-6 rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-900/50">
                <h3 className="mb-3 text-sm font-semibold text-gray-700 dark:text-gray-300">Neuen Benutzer einladen</h3>
                <div className="flex flex-wrap gap-3">
                  <input
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="E-Mail"
                    className="min-w-[180px] flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                  />
                  <input
                    value={inviteName}
                    onChange={(e) => setInviteName(e.target.value)}
                    placeholder="Name"
                    className="min-w-[140px] flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                  />
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                  >
                    <option value="member">Mitglied</option>
                    <option value="viewer">Betrachter</option>
                  </select>
                  <button
                    onClick={createUser}
                    disabled={!inviteEmail.trim() || !inviteName.trim()}
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-40"
                  >
                    Einladen
                  </button>
                </div>
              </div>

              <div className="overflow-hidden rounded-xl border border-gray-200 dark:border-gray-800">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900/60">
                      <th className="px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Name</th>
                      <th className="px-4 py-3 font-medium text-gray-500 dark:text-gray-400">E-Mail</th>
                      <th className="px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Rolle</th>
                      <th className="px-4 py-3 text-right font-medium text-gray-500 dark:text-gray-400">Aktionen</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                    {users.map((u) => (
                      <tr key={u.id} className="bg-white dark:bg-gray-900">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            {u.avatar_url ? (
                              <img src={u.avatar_url} alt="" className="h-6 w-6 rounded-full object-cover" />
                            ) : (
                              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-gray-200 text-xs font-bold text-gray-500 dark:bg-gray-700 dark:text-gray-400">
                                {u.display_name.charAt(0).toUpperCase()}
                              </div>
                            )}
                            <span className="font-medium text-gray-900 dark:text-white">{u.display_name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{u.email}</td>
                        <td className="px-4 py-3">
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            u.role === 'owner' ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' :
                            u.role === 'member' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300' :
                            'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                          }`}>
                            {u.role === 'owner' ? 'Inhaber' : u.role === 'member' ? 'Mitglied' : 'Betrachter'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          {u.role !== 'owner' && (
                            <button
                              onClick={() => toggleUserActive(u.id, true)}
                              className="rounded-lg px-2.5 py-1 text-xs font-medium text-red-500 transition-colors hover:bg-red-50 dark:hover:bg-red-950"
                            >
                              Deaktivieren
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {tab === 'llm' && (
            <LlmSettingsTab />
          )}

          {/* ── Intelligenz ── */}
          {tab === 'intelligence' && (
            <section>
              <h2 className="mb-1 text-lg font-semibold text-gray-900 dark:text-white">Intelligenz</h2>
              <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
                Systemwissen — Triage-Statistiken, Agent-Skills, Memory und Absenderprofile
              </p>

              {memLoading ? (
                <div className="flex h-32 items-center justify-center">
                  <div className="h-8 w-8 animate-spin rounded-full border-3 border-indigo-500 border-t-transparent" />
                </div>
              ) : (
                <div className="space-y-2">

                  {/* Triage-Statistiken */}
                  {triageStats && (
                    <CollapsibleBlock
                      id="triage-stats"
                      title="Triage-Statistiken"
                      subtitle={`Letzte ${triageStats.period_days} Tage · ${triageStats.total} E-Mails`}
                      expanded={memExpanded}
                      toggle={toggleMemFile}
                      defaultOpen
                    >
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <div className="rounded-lg bg-gray-50 p-3 text-center dark:bg-gray-800">
                          <div className="text-2xl font-bold text-gray-900 dark:text-white">{triageStats.total}</div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">Gesamt</div>
                        </div>
                        <div className="rounded-lg bg-green-50 p-3 text-center dark:bg-green-900/20">
                          <div className="text-2xl font-bold text-green-700 dark:text-green-300">{triageStats.auto_reply}</div>
                          <div className="text-xs text-green-600 dark:text-green-400">Auto-Reply</div>
                        </div>
                        <div className="rounded-lg bg-blue-50 p-3 text-center dark:bg-blue-900/20">
                          <div className="text-2xl font-bold text-blue-700 dark:text-blue-300">{triageStats.task}</div>
                          <div className="text-xs text-blue-600 dark:text-blue-400">Aufgaben</div>
                        </div>
                        <div className="rounded-lg bg-gray-50 p-3 text-center dark:bg-gray-800">
                          <div className="text-2xl font-bold text-gray-700 dark:text-gray-300">{triageStats.fyi}</div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">FYI</div>
                        </div>
                      </div>
                      <div className="mt-3 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                        <span>⌀ {triageStats.avg_per_day} E-Mails/Tag</span>
                        <span>{triageStats.reply_expected_count} mit erwarteter Antwort</span>
                      </div>
                    </CollapsibleBlock>
                  )}

                  {/* Agent-Skills */}
                  {agentSkills.length > 0 && agentSkills.map((skill) => (
                    <CollapsibleBlock
                      key={`skill-${skill.name}`}
                      id={`skill-${skill.name}`}
                      title={skill.name}
                      subtitle={skill.description}
                      badge={<span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">Skill</span>}
                      expanded={memExpanded}
                      toggle={toggleMemFile}
                    >
                      <div className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-sm leading-relaxed text-gray-800 dark:bg-gray-800 dark:text-gray-200">
                        {skill.content || <span className="italic text-gray-400">Kein Inhalt</span>}
                      </div>
                    </CollapsibleBlock>
                  ))}

                  {/* Memory-Dateien */}
                  {memFiles.map((file) => (
                    <CollapsibleBlock
                      key={`mem-${file.name}`}
                      id={`mem-${file.name}`}
                      title={file.name}
                      subtitle=""
                      badge={
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                          {file.size < 1024 ? `${file.size} B` : `${(file.size / 1024).toFixed(1)} KB`}
                        </span>
                      }
                      expanded={memExpanded}
                      toggle={toggleMemFile}
                    >
                      <div className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-sm text-gray-800 dark:bg-gray-800 dark:text-gray-200">
                        {file.content || <span className="italic text-gray-400">Leer</span>}
                      </div>
                    </CollapsibleBlock>
                  ))}

                  {/* Absenderprofile */}
                  {senderProfiles.length > 0 && (
                    <CollapsibleBlock
                      id="sender-profiles"
                      title="Absenderprofile"
                      subtitle={`${totalSenders} Absender bekannt`}
                      expanded={memExpanded}
                      toggle={toggleMemFile}
                    >
                      <div className="divide-y divide-gray-100 dark:divide-gray-800">
                        {senderProfiles.map((sp) => (
                          <div key={sp.email} className="flex items-center gap-3 py-2.5">
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-300">
                              {(sp.name || sp.email).charAt(0).toUpperCase()}
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-medium text-gray-900 dark:text-white">
                                {sp.name || sp.email}
                              </p>
                              <p className="truncate text-xs text-gray-400 dark:text-gray-500">{sp.email}</p>
                            </div>
                            <div className="flex shrink-0 items-center gap-2">
                              <span className="rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-900/30 dark:text-green-300">{sp.auto_reply_count}</span>
                              <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">{sp.task_count}</span>
                              <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">{sp.fyi_count}</span>
                              <span className="text-xs text-gray-400 dark:text-gray-500">{sp.total_emails}×</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </CollapsibleBlock>
                  )}

                  {/* Heartbeat */}
                  {heartbeat && (
                    <CollapsibleBlock
                      id="heartbeat"
                      title="Heartbeat"
                      subtitle=""
                      badge={
                        <span className="flex items-center gap-1.5 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/40 dark:text-green-300">
                          <span className="h-2 w-2 animate-pulse rounded-full bg-green-500" />
                          Aktiv
                        </span>
                      }
                      expanded={memExpanded}
                      toggle={toggleMemFile}
                    >
                      <div className="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200">
                        {heartbeat.content}
                      </div>
                      {heartbeat.skills.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {heartbeat.skills.map((skill) => (
                            <span key={skill} className="rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
                              {skill}
                            </span>
                          ))}
                        </div>
                      )}
                    </CollapsibleBlock>
                  )}
                </div>
              )}
            </section>
          )}

        </div>
      </div>
    </div>
  );
}

function LlmSettingsTab() {
  const [models, setModels] = useState<{ id: string; name: string; provider: string }[]>([]);
  const [llmSettings, setLlmSettings] = useState<{
    llm_providers: Record<string, { enabled: boolean; models: string[] }> | null;
    llm_default_model: string | null;
    llm_default_local_model: string | null;
    llm_default_temperature: number | null;
  }>({ llm_providers: null, llm_default_model: null, llm_default_local_model: null, llm_default_temperature: null });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  useEffect(() => {
    Promise.all([
      api.get<{ local: any[]; cloud: any[] }>('/api/models/available'),
      api.get<typeof llmSettings>('/api/settings/llm'),
    ]).then(([modelData, settings]) => {
      setModels([...modelData.local, ...modelData.cloud]);
      setLlmSettings(settings);
    }).catch(() => {});
  }, []);

  const providers = ['ollama', 'openai', 'anthropic', 'gemini', 'perplexity'];
  const providerLabels: Record<string, string> = {
    ollama: 'Ollama (Lokal)',
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    gemini: 'Google Gemini',
    perplexity: 'Perplexity',
  };

  const getProviderModels = (provider: string) =>
    models.filter((m) => m.provider === provider);

  const isProviderEnabled = (provider: string) =>
    llmSettings.llm_providers?.[provider]?.enabled ?? false;

  const getEnabledModels = (provider: string) =>
    llmSettings.llm_providers?.[provider]?.models ?? [];

  const toggleProvider = (provider: string) => {
    const current = llmSettings.llm_providers || {};
    const providerConfig = current[provider] || { enabled: false, models: [] };
    const newProviders = {
      ...current,
      [provider]: {
        ...providerConfig,
        enabled: !providerConfig.enabled,
        models: !providerConfig.enabled
          ? getProviderModels(provider).map((m) => m.id)
          : providerConfig.models,
      },
    };
    setLlmSettings({ ...llmSettings, llm_providers: newProviders });
  };

  const toggleModel = (provider: string, modelId: string) => {
    const current = llmSettings.llm_providers || {};
    const providerConfig = current[provider] || { enabled: true, models: [] };
    const models = providerConfig.models.includes(modelId)
      ? providerConfig.models.filter((m) => m !== modelId)
      : [...providerConfig.models, modelId];
    setLlmSettings({
      ...llmSettings,
      llm_providers: {
        ...current,
        [provider]: { ...providerConfig, models },
      },
    });
  };

  const handleSave = async () => {
    setSaving(true);
    setMsg(null);
    try {
      await api.put('/api/settings/llm', llmSettings);
      setMsg({ type: 'ok', text: 'LLM-Einstellungen gespeichert' });
    } catch {
      setMsg({ type: 'err', text: 'Fehler beim Speichern' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section>
      <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">LLM-Modelle</h2>
      <p className="mb-6 text-sm text-gray-500 dark:text-gray-400">
        Aktiviere die LLM-Provider und wähle die Modelle, die dir zur Verfügung stehen sollen.
      </p>

      <div className="space-y-6">
        {providers.map((provider) => {
          const providerModels = getProviderModels(provider);
          if (providerModels.length === 0) return null;
          const enabled = isProviderEnabled(provider);
          const enabledModels = getEnabledModels(provider);

          return (
            <div
              key={provider}
              className="rounded-xl border border-gray-200 p-4 dark:border-gray-700"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-white">
                    {providerLabels[provider] || provider}
                  </h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {providerModels.length} Modell{providerModels.length !== 1 ? 'e' : ''} verfügbar
                  </p>
                </div>
                <button
                  onClick={() => toggleProvider(provider)}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                    enabled ? 'bg-indigo-600' : 'bg-gray-200 dark:bg-gray-700'
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow ring-0 transition-transform ${
                      enabled ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>

              {enabled && (
                <div className="mt-3 space-y-2">
                  {providerModels.map((model) => (
                    <label
                      key={model.id}
                      className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                      <input
                        type="checkbox"
                        checked={enabledModels.includes(model.id)}
                        onChange={() => toggleModel(provider, model.id)}
                        className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="text-gray-700 dark:text-gray-300">{model.name}</span>
                      <span className="ml-auto text-xs text-gray-400">{model.id}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Standard-Modell
          </label>
          <select
            value={llmSettings.llm_default_model || ''}
            onChange={(e) =>
              setLlmSettings({ ...llmSettings, llm_default_model: e.target.value || null })
            }
            className="mt-1 block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          >
            <option value="">Kein Standard</option>
            {models
              .filter((m) => {
                const p = m.provider;
                return llmSettings.llm_providers?.[p]?.enabled && llmSettings.llm_providers[p].models.includes(m.id);
              })
              .map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Standard Lokal-Modell
          </label>
          <p className="mb-1 text-xs text-gray-500 dark:text-gray-400">
            Wird systemweit als Default für Agent, Triage und Code-Execution verwendet.
          </p>
          <select
            value={llmSettings.llm_default_local_model || ''}
            onChange={(e) =>
              setLlmSettings({ ...llmSettings, llm_default_local_model: e.target.value || null })
            }
            className="mt-1 block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          >
            <option value="">Automatisch (erstes verfügbares)</option>
            {models
              .filter((m) => m.provider === 'ollama')
              .map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Standard-Temperatur: {llmSettings.llm_default_temperature ?? 0.7}
          </label>
          <input
            type="range"
            min="0"
            max="1.5"
            step="0.1"
            value={llmSettings.llm_default_temperature ?? 0.7}
            onChange={(e) =>
              setLlmSettings({ ...llmSettings, llm_default_temperature: parseFloat(e.target.value) })
            }
            className="mt-1 w-full"
          />
          <div className="flex justify-between text-xs text-gray-400">
            <span>Praezise (0)</span>
            <span>Kreativ (1.5)</span>
          </div>
        </div>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? 'Speichern...' : 'Speichern'}
        </button>
        {msg && (
          <span className={`text-sm ${msg.type === 'ok' ? 'text-green-600' : 'text-red-500'}`}>
            {msg.text}
          </span>
        )}
      </div>
    </section>
  );
}

function CollapsibleBlock({
  id,
  title,
  subtitle,
  badge,
  expanded,
  toggle,
  defaultOpen,
  children,
}: {
  id: string;
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  expanded: Set<string>;
  toggle: (id: string) => void;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const isOpen = defaultOpen ? !expanded.has(id) : expanded.has(id);
  const handleToggle = () => toggle(id);

  return (
    <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
      <button
        onClick={handleToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2 min-w-0">
          <ChevronIcon className={`h-4 w-4 shrink-0 text-gray-400 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
          <span className="truncate text-sm font-semibold text-gray-900 dark:text-white">{title}</span>
          {badge}
        </div>
        {subtitle && (
          <span className="ml-3 shrink-0 truncate text-xs text-gray-400 dark:text-gray-500 max-w-[40%]">
            {subtitle}
          </span>
        )}
      </button>
      {isOpen && (
        <div className="border-t border-gray-100 px-4 py-4 dark:border-gray-800">
          {children}
        </div>
      )}
    </div>
  );
}

const SIDEBAR_PALETTE = [
  { key: 'default', label: 'Standard', swatch: 'bg-white dark:bg-gray-950' },
  { key: 'slate', label: 'Slate', swatch: 'bg-slate-200 dark:bg-slate-800' },
  { key: 'zinc', label: 'Zinc', swatch: 'bg-zinc-200 dark:bg-zinc-800' },
  { key: 'stone', label: 'Stone', swatch: 'bg-stone-200 dark:bg-stone-800' },
  { key: 'indigo', label: 'Indigo', swatch: 'bg-indigo-200 dark:bg-indigo-800' },
  { key: 'blue', label: 'Blue', swatch: 'bg-blue-200 dark:bg-blue-800' },
  { key: 'sky', label: 'Sky', swatch: 'bg-sky-200 dark:bg-sky-800' },
  { key: 'emerald', label: 'Emerald', swatch: 'bg-emerald-200 dark:bg-emerald-800' },
];

function CameraIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 0 1 5.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 0 0-1.134-.175 2.31 2.31 0 0 1-1.64-1.055l-.822-1.316a2.192 2.192 0 0 0-1.736-1.039 48.774 48.774 0 0 0-5.232 0 2.192 2.192 0 0 0-1.736 1.039l-.821 1.316Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0Z" />
    </svg>
  );
}

function ChevronIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}

function ModalIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h12A2.25 2.25 0 0 1 20.25 6v12A2.25 2.25 0 0 1 18 20.25H6A2.25 2.25 0 0 1 3.75 18V6Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9M7.5 12h9M7.5 15.75h5.25" />
    </svg>
  );
}

function PanelIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h12A2.25 2.25 0 0 1 20.25 6v12A2.25 2.25 0 0 1 18 20.25H6A2.25 2.25 0 0 1 3.75 18V6Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 3.75v16.5" />
    </svg>
  );
}

function FullscreenIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9m11.25-5.25v4.5m0-4.5h-4.5m4.5 0L15 9m5.25 11.25v-4.5m0 4.5h-4.5m4.5 0L15 15m-11.25 5.25v-4.5m0 4.5h4.5m-4.5 0L9 15" />
    </svg>
  );
}

function PipedriveIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none">
      <rect width="24" height="24" rx="6" fill="#017737" />
      <path d="M12 4C8.69 4 6 6.69 6 10c0 2.22 1.21 4.16 3 5.2V18a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2v-2.8c1.79-1.04 3-2.98 3-5.2 0-3.31-2.69-6-6-6Zm0 9a3 3 0 1 1 0-6 3 3 0 0 1 0 6Z" fill="white" />
    </svg>
  );
}
