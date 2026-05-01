import { useState, useEffect, useCallback } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { Sidebar } from '../components/Sidebar';
import { MobileHeader } from '../components/MobileHeader';
import { BottomTabBar } from '../components/BottomTabBar';
import { SearchDialog } from '../components/SearchDialog';
import { TaskDetailDialog } from '../components/TaskDetailDialog';
import { useBadgeData, BadgeProvider } from '../hooks/useBadges';
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
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [appSettings, setAppSettings] = useState<AppSettings>({});
  const navigate = useNavigate();

  const badges = useBadgeData(sidebarRefreshKey);

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
    (taskId: string) => {
      setSearchOpen(false);
      setSelectedTaskId(taskId);
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

  const openSidebar = useCallback(() => setSidebarOpen(true), []);
  const openSearch = useCallback(() => setSearchOpen(true), []);

  return (
    <BadgeProvider value={badges}>
      <div className="flex h-screen overflow-hidden bg-gradient-to-br from-slate-50 via-indigo-50/30 to-sky-50/40 dark:from-gray-950 dark:via-indigo-950/20 dark:to-gray-950">
        <Sidebar
          isOpen={sidebarOpen}
          collapsed={sidebarCollapsed}
          onClose={() => setSidebarOpen(false)}
          onToggleCollapse={toggleCollapse}
          onSearchOpen={openSearch}
          refreshKey={sidebarRefreshKey}
          appLogoUrl={appSettings.app_logo_url}
          sidebarColor={appSettings.sidebar_color}
        />

        <div className="flex flex-1 flex-col overflow-hidden">
          <MobileHeader onMenuOpen={openSidebar} onSearchOpen={openSearch} />

          <main className="flex-1 overflow-hidden lg:pt-0 lg:pb-0" style={{ paddingTop: 'calc(3rem + env(safe-area-inset-top, 0px))', paddingBottom: 'calc(3.5rem + env(safe-area-inset-bottom, 0px))' }}>
            <Outlet context={{ refreshSidebar, refreshAppSettings }} />
          </main>

          <BottomTabBar onMoreOpen={openSidebar} />
        </div>

        <SearchDialog
          isOpen={searchOpen}
          onClose={() => setSearchOpen(false)}
          onTaskClick={handleTaskClick}
          onProjectClick={handleProjectClick}
        />

        {selectedTaskId && (
          <TaskDetailDialog
            taskId={selectedTaskId}
            onClose={() => setSelectedTaskId(null)}
            onUpdated={() => setSelectedTaskId(null)}
          />
        )}
      </div>
    </BadgeProvider>
  );
}
