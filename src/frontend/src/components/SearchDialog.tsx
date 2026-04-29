import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { api } from '../api/client';

interface SearchDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onTaskClick: (taskId: string) => void;
  onProjectClick: (projectId: string) => void;
}

interface SearchTask {
  id: string;
  title: string;
  project_id: string;
  project_name: string;
  assignee: 'me' | 'agent';
  is_completed: boolean;
  due_date: string;
}

interface SearchProject {
  id: string;
  name: string;
  color: string;
  status: string;
}

interface SearchTag {
  id: string;
  name: string;
  color: string;
}

interface CrmHit {
  id: number | string;
  name: string;
  type: string;
  detail: string | null;
  email: string | null;
  pic_url: string | null;
}

interface TogglHit {
  id: number;
  name: string;
  type: string; // "client" | "project"
  workspace_id: number | null;
}

interface BexioHit {
  id: number;
  name: string;
  type: string; // "contact"
  email: string | null;
}

interface SearchResults {
  tasks: SearchTask[];
  projects: SearchProject[];
  tags: SearchTag[];
  crm: CrmHit[];
  toggl: TogglHit[];
  bexio: BexioHit[];
}

type ResultItem =
  | { kind: 'task'; data: SearchTask }
  | { kind: 'project'; data: SearchProject }
  | { kind: 'tag'; data: SearchTag }
  | { kind: 'crm'; data: CrmHit }
  | { kind: 'toggl'; data: TogglHit }
  | { kind: 'bexio'; data: BexioHit };

export function SearchDialog({
  isOpen,
  onClose,
  onTaskClick,
  onProjectClick,
}: SearchDialogProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const flatItems = useMemo<ResultItem[]>(() => {
    if (!results) return [];
    const items: ResultItem[] = [];
    for (const t of results.tasks) items.push({ kind: 'task', data: t });
    for (const p of results.projects) items.push({ kind: 'project', data: p });
    for (const tag of results.tags) items.push({ kind: 'tag', data: tag });
    for (const c of (results.crm || [])) items.push({ kind: 'crm', data: c });
    for (const t of (results.toggl || [])) items.push({ kind: 'toggl', data: t });
    for (const b of (results.bexio || [])) items.push({ kind: 'bexio', data: b });
    return items;
  }, [results]);

  const grouped = useMemo(() => {
    if (!results) return null;
    const sections: { label: string; items: ResultItem[] }[] = [];
    if (results.tasks.length > 0)
      sections.push({ label: 'Tasks', items: results.tasks.map((d) => ({ kind: 'task' as const, data: d })) });
    if (results.projects.length > 0)
      sections.push({ label: 'Projekte', items: results.projects.map((d) => ({ kind: 'project' as const, data: d })) });
    if (results.tags.length > 0)
      sections.push({ label: 'Tags', items: results.tags.map((d) => ({ kind: 'tag' as const, data: d })) });
    if ((results.crm || []).length > 0)
      sections.push({ label: 'CRM (Pipedrive)', items: results.crm.map((d) => ({ kind: 'crm' as const, data: d })) });
    if ((results.toggl || []).length > 0)
      sections.push({ label: 'Toggl Track', items: results.toggl.map((d) => ({ kind: 'toggl' as const, data: d })) });
    if ((results.bexio || []).length > 0)
      sections.push({ label: 'Bexio', items: results.bexio.map((d) => ({ kind: 'bexio' as const, data: d })) });
    return sections;
  }, [results]);

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setResults(null);
      setActiveIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [isOpen]);

  useEffect(() => {
    if (!query.trim()) {
      setResults(null);
      setActiveIndex(0);
      return;
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => {
      setLoading(true);
      api
        .get<SearchResults>(`/api/search?q=${encodeURIComponent(query.trim())}`)
        .then((data) => {
          if (!controller.signal.aborted) {
            setResults(data);
            setActiveIndex(0);
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) setResults(null);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 300);

    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [query]);

  const activateItem = useCallback(
    (item: ResultItem) => {
      if (item.kind === 'task') {
        onTaskClick(item.data.id);
        onClose();
      } else if (item.kind === 'project') {
        onProjectClick(item.data.id);
        onClose();
      } else if (item.kind === 'crm') {
        const crm = item.data;
        const pathMap: Record<string, string> = { person: 'person', deal: 'deal', organization: 'organization' };
        const path = pathMap[crm.type] || crm.type;
        window.open(`https://innosmith.pipedrive.com/${path}/${crm.id}`, '_blank');
        onClose();
      } else if (item.kind === 'toggl') {
        const t = item.data;
        const wsId = t.workspace_id || 0;
        if (t.type === 'client') {
          window.open(`https://track.toggl.com/${wsId}/clients`, '_blank');
        } else {
          window.open(`https://track.toggl.com/${wsId}/projects/${t.id}/team`, '_blank');
        }
        onClose();
      } else if (item.kind === 'bexio') {
        const b = item.data;
        if (b.type === 'contact') {
          window.open(`https://office.bexio.com/index.cfm/contact/show/id/${b.id}`, '_blank');
        }
        onClose();
      }
    },
    [onTaskClick, onProjectClick, onClose],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((prev) => (prev + 1) % Math.max(flatItems.length, 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((prev) => (prev - 1 + flatItems.length) % Math.max(flatItems.length, 1));
        return;
      }
      if (e.key === 'Enter' && flatItems[activeIndex]) {
        e.preventDefault();
        activateItem(flatItems[activeIndex]);
      }
    },
    [flatItems, activeIndex, activateItem, onClose],
  );

  useEffect(() => {
    const el = listRef.current?.querySelector('[data-active="true"]');
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  if (!isOpen) return null;

  let runningIndex = -1;

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === backdropRef.current) onClose();
      }}
    >
      <div
        className="mt-[12vh] flex w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900"
        onKeyDown={handleKeyDown}
      >
        {/* Suchfeld */}
        <div className="flex items-center gap-3 border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <SearchIcon className="h-5 w-5 shrink-0 text-gray-400 dark:text-gray-500" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Suchen…"
            className="flex-1 bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-400 dark:text-white dark:placeholder:text-gray-500"
          />
          {loading && (
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
          )}
          <kbd className="hidden rounded-md border border-gray-200 px-1.5 py-0.5 text-[10px] font-medium text-gray-400 sm:inline-block dark:border-gray-600 dark:text-gray-500">
            ESC
          </kbd>
        </div>

        {/* Ergebnisse */}
        <div ref={listRef} className="max-h-[60vh] overflow-y-auto">
          {!query.trim() && (
            <div className="flex flex-col items-center gap-2 px-4 py-10 text-center text-sm text-gray-400 dark:text-gray-500">
              <span className="flex items-center gap-1.5">
                <kbd className="rounded-md border border-gray-200 px-1.5 py-0.5 text-[10px] font-medium dark:border-gray-600">
                  /
                </kbd>
                zum Suchen
              </span>
            </div>
          )}

          {query.trim() && !loading && grouped && grouped.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-gray-400 dark:text-gray-500">
              Keine Ergebnisse für &laquo;{query}&raquo;
            </div>
          )}

          {grouped &&
            grouped.map((section) => (
              <div key={section.label}>
                <div className="sticky top-0 z-10 bg-gray-50/90 px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500 backdrop-blur-sm dark:bg-gray-800/90 dark:text-gray-400">
                  {section.label}
                </div>
                {section.items.map((item) => {
                  runningIndex++;
                  const idx = runningIndex;
                  const isActive = idx === activeIndex;

                  if (item.kind === 'task') {
                    const task = item.data;
                    return (
                      <button
                        key={task.id}
                        data-active={isActive}
                        onClick={() => activateItem(item)}
                        onMouseEnter={() => setActiveIndex(idx)}
                        className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                          isActive
                            ? 'bg-indigo-50 dark:bg-indigo-950/40'
                            : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
                        }`}
                      >
                        <span
                          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 ${
                            task.is_completed
                              ? 'border-green-400 bg-green-400 text-white'
                              : 'border-gray-300 dark:border-gray-600'
                          }`}
                        >
                          {task.is_completed && <CheckIcon className="h-3 w-3" />}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p
                            className={`truncate text-sm font-medium ${
                              task.is_completed
                                ? 'text-gray-400 line-through dark:text-gray-600'
                                : 'text-gray-900 dark:text-white'
                            }`}
                          >
                            {task.title}
                          </p>
                          <p className="truncate text-xs text-gray-400 dark:text-gray-500">
                            {task.project_name}
                            {task.due_date && ` · ${formatDate(task.due_date)}`}
                          </p>
                        </div>
                        {task.assignee === 'agent' && (
                          <AgentBadge />
                        )}
                      </button>
                    );
                  }

                  if (item.kind === 'project') {
                    const project = item.data;
                    return (
                      <button
                        key={project.id}
                        data-active={isActive}
                        onClick={() => activateItem(item)}
                        onMouseEnter={() => setActiveIndex(idx)}
                        className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                          isActive
                            ? 'bg-indigo-50 dark:bg-indigo-950/40'
                            : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
                        }`}
                      >
                        <span
                          className="h-3 w-3 shrink-0 rounded-full"
                          style={{ backgroundColor: project.color }}
                        />
                        <span className="truncate text-sm font-medium text-gray-900 dark:text-white">
                          {project.name}
                        </span>
                        <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">
                          {project.status === 'active' ? 'Aktiv' : project.status}
                        </span>
                      </button>
                    );
                  }

                  // tag
                  if (item.kind === 'tag') {
                    const tag = item.data;
                    return (
                      <div
                        key={tag.id}
                        data-active={isActive}
                        onMouseEnter={() => setActiveIndex(idx)}
                        className={`flex items-center gap-3 px-4 py-2.5 transition-colors ${
                          isActive
                            ? 'bg-indigo-50 dark:bg-indigo-950/40'
                            : ''
                        }`}
                      >
                        <span
                          className="inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium"
                          style={{
                            backgroundColor: tag.color + '20',
                            color: tag.color,
                          }}
                        >
                          {tag.name}
                        </span>
                      </div>
                    );
                  }

                  // crm
                  if (item.kind === 'crm') {
                    const crm = item.data;
                    const typeLabels: Record<string, string> = { person: 'Kontakt', deal: 'Deal', organization: 'Organisation' };
                    const typeColors: Record<string, string> = {
                      person: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
                      deal: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
                      organization: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
                    };
                    return (
                      <button
                        key={`${crm.type}-${crm.id}`}
                        data-active={isActive}
                        onClick={() => activateItem(item)}
                        onMouseEnter={() => setActiveIndex(idx)}
                        className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                          isActive
                            ? 'bg-indigo-50 dark:bg-indigo-950/40'
                            : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
                        }`}
                      >
                        {crm.pic_url ? (
                          <img
                            src={crm.pic_url}
                            alt=""
                            className="h-9 w-9 shrink-0 rounded-full object-cover"
                          />
                        ) : (
                          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300">
                            <CrmSearchIcon className="h-4 w-4" />
                          </span>
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-gray-900 dark:text-white">
                            {crm.name}
                          </p>
                          <p className="truncate text-xs text-gray-400 dark:text-gray-500">
                            {crm.detail || crm.email || ''}
                          </p>
                        </div>
                        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${typeColors[crm.type] || 'bg-gray-100 text-gray-600'}`}>
                          {typeLabels[crm.type] || crm.type}
                        </span>
                        <ExternalLinkIcon className="h-3.5 w-3.5 shrink-0 text-gray-300 dark:text-gray-600" />
                      </button>
                    );
                  }

                  // toggl
                  if (item.kind === 'toggl') {
                    const t = item.data;
                    const togglTypeLabels: Record<string, string> = { client: 'Kunde', project: 'Projekt' };
                    const togglTypeColors: Record<string, string> = {
                      client: 'bg-pink-100 text-pink-700 dark:bg-pink-900/40 dark:text-pink-300',
                      project: 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300',
                    };
                    return (
                      <button
                        key={`toggl-${t.type}-${t.id}`}
                        data-active={isActive}
                        onClick={() => activateItem(item)}
                        onMouseEnter={() => setActiveIndex(idx)}
                        className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                          isActive
                            ? 'bg-indigo-50 dark:bg-indigo-950/40'
                            : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
                        }`}
                      >
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-pink-100 text-pink-700 dark:bg-pink-900/40 dark:text-pink-300">
                          <TogglIcon className="h-4 w-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-gray-900 dark:text-white">
                            {t.name}
                          </p>
                        </div>
                        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${togglTypeColors[t.type] || 'bg-gray-100 text-gray-600'}`}>
                          {togglTypeLabels[t.type] || t.type}
                        </span>
                        <ExternalLinkIcon className="h-3.5 w-3.5 shrink-0 text-gray-300 dark:text-gray-600" />
                      </button>
                    );
                  }

                  // bexio
                  if (item.kind === 'bexio') {
                    const b = item.data;
                    return (
                      <button
                        key={`bexio-${b.type}-${b.id}`}
                        data-active={isActive}
                        onClick={() => activateItem(item)}
                        onMouseEnter={() => setActiveIndex(idx)}
                        className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                          isActive
                            ? 'bg-indigo-50 dark:bg-indigo-950/40'
                            : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
                        }`}
                      >
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300">
                          <BexioIcon className="h-4 w-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-gray-900 dark:text-white">
                            {b.name}
                          </p>
                          {b.email && (
                            <p className="truncate text-xs text-gray-400 dark:text-gray-500">
                              {b.email}
                            </p>
                          )}
                        </div>
                        <span className="shrink-0 rounded-full bg-teal-100 px-2 py-0.5 text-[10px] font-medium text-teal-700 dark:bg-teal-900/40 dark:text-teal-300">
                          Kontakt
                        </span>
                        <ExternalLinkIcon className="h-3.5 w-3.5 shrink-0 text-gray-300 dark:text-gray-600" />
                      </button>
                    );
                  }

                  return null;
                })}
              </div>
            ))}
        </div>

        {/* Footer-Hinweise */}
        {flatItems.length > 0 && (
          <div className="flex items-center gap-4 border-t border-gray-200 px-4 py-2 text-[11px] text-gray-400 dark:border-gray-700 dark:text-gray-500">
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-gray-200 px-1 py-0.5 text-[10px] dark:border-gray-600">↑↓</kbd>
              Navigieren
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-gray-200 px-1 py-0.5 text-[10px] dark:border-gray-600">↵</kbd>
              Öffnen
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-gray-200 px-1 py-0.5 text-[10px] dark:border-gray-600">ESC</kbd>
              Schliessen
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = date.getTime() - now.getTime();
  const days = Math.ceil(diff / (1000 * 60 * 60 * 24));

  if (days === 0) return 'Heute';
  if (days === 1) return 'Morgen';
  if (days === -1) return 'Gestern';

  return date.toLocaleDateString('de-DE', { day: 'numeric', month: 'short' });
}

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={3} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
    </svg>
  );
}

function AgentBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-medium text-violet-600 dark:bg-violet-950 dark:text-violet-300">
      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
      </svg>
      Agent
    </span>
  );
}

function CrmSearchIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
    </svg>
  );
}

function ExternalLinkIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
    </svg>
  );
}

function TogglIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
    </svg>
  );
}

function BexioIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18.75a60.07 60.07 0 0 1 15.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 0 1 3 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 0 0-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 0 1-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 0 0 3 15h-.75M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm3 0h.008v.008H18V10.5Zm-12 0h.008v.008H6V10.5Z" />
    </svg>
  );
}
