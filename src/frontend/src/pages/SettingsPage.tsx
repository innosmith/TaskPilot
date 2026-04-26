import { useState, useEffect, useCallback, useRef } from 'react';
import { useOutletContext } from 'react-router-dom';
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
}

interface TriageTestResult {
  id: string;
  message_id: string;
  subject: string | null;
  from_address: string | null;
  triage_class: string | null;
}

export function SettingsPage() {
  const [tab, setTab] = useState<'profile' | 'display' | 'triage' | 'admin'>('profile');
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [settings, setSettings] = useState<UserSettingsData>({});
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(true);
  const { refreshAppSettings } = useOutletContext<{ refreshAppSettings: () => void }>();

  const [displayName, setDisplayName] = useState('');
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

  const fetchData = useCallback(async () => {
    try {
      const [p, s] = await Promise.all([
        api.get<UserProfile>('/api/auth/me'),
        api.get<UserSettingsData>('/api/settings'),
      ]);
      setProfile(p);
      setSettings(s);
      setDisplayName(p.display_name);
      if (p.role === 'owner') {
        const [u, ts] = await Promise.all([
          api.get<ManagedUser[]>('/api/auth/users'),
          api.get<TriageSettingsData>('/api/settings/triage'),
        ]);
        setUsers(u);
        if (ts.triage_prompt) setTriagePrompt(ts.triage_prompt);
        if (ts.triage_interval_seconds) setTriageInterval(Math.round(ts.triage_interval_seconds / 60));
        if (ts.triage_enabled !== null && ts.triage_enabled !== undefined) setTriageEnabled(ts.triage_enabled);
      }
    } catch { /* */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const saveProfile = async () => {
    if (!displayName.trim()) return;
    try {
      const updated = await api.patch<UserProfile>('/api/auth/me', { display_name: displayName.trim() });
      setProfile(updated);
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

  const updateSetting = async (key: string, value: string | null) => {
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

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-3 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  const isOwner = profile?.role === 'owner';
  const tabs = [
    { id: 'profile' as const, label: 'Profil' },
    { id: 'display' as const, label: 'Darstellung' },
    ...(isOwner ? [{ id: 'triage' as const, label: 'E-Mail-Triage' }] : []),
    ...(isOwner ? [{ id: 'admin' as const, label: 'Admin' }] : []),
  ];

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-gray-200 px-6 py-4 dark:border-gray-800">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Einstellungen</h1>
      </div>

      <div className="border-b border-gray-200 px-6 dark:border-gray-800">
        <div className="flex gap-4">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`border-b-2 px-1 py-3 text-sm font-medium transition-colors ${
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

      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-2xl space-y-8">

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
                        disabled={!displayName.trim() || displayName === profile.display_name}
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
                      value={profile.email}
                      disabled
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400"
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

          {tab === 'display' && (
            <section>
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Darstellung</h2>
              <div className="space-y-6">
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
                  <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">App-Logo</label>
                  <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                    Wird oben links in der Sidebar angezeigt (z.B. Firmenlogo).
                  </p>
                  <div className="flex items-center gap-3">
                    <div
                      className="group relative flex h-12 w-12 cursor-pointer items-center justify-center overflow-hidden rounded-lg border border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800"
                      onClick={() => logoInput.current?.click()}
                    >
                      {settings.app_logo_url ? (
                        <img src={settings.app_logo_url} alt="" className="h-full w-full object-cover" />
                      ) : (
                        <span className="text-xl font-bold text-gray-400">T</span>
                      )}
                      <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
                        <CameraIcon className="h-4 w-4 text-white" />
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

                <div>
                  <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">Sidebar-Farbe</label>
                  <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                    Wähle eine Hintergrundfarbe für die Sidebar (passt sich an Light/Dark an).
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
                            r.triage_class === 'quick_response' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' :
                            r.triage_class === 'board_task' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300' :
                            r.triage_class === 'bedenkzeit' ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' :
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

          {tab === 'admin' && isOwner && (
            <section>
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Benutzerverwaltung</h2>

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
                    <option value="member">Member</option>
                    <option value="viewer">Viewer</option>
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
                            {u.role}
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
        </div>
      </div>
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
