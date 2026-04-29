import { useState, useEffect, useCallback } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { useSSE } from '../hooks/useSSE';
import { ThemeToggle } from './ThemeToggle';
import { ProjectIcon } from './ProjectIcon';
import type { AgentJob, Project } from '../types';

const SIDEBAR_COLORS: Record<string, { light: string; dark: string }> = {
  default: { light: 'bg-white', dark: 'dark:bg-gray-950' },
  slate: { light: 'bg-slate-50', dark: 'dark:bg-slate-950' },
  zinc: { light: 'bg-zinc-50', dark: 'dark:bg-zinc-950' },
  stone: { light: 'bg-stone-50', dark: 'dark:bg-stone-950' },
  indigo: { light: 'bg-indigo-50', dark: 'dark:bg-indigo-950' },
  blue: { light: 'bg-blue-50', dark: 'dark:bg-blue-950' },
  sky: { light: 'bg-sky-50', dark: 'dark:bg-sky-950' },
  emerald: { light: 'bg-emerald-50', dark: 'dark:bg-emerald-950' },
};

interface SidebarProps {
  isOpen: boolean;
  collapsed: boolean;
  onClose: () => void;
  onToggleCollapse: () => void;
  onSearchOpen: () => void;
  refreshKey: number;
  appLogoUrl?: string | null;
  sidebarColor?: string | null;
}

export function Sidebar({
  isOpen,
  collapsed,
  onClose,
  onToggleCollapse,
  onSearchOpen,
  refreshKey,
  appLogoUrl,
  sidebarColor,
}: SidebarProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeJobCount, setActiveJobCount] = useState(0);
  const [unreadMailCount, setUnreadMailCount] = useState(0);
  const [pendingDecisions, setPendingDecisions] = useState(0);
  const [focusTaskCount, setFocusTaskCount] = useState(0);
  const { logout } = useAuth();
  const navigate = useNavigate();

  const refreshBadges = useCallback(() => {
    api
      .get<AgentJob[]>('/api/agent-jobs')
      .then((jobs) => {
        const active = jobs.filter((j) => ['queued', 'running', 'awaiting_approval'].includes(j.status));
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
        const focusCol = data.columns?.find(c => c.position === 0) || data.columns?.[0];
        setFocusTaskCount(focusCol?.tasks?.length ?? 0);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    api.get<Project[]>('/api/projects').then(setProjects).catch(() => {});
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
      api.get<Project[]>('/api/projects').then(setProjects).catch(() => {});
      api
        .get<{ columns: { position: number; tasks: unknown[] }[] }>('/api/pipeline')
        .then((data) => {
          const focusCol = data.columns?.find(c => c.position === 0) || data.columns?.[0];
          setFocusTaskCount(focusCol?.tasks?.length ?? 0);
        })
        .catch(() => {});
    }
  });

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const bgClasses = SIDEBAR_COLORS[sidebarColor || 'default'] || SIDEBAR_COLORS.default;

  const linkClasses = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      isActive
        ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
        : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800'
    }`;

  const collapsedLinkClasses = ({ isActive }: { isActive: boolean }) =>
    `flex items-center justify-center rounded-lg p-2 transition-colors ${
      isActive
        ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
        : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800'
    }`;

  const w = collapsed ? 'w-[56px]' : 'w-64';

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/30 backdrop-blur-sm lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed top-0 left-0 z-40 flex h-full ${w} flex-col border-r border-gray-200 ${bgClasses.light} ${bgClasses.dark} transition-all duration-200 dark:border-gray-800 lg:static lg:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Logo + Collapse Toggle */}
        <div className="flex items-center gap-2 border-b border-gray-200 px-3 py-3 dark:border-gray-800">
          {collapsed ? (
            <button
              onClick={onToggleCollapse}
              className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200 lg:flex"
              title="Sidebar ausklappen"
            >
              <MenuIcon className="h-5 w-5" />
            </button>
          ) : (
            <>
              {appLogoUrl ? (
                <img src={appLogoUrl} alt="" className="h-8 w-8 shrink-0 rounded-lg object-cover" />
              ) : (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
                  T
                </div>
              )}
              <span className="flex-1 text-lg font-semibold text-gray-900 dark:text-white">
                TaskPilot
              </span>
              <button
                onClick={onToggleCollapse}
                className="hidden shrink-0 rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300 lg:flex"
                title="Sidebar einklappen"
              >
                <CollapseIcon className="h-4 w-4" />
              </button>
            </>
          )}
        </div>

        {/* Suche */}
        {!collapsed ? (
          <div className="px-3 pt-3">
            <button
              onClick={onSearchOpen}
              className="flex w-full items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-500 transition-colors hover:border-gray-300 hover:text-gray-700 dark:border-gray-700 dark:text-gray-400 dark:hover:border-gray-600 dark:hover:text-gray-300"
            >
              <SearchIcon className="h-4 w-4 shrink-0" />
              <span className="flex-1 text-left">Suchen...</span>
              <kbd className="rounded border border-gray-300 px-1.5 py-0.5 text-xs text-gray-400 dark:border-gray-600">
                /
              </kbd>
            </button>
          </div>
        ) : (
          <div className="flex justify-center pt-3">
            <button
              onClick={onSearchOpen}
              className="rounded-lg p-2 text-gray-500 transition-colors hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
              title="Suchen (/)"
            >
              <SearchIcon className="h-5 w-5" />
            </button>
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 space-y-1 overflow-y-auto px-2 py-3">
          {collapsed ? (
            <>
              <NavLink to="/cockpit" className={collapsedLinkClasses} onClick={onClose} title="Cockpit">
                <span className="relative">
                  <CockpitIcon className="h-5 w-5" />
                  {pendingDecisions > 0 && (
                    <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-rose-500 text-[9px] font-bold text-white">
                      {pendingDecisions}
                    </span>
                  )}
                </span>
              </NavLink>
              <NavLink to="/pipeline" className={collapsedLinkClasses} onClick={onClose} title="Agenda">
                <span className="relative">
                  <AgendaIcon className="h-5 w-5" />
                  {focusTaskCount > 0 && (
                    <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-amber-500 text-[9px] font-bold text-white">
                      {focusTaskCount > 9 ? '9+' : focusTaskCount}
                    </span>
                  )}
                </span>
              </NavLink>
              <NavLink to="/agenten" className={collapsedLinkClasses} onClick={onClose} title="Agenten">
                <span className="relative">
                  <AgentIcon className="h-5 w-5" />
                  {activeJobCount > 0 && (
                    <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-indigo-500 text-[9px] font-bold text-white">
                      {activeJobCount}
                    </span>
                  )}
                </span>
              </NavLink>

              <div className="my-2 border-t border-gray-200 dark:border-gray-800" />

              {projects.map((project) => (
                <NavLink
                  key={project.id}
                  to={`/projects/${project.id}`}
                  className={collapsedLinkClasses}
                  onClick={onClose}
                  title={project.name}
                >
                  <ProjectIcon
                    iconUrl={project.icon_url}
                    iconEmoji={project.icon_emoji}
                    color={project.color}
                    size={20}
                  />
                </NavLink>
              ))}

              <div className="my-2 border-t border-gray-200 dark:border-gray-800" />

              <NavLink to="/inbox" className={collapsedLinkClasses} onClick={onClose} title="Posteingang">
                <span className="relative">
                  <MailIcon className="h-5 w-5" />
                  {unreadMailCount > 0 && (
                    <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-blue-500 text-[9px] font-bold text-white">
                      {unreadMailCount > 9 ? '9+' : unreadMailCount}
                    </span>
                  )}
                </span>
              </NavLink>
              <NavLink to="/signale" className={collapsedLinkClasses} onClick={onClose} title="Signale">
                <SignaleIcon className="h-5 w-5" />
              </NavLink>
            </>
          ) : (
            <>
              <NavLink to="/cockpit" className={linkClasses} onClick={onClose}>
                <CockpitIcon className="h-5 w-5" />
                <span className="flex-1">Cockpit</span>
                {pendingDecisions > 0 && (
                  <span className="flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
                    {pendingDecisions}
                  </span>
                )}
              </NavLink>

              <NavLink to="/pipeline" className={linkClasses} onClick={onClose}>
                <AgendaIcon className="h-5 w-5" />
                <span className="flex-1">Agenda</span>
                {focusTaskCount > 0 && (
                  <span className="flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                    {focusTaskCount}
                  </span>
                )}
              </NavLink>

              <NavLink to="/agenten" className={linkClasses} onClick={onClose}>
                <AgentIcon className="h-5 w-5" />
                <span className="flex-1">Agenten</span>
                {activeJobCount > 0 && (
                  <span className="flex items-center gap-1 rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500" />
                    {activeJobCount}
                  </span>
                )}
              </NavLink>

              <div className="mt-6 mb-2 flex items-center justify-between px-3">
                <span className="text-xs font-semibold tracking-wider text-gray-400 uppercase dark:text-gray-500">
                  Projekte
                </span>
                <NavLink
                  to="/projects"
                  className="rounded p-0.5 text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
                  onClick={onClose}
                  title="Alle Projekte"
                >
                  <GridIcon className="h-3.5 w-3.5" />
                </NavLink>
              </div>

              {projects.map((project) => (
                <NavLink
                  key={project.id}
                  to={`/projects/${project.id}`}
                  className={linkClasses}
                  onClick={onClose}
                >
                  <ProjectIcon
                    iconUrl={project.icon_url}
                    iconEmoji={project.icon_emoji}
                    color={project.color}
                    size={16}
                  />
                  {project.name}
                </NavLink>
              ))}

              <div className="mt-4 mb-2 border-t border-gray-200 pt-2 dark:border-gray-800" />

              <NavLink to="/inbox" className={linkClasses} onClick={onClose}>
                <MailIcon className="h-5 w-5" />
                <span className="flex-1">Posteingang</span>
                {unreadMailCount > 0 && (
                  <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                    {unreadMailCount}
                  </span>
                )}
              </NavLink>

              <NavLink to="/signale" className={linkClasses} onClick={onClose}>
                <SignaleIcon className="h-5 w-5" />
                <span className="flex-1">Signale</span>
              </NavLink>
            </>
          )}
        </nav>

        {/* Footer */}
        <div className="border-t border-gray-200 px-2 py-2 dark:border-gray-800">
          {collapsed ? (
            <div className="flex flex-col items-center gap-2">
              <NavLink to="/settings" className={collapsedLinkClasses} onClick={onClose} title="Einstellungen">
                <SettingsIcon className="h-5 w-5" />
              </NavLink>
              <ThemeCycleButton />
              <LogoutButton onLogout={handleLogout} collapsed />
            </div>
          ) : (
            <>
              <NavLink to="/settings" className={linkClasses} onClick={onClose}>
                <SettingsIcon className="h-5 w-5" />
                Einstellungen
              </NavLink>
              <div className="mt-2 flex items-center justify-between px-1">
                <ThemeToggle />
                <LogoutButton onLogout={handleLogout} />
              </div>
            </>
          )}
        </div>
      </aside>
    </>
  );
}

/* ── ThemeCycleButton ── */

function ThemeCycleButton() {
  const { mode, setMode } = useTheme();
  const next = mode === 'light' ? 'dark' : mode === 'dark' ? 'system' : 'light';
  const labels: Record<string, string> = { light: 'Dunkel', dark: 'System', system: 'Hell' };
  return (
    <button
      onClick={() => setMode(next)}
      className="rounded-lg p-2 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
      title={`Wechsel zu: ${labels[mode]}`}
    >
      {mode === 'light' && <SunSmallIcon className="h-5 w-5" />}
      {mode === 'dark' && <MoonSmallIcon className="h-5 w-5" />}
      {mode === 'system' && <MonitorSmallIcon className="h-5 w-5" />}
    </button>
  );
}

/* ── LogoutButton ── */

function LogoutButton({ onLogout, collapsed = false }: { onLogout: () => void; collapsed?: boolean }) {
  const [confirm, setConfirm] = useState(false);
  useEffect(() => {
    if (!confirm) return;
    const t = setTimeout(() => setConfirm(false), 3000);
    return () => clearTimeout(t);
  }, [confirm]);

  if (collapsed) {
    return (
      <button
        onClick={() => { if (confirm) { onLogout(); } else { setConfirm(true); } }}
        className={`rounded-lg p-2 transition-colors ${
          confirm
            ? 'bg-red-100 text-red-600 dark:bg-red-950 dark:text-red-400'
            : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200'
        }`}
        title={confirm ? 'Nochmals klicken zum Abmelden' : 'Abmelden'}
      >
        <LogoutIcon className="h-5 w-5" />
      </button>
    );
  }

  return (
    <button
      onClick={() => { if (confirm) { onLogout(); } else { setConfirm(true); } }}
      className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
        confirm
          ? 'bg-red-100 text-red-600 dark:bg-red-950 dark:text-red-400'
          : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200'
      }`}
      title={confirm ? 'Nochmals klicken zum Abmelden' : 'Abmelden'}
    >
      {confirm ? 'Abmelden?' : <LogoutIcon className="h-5 w-5" />}
    </button>
  );
}

/* ── Icons ── */

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
    </svg>
  );
}

function CockpitIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5m.75-9 3-3 2.148 2.148A12.061 12.061 0 0 1 16.5 7.605" />
    </svg>
  );
}

function AgendaIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25A2.25 2.25 0 0 1 13.5 18v-2.25Z" />
    </svg>
  );
}

function AgentIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
    </svg>
  );
}

function MailIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
    </svg>
  );
}

function GridIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25A2.25 2.25 0 0 1 13.5 18v-2.25Z" />
    </svg>
  );
}

function LogoutIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
    </svg>
  );
}

function SettingsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.431.992a7.723 7.723 0 0 1 0 .255c-.007.378.138.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
    </svg>
  );
}

function ChevronLeftIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
    </svg>
  );
}

function MenuIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
    </svg>
  );
}

function CollapseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M12 17.25h8.25" />
    </svg>
  );
}

function ChevronRightIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
    </svg>
  );
}

function SunSmallIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
    </svg>
  );
}

function MoonSmallIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" />
    </svg>
  );
}

function MonitorSmallIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 17.25v1.007a3 3 0 0 1-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0 1 15 18.257V17.25m6-12V15a2.25 2.25 0 0 1-2.25 2.25H5.25A2.25 2.25 0 0 1 3 15V5.25A2.25 2.25 0 0 1 5.25 3h13.5A2.25 2.25 0 0 1 21 5.25Z" />
    </svg>
  );
}

function SignaleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.348 14.652a3.75 3.75 0 0 1 0-5.304m5.304 0a3.75 3.75 0 0 1 0 5.304m-7.425 2.121a6.75 6.75 0 0 1 0-9.546m9.546 0a6.75 6.75 0 0 1 0 9.546M5.106 18.894c-3.808-3.807-3.808-9.98 0-13.788m13.788 0c3.808 3.807 3.808 9.98 0 13.788M12 12h.008v.008H12V12Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" />
    </svg>
  );
}
