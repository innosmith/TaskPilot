import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api/client';
import type { TaskDetail, ChecklistItem, TaskUpdatePayload, AgentJob, Tag, TaskDetailMode } from '../types';

interface TaskDetailDialogProps {
  taskId: string | null;
  onClose: () => void;
  onUpdated: () => void;
}

interface ModelInfo {
  id: string;
  name: string;
  type: 'local' | 'cloud';
  provider: string;
}

interface ModelsData {
  local: ModelInfo[];
  cloud: ModelInfo[];
}

export function TaskDetailDialog({
  taskId,
  onClose,
  onUpdated,
}: TaskDetailDialogProps) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [agentJobs, setAgentJobs] = useState<AgentJob[]>([]);
  const [allTags, setAllTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingTitle, setEditingTitle] = useState(false);
  const [editingDesc, setEditingDesc] = useState(false);
  const [titleValue, setTitleValue] = useState('');
  const [descValue, setDescValue] = useState('');
  const [newChecklistText, setNewChecklistText] = useState('');
  const [showTagPicker, setShowTagPicker] = useState(false);
  const [mode, setMode] = useState<TaskDetailMode>('modal');
  const [models, setModels] = useState<ModelsData | null>(null);
  const backdropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get<ModelsData>('/api/models').then(setModels).catch(() => {});
  }, []);

  useEffect(() => {
    api.get<{ task_detail_mode?: string }>('/api/settings')
      .then((s) => {
        if (s.task_detail_mode === 'panel' || s.task_detail_mode === 'fullscreen') {
          setMode(s.task_detail_mode);
        }
      })
      .catch(() => {});
  }, []);

  const persistMode = useCallback((m: TaskDetailMode) => {
    setMode(m);
    api.patch('/api/settings', { task_detail_mode: m }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!taskId) {
      setTask(null);
      setAgentJobs([]);
      return;
    }
    setLoading(true);
    Promise.all([
      api.get<TaskDetail>(`/api/tasks/${taskId}`),
      api.get<AgentJob[]>(`/api/agent-jobs?task_id=${taskId}`),
      api.get<Tag[]>('/api/tags'),
    ])
      .then(([taskData, jobsData, tagsData]) => {
        setTask(taskData);
        setAgentJobs(jobsData);
        setAllTags(tagsData);
        setTitleValue(taskData.title);
        setDescValue(taskData.description || '');
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [taskId]);

  const updateTask = useCallback(
    async (payload: TaskUpdatePayload) => {
      if (!taskId) return;
      await api.patch(`/api/tasks/${taskId}`, payload);
      onUpdated();
      const updated = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
      setTask(updated);
    },
    [taskId, onUpdated],
  );

  const saveTitle = useCallback(async () => {
    if (titleValue.trim() && titleValue !== task?.title) {
      await updateTask({ title: titleValue.trim() });
    }
    setEditingTitle(false);
  }, [titleValue, task?.title, updateTask]);

  const saveDescription = useCallback(async () => {
    if (descValue !== (task?.description || '')) {
      await updateTask({ description: descValue });
    }
    setEditingDesc(false);
  }, [descValue, task?.description, updateTask]);

  const toggleChecklistItem = useCallback(
    async (item: ChecklistItem) => {
      if (!taskId) return;
      await api.patch(`/api/tasks/${taskId}/checklist/${item.id}`, {
        is_checked: !item.is_checked,
      });
      const updated = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
      setTask(updated);
      onUpdated();
    },
    [taskId, onUpdated],
  );

  const addChecklistItem = useCallback(
    async (text: string) => {
      if (!taskId || !text.trim()) return;
      await api.post(`/api/tasks/${taskId}/checklist`, { text: text.trim() });
      const updated = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
      setTask(updated);
      setNewChecklistText('');
      onUpdated();
    },
    [taskId, onUpdated],
  );

  const toggleTag = useCallback(
    async (tag: Tag) => {
      if (!taskId || !task) return;
      const hasTag = task.tags.some((t) => t.id === tag.id);
      if (hasTag) {
        await api.delete(`/api/tags/tasks/${taskId}/tags/${tag.id}`);
      } else {
        await api.post(`/api/tags/tasks/${taskId}/tags/${tag.id}`);
      }
      const updated = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
      setTask(updated);
      onUpdated();
    },
    [taskId, task, onUpdated],
  );

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  if (!taskId) return null;

  const backdropClass =
    mode === 'fullscreen'
      ? 'fixed inset-0 z-50'
      : mode === 'modal'
        ? 'fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm'
        : 'fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm';

  const panelClass =
    mode === 'fullscreen'
      ? 'flex h-full w-full flex-col overflow-hidden bg-white dark:bg-gray-950'
      : mode === 'modal'
        ? 'flex w-full max-w-2xl max-h-[85vh] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-gray-950'
        : 'flex h-full w-full max-w-lg flex-col overflow-hidden bg-white shadow-2xl dark:bg-gray-950';

  return (
    <div
      ref={backdropRef}
      className={backdropClass}
      onClick={(e) => {
        if (e.target === backdropRef.current) onClose();
      }}
    >
      <div className={panelClass}>
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-gray-800">
          <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Task-Details
          </h2>
          <div className="flex items-center gap-1">
            <button
              onClick={() => persistMode('modal')}
              className={`rounded-lg p-1.5 transition-colors ${mode === 'modal' ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400' : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300'}`}
              title="Modal"
            >
              <ModalIcon className="h-4 w-4" />
            </button>
            <button
              onClick={() => persistMode('panel')}
              className={`rounded-lg p-1.5 transition-colors ${mode === 'panel' ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400' : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300'}`}
              title="Seitenpanel"
            >
              <PanelIcon className="h-4 w-4" />
            </button>
            <button
              onClick={() => persistMode('fullscreen')}
              className={`rounded-lg p-1.5 transition-colors ${mode === 'fullscreen' ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400' : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300'}`}
              title="Vollbild"
            >
              <FullscreenIcon className="h-4 w-4" />
            </button>
            <div className="mx-1 h-4 w-px bg-gray-200 dark:bg-gray-700" />
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
            >
              <CloseIcon className="h-5 w-5" />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex flex-1 items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
          </div>
        ) : task ? (
          <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
            {/* Title */}
            {editingTitle ? (
              <input
                value={titleValue}
                onChange={(e) => setTitleValue(e.target.value)}
                onBlur={saveTitle}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') saveTitle();
                  if (e.key === 'Escape') {
                    setTitleValue(task.title);
                    setEditingTitle(false);
                  }
                }}
                autoFocus
                className="w-full rounded-lg border border-indigo-300 bg-transparent px-3 py-2 text-xl font-semibold text-gray-900 outline-none focus:ring-2 focus:ring-indigo-500 dark:border-indigo-700 dark:text-white"
              />
            ) : (
              <h1
                onClick={() => setEditingTitle(true)}
                className="cursor-pointer rounded-lg px-3 py-2 text-xl font-semibold text-gray-900 transition-colors hover:bg-gray-50 dark:text-white dark:hover:bg-gray-900"
              >
                {task.title}
              </h1>
            )}

            {/* Tags */}
            <div className="flex flex-wrap items-center gap-2">
              {task.tags.map((tag) => (
                <button
                  key={tag.id}
                  onClick={() => toggleTag(tag)}
                  className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-opacity hover:opacity-70"
                  style={{ backgroundColor: tag.color + '20', color: tag.color }}
                  title="Tag entfernen"
                >
                  {tag.name}
                  <span className="text-[10px]">x</span>
                </button>
              ))}
              <div className="relative">
                <button
                  onClick={() => setShowTagPicker(!showTagPicker)}
                  className="rounded-full border border-dashed border-gray-300 px-2 py-0.5 text-xs text-gray-500 transition-colors hover:border-gray-400 hover:text-gray-700 dark:border-gray-700 dark:text-gray-500 dark:hover:border-gray-600 dark:hover:text-gray-400"
                >
                  + Tag
                </button>
                {showTagPicker && (
                  <div className="absolute left-0 top-8 z-10 w-48 rounded-lg border border-gray-200 bg-white p-2 shadow-xl dark:border-gray-700 dark:bg-gray-900">
                    {allTags.filter((t) => !task.tags.some((tt) => tt.id === t.id)).map((tag) => (
                      <button
                        key={tag.id}
                        onClick={() => { toggleTag(tag); setShowTagPicker(false); }}
                        className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors hover:bg-gray-50 dark:hover:bg-gray-800"
                      >
                        <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: tag.color }} />
                        {tag.name}
                      </button>
                    ))}
                    {allTags.filter((t) => !task.tags.some((tt) => tt.id === t.id)).length === 0 && (
                      <p className="px-2 py-1 text-xs text-gray-400">Keine weiteren Tags</p>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-500 dark:text-gray-400">Zuständig</span>
                <button
                  onClick={() => updateTask({ assignee: task.assignee === 'agent' ? 'me' : 'agent' })}
                  className={`mt-0.5 flex items-center gap-2 rounded-lg px-2 py-1 font-medium transition-colors ${
                    task.assignee === 'agent'
                      ? 'bg-violet-50 text-violet-700 hover:bg-violet-100 dark:bg-violet-950 dark:text-violet-300 dark:hover:bg-violet-900'
                      : 'bg-gray-50 text-gray-900 hover:bg-gray-100 dark:bg-gray-900 dark:text-white dark:hover:bg-gray-800'
                  }`}
                >
                  {task.assignee === 'agent' ? (
                    <>
                      <AgentIcon className="h-4 w-4" />
                      AI Agent
                    </>
                  ) : (
                    <>
                      <UserIcon className="h-4 w-4" />
                      Ich
                    </>
                  )}
                </button>
              </div>
              {task.due_date && (
                <div>
                  <span className="text-gray-500 dark:text-gray-400">Fällig</span>
                  <p className="mt-0.5 font-medium text-gray-900 dark:text-white">
                    {new Date(task.due_date).toLocaleDateString('de-DE', {
                      day: 'numeric',
                      month: 'long',
                      year: 'numeric',
                    })}
                  </p>
                </div>
              )}

              {/* Wiederholung */}
              <div>
                <span className="text-gray-500 dark:text-gray-400">Wiederholung</span>
                <RecurrenceSelector
                  value={task.recurrence_rule}
                  isInstance={!!task.template_id}
                  onChange={(rule) => updateTask({ recurrence_rule: rule } as TaskUpdatePayload)}
                />
              </div>

              {/* Kalender-Blocker (nur bei Wiederholungsvorlagen) */}
              {task.recurrence_rule && !task.template_id && (
                <>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Kalender-Dauer</span>
                    <select
                      value={task.calendar_duration_minutes ?? ''}
                      onChange={(e) => updateTask({ calendar_duration_minutes: e.target.value ? Number(e.target.value) : null } as TaskUpdatePayload)}
                      className="mt-0.5 w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs dark:border-gray-700 dark:bg-gray-900 dark:text-white"
                    >
                      <option value="">Kein Kalenderblocker</option>
                      <option value="15">15 Minuten</option>
                      <option value="30">30 Minuten</option>
                      <option value="45">45 Minuten</option>
                      <option value="60">1 Stunde</option>
                      <option value="90">1.5 Stunden</option>
                      <option value="120">2 Stunden</option>
                      <option value="180">3 Stunden</option>
                      <option value="240">4 Stunden</option>
                    </select>
                  </div>
                  {(task.calendar_duration_minutes ?? 0) > 0 && (
                    <div>
                      <span className="text-gray-500 dark:text-gray-400">Bevorzugte Zeit</span>
                      <select
                        value={task.calendar_preferred_time ?? 'morning_after_1030'}
                        onChange={(e) => updateTask({ calendar_preferred_time: e.target.value } as TaskUpdatePayload)}
                        className="mt-0.5 w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs dark:border-gray-700 dark:bg-gray-900 dark:text-white"
                      >
                        <option value="morning_after_1030">Vormittag (ab 10:30)</option>
                        <option value="afternoon">Nachmittag (13:00-18:00)</option>
                        <option value="any">Ganzer Tag (08:00-18:00)</option>
                      </select>
                    </div>
                  )}
                </>
              )}

              <div className="col-span-2">
                <label className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={task.is_completed}
                    onChange={() => updateTask({ is_completed: !task.is_completed })}
                    className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-gray-600"
                  />
                  <span className={`text-sm font-medium ${task.is_completed ? 'text-green-600 dark:text-green-400' : 'text-gray-700 dark:text-gray-300'}`}>
                    {task.is_completed ? 'Erledigt' : 'Als erledigt markieren'}
                  </span>
                </label>
              </div>
            </div>

            {/* Agent-Steuerung */}
            {task.assignee === 'agent' && (
              <div className="rounded-lg border border-violet-200 bg-violet-50/50 p-4 dark:border-violet-900 dark:bg-violet-950/30">
                <h3 className="mb-3 text-sm font-semibold text-violet-700 dark:text-violet-300">
                  Agent-Konfiguration
                </h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <label className="text-xs text-gray-500 dark:text-gray-400">LLM-Modell</label>
                    <select
                      value={task.llm_override || ''}
                      onChange={(e) => updateTask({ llm_override: e.target.value || undefined } as TaskUpdatePayload)}
                      className="mt-0.5 w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs dark:border-gray-700 dark:bg-gray-900 dark:text-white"
                    >
                      <option value="">Standard (lokal)</option>
                      {models && (
                        <>
                          <optgroup label="🔒 Lokal (Datenschutz)">
                            {models.local.map(m => (
                              <option key={m.id} value={m.id}>{m.name}</option>
                            ))}
                          </optgroup>
                          <optgroup label="☁️ Cloud">
                            {models.cloud.map(m => (
                              <option
                                key={m.id}
                                value={m.id}
                                disabled={task.data_class === 'highly_confidential'}
                              >
                                {m.name}{task.data_class === 'highly_confidential' ? ' (gesperrt)' : ''}
                              </option>
                            ))}
                          </optgroup>
                        </>
                      )}
                      {!models && (
                        <>
                          <option value="ollama/qwen3.5:35b">Qwen 3.5 35B</option>
                          <option value="ollama/qwen3:32b">Qwen 3 32B</option>
                        </>
                      )}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 dark:text-gray-400">Autonomie</label>
                    <select
                      value={task.autonomy_level}
                      onChange={(e) => updateTask({ autonomy_level: e.target.value } as TaskUpdatePayload)}
                      className="mt-0.5 w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs dark:border-gray-700 dark:bg-gray-900 dark:text-white"
                    >
                      <option value="L0">L0 — Blockieren</option>
                      <option value="L1">L1 — Genehmigen</option>
                      <option value="L2">L2 — Benachrichtigen</option>
                      <option value="L3">L3 — Vollautonom</option>
                    </select>
                  </div>
                  <div className="col-span-2">
                    <label className="text-xs text-gray-500 dark:text-gray-400">Datenklasse</label>
                    <div className="mt-1 flex gap-2">
                      {(['internal', 'confidential', 'highly_confidential'] as const).map((dc) => (
                        <button
                          key={dc}
                          onClick={() => updateTask({ data_class: dc } as TaskUpdatePayload)}
                          className={`rounded-lg px-2 py-1 text-xs font-medium transition-colors ${
                            task.data_class === dc
                              ? dc === 'highly_confidential'
                                ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
                                : dc === 'confidential'
                                  ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
                                  : 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
                              : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'
                          }`}
                        >
                          {{ internal: 'Intern', confidential: 'Vertraulich', highly_confidential: 'Streng vertraulich' }[dc]}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Description */}
            <div>
              <h3 className="mb-2 text-sm font-semibold text-gray-600 dark:text-gray-400">
                Beschreibung
              </h3>
              {editingDesc ? (
                <div>
                  <textarea
                    value={descValue}
                    onChange={(e) => setDescValue(e.target.value)}
                    rows={8}
                    autoFocus
                    className="w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-900 outline-none focus:ring-2 focus:ring-indigo-500 dark:border-gray-700 dark:text-white"
                  />
                  <div className="mt-2 flex gap-2">
                    <button
                      onClick={saveDescription}
                      className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-700"
                    >
                      Speichern
                    </button>
                    <button
                      onClick={() => {
                        setDescValue(task.description || '');
                        setEditingDesc(false);
                      }}
                      className="rounded-lg px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                    >
                      Abbrechen
                    </button>
                  </div>
                </div>
              ) : (
                <div
                  onClick={() => setEditingDesc(true)}
                  className="min-h-[60px] cursor-pointer rounded-lg px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-900"
                >
                  {task.description ? (
                    <div className="whitespace-pre-wrap">{task.description}</div>
                  ) : (
                    <span className="italic text-gray-400 dark:text-gray-600">
                      Beschreibung hinzufügen...
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Checklist */}
            <div>
              <h3 className="mb-2 text-sm font-semibold text-gray-600 dark:text-gray-400">
                Checkliste{task.checklist_items.length > 0 && ` (${task.checklist_items.filter((i) => i.is_checked).length}/${task.checklist_items.length})`}
              </h3>
              {task.checklist_items.length > 0 && (
                <>
                  <div className="mb-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-800">
                    <div
                      className="h-full rounded-full bg-indigo-500 transition-all"
                      style={{
                        width: `${
                          (task.checklist_items.filter((i) => i.is_checked).length /
                            task.checklist_items.length) * 100
                        }%`,
                      }}
                    />
                  </div>
                  <div className="space-y-1">
                    {task.checklist_items
                      .sort((a, b) => a.position - b.position)
                      .map((item) => (
                        <label
                          key={item.id}
                          className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-gray-50 dark:hover:bg-gray-900"
                        >
                          <input
                            type="checkbox"
                            checked={item.is_checked}
                            onChange={() => toggleChecklistItem(item)}
                            className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-gray-600"
                          />
                          <span
                            className={`text-sm ${
                              item.is_checked
                                ? 'text-gray-400 line-through dark:text-gray-600'
                                : 'text-gray-800 dark:text-gray-200'
                            }`}
                          >
                            {item.text}
                          </span>
                        </label>
                      ))}
                  </div>
                </>
              )}
              <div className="mt-2 flex gap-2">
                <input
                  value={newChecklistText}
                  onChange={(e) => setNewChecklistText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && newChecklistText.trim()) {
                      addChecklistItem(newChecklistText);
                    }
                  }}
                  placeholder="Neuer Eintrag..."
                  className="flex-1 rounded-lg border border-gray-200 bg-transparent px-3 py-1.5 text-sm text-gray-900 outline-none placeholder:text-gray-400 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-300 dark:border-gray-700 dark:text-white dark:placeholder:text-gray-600"
                />
                <button
                  onClick={() => addChecklistItem(newChecklistText)}
                  disabled={!newChecklistText.trim()}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-40"
                >
                  +
                </button>
              </div>
            </div>

            {/* Agent Jobs */}
            {agentJobs.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-semibold text-gray-600 dark:text-gray-400">
                  Agent-Aufträge
                </h3>
                <div className="space-y-2">
                  {agentJobs.map((job) => (
                    <div
                      key={job.id}
                      className="rounded-lg border border-gray-200 p-3 dark:border-gray-800"
                    >
                      <div className="flex items-center justify-between">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          job.status === 'completed' ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' :
                          job.status === 'running' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300' :
                          job.status === 'failed' ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' :
                          job.status === 'awaiting_approval' ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300' :
                          'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
                        }`}>
                          {job.status}
                        </span>
                        <span className="text-xs text-gray-400">
                          {new Date(job.created_at).toLocaleString('de-DE')}
                        </span>
                      </div>
                      {job.output && (
                        <div className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                          {job.output}
                        </div>
                      )}
                      {job.error_message && (
                        <p className="mt-2 text-xs text-red-600 dark:text-red-400">{job.error_message}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center text-gray-500">
            Task nicht gefunden.
          </div>
        )}
      </div>
    </div>
  );
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
    </svg>
  );
}

const RECURRENCE_PRESETS = [
  { label: 'Keine', value: null },
  { label: 'Täglich (09:00)', value: '0 9 * * *' },
  { label: 'Werktags (09:00)', value: '0 9 * * 1-5' },
  { label: 'Wöchentlich Mo (07:00)', value: '0 7 * * MON' },
  { label: 'Wöchentlich Mo (09:00)', value: '0 9 * * MON' },
  { label: 'Monatlich 1. (08:00)', value: '0 8 1 * *' },
  { label: 'Monatlich 15. (08:00)', value: '0 8 15 * *' },
  { label: 'Monatlich 20. (08:00)', value: '0 8 20 * *' },
  { label: 'Monatlich 25. (08:00)', value: '0 8 25 * *' },
] as const;

function cronToHumanDE(cron: string): string {
  const presets: Record<string, string> = {
    '0 9 * * *': 'Täglich um 09:00',
    '0 7 * * *': 'Täglich um 07:00',
    '0 8 * * *': 'Täglich um 08:00',
    '0 9 * * 1-5': 'Werktags um 09:00',
    '0 7 * * 1-5': 'Werktags um 07:00',
    '0 7 * * MON': 'Jeden Montag um 07:00',
    '0 8 * * MON': 'Jeden Montag um 08:00',
    '0 9 * * MON': 'Jeden Montag um 09:00',
    '0 8 1 * *': 'Monatlich am 1. um 08:00',
    '0 9 1 * *': 'Monatlich am 1. um 09:00',
    '0 8 15 * *': 'Monatlich am 15. um 08:00',
  };
  return presets[cron] || cron;
}

function RecurrenceSelector({
  value,
  isInstance,
  onChange,
}: {
  value: string | null;
  isInstance: boolean;
  onChange: (rule: string | null) => void;
}) {
  const [showCustom, setShowCustom] = useState(false);
  const [customValue, setCustomValue] = useState('');

  if (isInstance) {
    return (
      <div className="mt-0.5 flex items-center gap-1.5 rounded-lg bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
        <RepeatSmallIcon className="h-3.5 w-3.5" />
        Instanz einer Vorlage
      </div>
    );
  }

  return (
    <div className="mt-0.5">
      <select
        value={
          showCustom
            ? '__custom__'
            : value && RECURRENCE_PRESETS.some((p) => p.value === value)
              ? value
              : value
                ? '__custom__'
                : ''
        }
        onChange={(e) => {
          const v = e.target.value;
          if (v === '__custom__') {
            setShowCustom(true);
            setCustomValue(value || '');
          } else if (v === '') {
            setShowCustom(false);
            onChange(null);
          } else {
            setShowCustom(false);
            onChange(v);
          }
        }}
        className="w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs dark:border-gray-700 dark:bg-gray-900 dark:text-white"
      >
        {RECURRENCE_PRESETS.map((p) => (
          <option key={p.label} value={p.value ?? ''}>
            {p.label}
          </option>
        ))}
        <option value="__custom__">Benutzerdefiniert (Cron)...</option>
      </select>
      {showCustom && (
        <div className="mt-1.5 flex gap-1.5">
          <input
            value={customValue}
            onChange={(e) => setCustomValue(e.target.value)}
            placeholder="z.B. 0 7 * * MON"
            className="flex-1 rounded-lg border border-gray-200 bg-transparent px-2 py-1 text-xs outline-none focus:border-indigo-300 dark:border-gray-700 dark:text-white"
          />
          <button
            onClick={() => {
              if (customValue.trim()) {
                onChange(customValue.trim());
                setShowCustom(false);
              }
            }}
            className="rounded-lg bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-700"
          >
            OK
          </button>
        </div>
      )}
      {value && (
        <p className="mt-1 text-[10px] text-gray-400 dark:text-gray-500">
          {cronToHumanDE(value)}
        </p>
      )}
    </div>
  );
}

function RepeatSmallIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182M21.015 4.356v4.992" />
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

function UserIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
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
