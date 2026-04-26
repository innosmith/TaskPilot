import { useState, useEffect, useCallback } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { Sidebar } from '../components/Sidebar';
import { SearchDialog } from '../components/SearchDialog';
import { api } from '../api/client';

interface AppSettings {
  sidebar_collapsed?: boolean;
  app_logo_url?: string | null;
  sidebar_color?: string | null;
}

export function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [appSettings, setAppSettings] = useState<AppSettings>({});
  const navigate = useNavigate();

  useEffect(() => {
    api.get<AppSettings>('/api/settings').then((s) => {
      if (s.sidebar_collapsed) setSidebarCollapsed(true);
      setAppSettings(s);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === '/' && !searchOpen && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [searchOpen]);

  const toggleCollapse = useCallback(() => {
    const next = !sidebarCollapsed;
    setSidebarCollapsed(next);
    api.patch('/api/settings', { sidebar_collapsed: next }).catch(() => {});
  }, [sidebarCollapsed]);

  const handleTaskClick = useCallback(
    (_taskId: string) => {
      setSearchOpen(false);
    },
    [],
  );

  const handleProjectClick = useCallback(
    (projectId: string) => {
      setSearchOpen(false);
      navigate(`/projects/${projectId}`);
    },
    [navigate],
  );

  const refreshSidebar = useCallback(() => {
    setSidebarRefreshKey((k) => k + 1);
  }, []);

  const refreshAppSettings = useCallback(() => {
    api.get<AppSettings>('/api/settings').then((s) => {
      setAppSettings(s);
    }).catch(() => {});
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 dark:bg-gray-950">
      <Sidebar
        isOpen={sidebarOpen}
        collapsed={sidebarCollapsed}
        onClose={() => setSidebarOpen(false)}
        onToggleCollapse={toggleCollapse}
        onSearchOpen={() => setSearchOpen(true)}
        refreshKey={sidebarRefreshKey}
        appLogoUrl={appSettings.app_logo_url}
        sidebarColor={appSettings.sidebar_color}
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile-only floating menu button */}
        <button
          onClick={() => setSidebarOpen(true)}
          className="fixed left-3 top-3 z-20 rounded-lg bg-white/80 p-1.5 text-gray-500 shadow-md backdrop-blur-sm hover:bg-white dark:bg-gray-900/80 dark:text-gray-400 dark:hover:bg-gray-900 lg:hidden"
        >
          <MenuIcon className="h-5 w-5" />
        </button>

        <main className="flex-1 overflow-hidden">
          <Outlet context={{ refreshSidebar, refreshAppSettings }} />
        </main>
      </div>

      <SearchDialog
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        onTaskClick={handleTaskClick}
        onProjectClick={handleProjectClick}
      />
    </div>
  );
}

function MenuIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
    </svg>
  );
}
