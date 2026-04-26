import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';

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

const REFRESH_INTERVAL = 30_000;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function MemoryPage() {
  const [heartbeat, setHeartbeat] = useState<HeartbeatStatus | null>(null);
  const [files, setFiles] = useState<MemoryFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchData = useCallback(async () => {
    try {
      const [hb, mem] = await Promise.all([
        api.get<HeartbeatStatus>('/api/memory/status/heartbeat'),
        api.get<MemoryFile[]>('/api/memory'),
      ]);
      setHeartbeat(hb);
      setFiles(mem);
      setError(null);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, REFRESH_INTERVAL);
    return () => clearInterval(id);
  }, [fetchData]);

  const toggleFile = (name: string) => {
    setExpandedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-3 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-gray-200 px-6 py-4 dark:border-gray-800">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                Memory Dashboard
              </h1>
              {heartbeat && (
                <span className="flex items-center gap-1.5 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/40 dark:text-green-300">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-green-500" />
                  Online
                </span>
              )}
            </div>
            <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
              Nanobot-Zustand — Heartbeat, Skills und Memory-Dateien
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400 dark:text-gray-500">
              Aktualisiert {lastRefresh.toLocaleTimeString('de-DE')}
            </span>
            <button
              onClick={fetchData}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-700"
            >
              Aktualisieren
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
            {error}
          </div>
        )}

        {/* Heartbeat-Status */}
        {heartbeat && (
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Heartbeat
            </h2>
            <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
              <div className="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200">
                {heartbeat.content}
              </div>

              {heartbeat.skills.length > 0 && (
                <div className="mt-4 border-t border-gray-100 pt-4 dark:border-gray-800">
                  <h3 className="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">
                    Skills ({heartbeat.skills.length})
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {heartbeat.skills.map((skill) => (
                      <span
                        key={skill}
                        className="rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Agents.md */}
        {heartbeat?.agents_md && (
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Agents.md
            </h2>
            <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
              <div className="max-h-96 overflow-y-auto whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200">
                {heartbeat.agents_md}
              </div>
            </div>
          </section>
        )}

        {/* Memory-Dateien */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Memory-Dateien ({files.length})
          </h2>
          {files.length === 0 ? (
            <div className="flex h-32 items-center justify-center rounded-xl border border-gray-200 text-gray-400 dark:border-gray-800 dark:text-gray-600">
              Keine Memory-Dateien vorhanden
            </div>
          ) : (
            <div className="space-y-3">
              {files.map((file) => {
                const isExpanded = expandedFiles.has(file.name);
                return (
                  <div
                    key={file.name}
                    className="rounded-xl border border-gray-200 bg-white transition-shadow hover:shadow-md dark:border-gray-800 dark:bg-gray-900"
                  >
                    <button
                      onClick={() => toggleFile(file.name)}
                      className="flex w-full items-center justify-between px-5 py-3.5 text-left"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <svg
                          className={`h-4 w-4 shrink-0 text-gray-400 transition-transform dark:text-gray-500 ${isExpanded ? 'rotate-90' : ''}`}
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth={2}
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                        </svg>
                        <span className="truncate text-sm font-medium text-gray-900 dark:text-white">
                          {file.name}
                        </span>
                      </div>
                      <span className="ml-3 shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                        {formatBytes(file.size)}
                      </span>
                    </button>

                    {isExpanded && (
                      <div className="border-t border-gray-100 px-5 py-4 dark:border-gray-800">
                        <div className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-sm text-gray-800 dark:bg-gray-800 dark:text-gray-200">
                          {file.content || <span className="italic text-gray-400">Leer</span>}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
