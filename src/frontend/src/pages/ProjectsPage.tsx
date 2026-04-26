import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';

interface ProjectMetrics {
  id: string;
  name: string;
  color: string;
  status: 'active' | 'archived';
  total_tasks: number;
  open_tasks: number;
  completed_tasks: number;
  overdue_tasks: number;
  progress_pct: number;
}

interface ProjectCreatePayload {
  name: string;
  color: string;
  description?: string;
}

const PRESET_COLORS = [
  '#3B82F6',
  '#EF4444',
  '#10B981',
  '#F59E0B',
  '#8B5CF6',
  '#EC4899',
  '#6366F1',
  '#14B8A6',
];

export function ProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectMetrics[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState('');
  const [formColor, setFormColor] = useState(PRESET_COLORS[0]);
  const [formDescription, setFormDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchProjects = useCallback(async () => {
    try {
      const data = await api.get<ProjectMetrics[]>('/api/projects/overview/metrics');
      setProjects(data);
    } catch { /* handled by api client */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchProjects(); }, [fetchProjects]);

  const resetForm = () => {
    setFormName('');
    setFormColor(PRESET_COLORS[0]);
    setFormDescription('');
    setShowForm(false);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim()) return;
    setSubmitting(true);
    try {
      const payload: ProjectCreatePayload = {
        name: formName.trim(),
        color: formColor,
      };
      if (formDescription.trim()) {
        payload.description = formDescription.trim();
      }
      await api.post('/api/projects', payload);
      resetForm();
      fetchProjects();
    } catch { /* handled by api client */ }
    finally { setSubmitting(false); }
  };

  const handleArchive = async (e: React.MouseEvent, projectId: string) => {
    e.stopPropagation();
    try {
      await api.patch(`/api/projects/${projectId}`, { status: 'archived' });
      fetchProjects();
    } catch { /* handled by api client */ }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-3 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  const activeProjects = projects.filter((p) => p.status === 'active');
  const archivedProjects = projects.filter((p) => p.status === 'archived');

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-gray-200 px-6 py-4 dark:border-gray-800">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">Projekte</h1>
            <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
              {activeProjects.length} aktiv{archivedProjects.length > 0 && ` · ${archivedProjects.length} archiviert`}
            </p>
          </div>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700"
          >
            {showForm ? 'Abbrechen' : 'Neues Projekt'}
          </button>
        </div>
      </div>

      {showForm && (
        <div className="border-b border-gray-200 bg-gray-50 px-6 py-4 dark:border-gray-800 dark:bg-gray-900/50">
          <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-4">
            <div className="min-w-[200px] flex-1">
              <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                Name
              </label>
              <input
                type="text"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="Projektname"
                autoFocus
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:placeholder-gray-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                Farbe
              </label>
              <div className="flex gap-1.5">
                {PRESET_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setFormColor(c)}
                    className={`h-7 w-7 rounded-full transition-transform hover:scale-110 ${
                      formColor === c ? 'ring-2 ring-offset-2 ring-indigo-500 dark:ring-offset-gray-900' : ''
                    }`}
                    style={{ backgroundColor: c }}
                  />
                ))}
              </div>
            </div>
            <div className="min-w-[200px] flex-1">
              <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                Beschreibung
              </label>
              <input
                type="text"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                placeholder="Optional"
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:placeholder-gray-500"
              />
            </div>
            <button
              type="submit"
              disabled={submitting || !formName.trim()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? 'Erstellen…' : 'Erstellen'}
            </button>
          </form>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-6">
        {projects.length === 0 ? (
          <div className="flex h-48 items-center justify-center text-gray-400 dark:text-gray-600">
            <p>Noch keine Projekte vorhanden</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-gray-200 dark:border-gray-800">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900/60">
                  <th className="px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Projekt</th>
                  <th className="px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Status</th>
                  <th className="px-4 py-3 text-right font-medium text-gray-500 dark:text-gray-400">Offen</th>
                  <th className="px-4 py-3 text-right font-medium text-gray-500 dark:text-gray-400">Erledigt</th>
                  <th className="px-4 py-3 text-right font-medium text-gray-500 dark:text-gray-400">Überfällig</th>
                  <th className="w-48 px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Fortschritt</th>
                  <th className="px-4 py-3 text-right font-medium text-gray-500 dark:text-gray-400">Aktionen</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                {projects.map((project) => (
                  <tr
                    key={project.id}
                    onClick={() => navigate(`/projects/${project.id}`)}
                    className="cursor-pointer bg-white transition-colors hover:bg-gray-50 dark:bg-gray-900 dark:hover:bg-gray-800/60"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <span
                          className="h-3 w-3 shrink-0 rounded-full"
                          style={{ backgroundColor: project.color }}
                        />
                        <span className="font-medium text-gray-900 dark:text-white">
                          {project.name}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          project.status === 'active'
                            ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
                            : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'
                        }`}
                      >
                        {project.status === 'active' ? 'Aktiv' : 'Archiviert'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-gray-700 dark:text-gray-300">
                      {project.open_tasks}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-gray-700 dark:text-gray-300">
                      {project.completed_tasks}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`tabular-nums ${
                          project.overdue_tasks > 0
                            ? 'font-medium text-red-600 dark:text-red-400'
                            : 'text-gray-700 dark:text-gray-300'
                        }`}
                      >
                        {project.overdue_tasks}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                          <div
                            className="h-full rounded-full bg-indigo-500 transition-all"
                            style={{ width: `${Math.min(project.progress_pct, 100)}%` }}
                          />
                        </div>
                        <span className="w-10 text-right text-xs tabular-nums text-gray-500 dark:text-gray-400">
                          {Math.round(project.progress_pct)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {project.status === 'active' && (
                        <button
                          onClick={(e) => handleArchive(e, project.id)}
                          className="rounded-lg px-2.5 py-1 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
                        >
                          Archivieren
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
