import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api/client';
import type { TaskDetail, ChecklistItem, TaskUpdatePayload } from '../types';

interface TaskDetailDialogProps {
  taskId: string | null;
  onClose: () => void;
  onUpdated: () => void;
}

export function TaskDetailDialog({
  taskId,
  onClose,
  onUpdated,
}: TaskDetailDialogProps) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [editingTitle, setEditingTitle] = useState(false);
  const [editingDesc, setEditingDesc] = useState(false);
  const [titleValue, setTitleValue] = useState('');
  const [descValue, setDescValue] = useState('');
  const backdropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!taskId) {
      setTask(null);
      return;
    }
    setLoading(true);
    api
      .get<TaskDetail>(`/api/tasks/${taskId}`)
      .then((data) => {
        setTask(data);
        setTitleValue(data.title);
        setDescValue(data.description || '');
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
        is_done: !item.is_done,
      });
      const updated = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
      setTask(updated);
      onUpdated();
    },
    [taskId, onUpdated],
  );

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  if (!taskId) return null;

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === backdropRef.current) onClose();
      }}
    >
      <div className="flex h-full w-full max-w-lg flex-col overflow-hidden bg-white shadow-2xl dark:bg-gray-950">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-gray-800">
          <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Task-Details
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
          >
            <CloseIcon className="h-5 w-5" />
          </button>
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

            {/* Metadata */}
            <div className="flex flex-wrap gap-3">
              {task.tags.map((tag) => (
                <span
                  key={tag.id}
                  className="inline-flex rounded-full px-2.5 py-1 text-xs font-medium"
                  style={{
                    backgroundColor: tag.color + '20',
                    color: tag.color,
                  }}
                >
                  {tag.name}
                </span>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-500 dark:text-gray-400">Zuständig</span>
                <p className="mt-0.5 font-medium text-gray-900 dark:text-white">
                  {task.assignee === 'agent' ? 'AI Agent' : 'Ich'}
                </p>
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
            </div>

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
            {task.checklist_items.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-semibold text-gray-600 dark:text-gray-400">
                  Checkliste ({task.checklist_items.filter((i) => i.is_done).length}/
                  {task.checklist_items.length})
                </h3>
                <div className="mb-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-800">
                  <div
                    className="h-full rounded-full bg-indigo-500 transition-all"
                    style={{
                      width: `${
                        task.checklist_items.length > 0
                          ? (task.checklist_items.filter((i) => i.is_done).length /
                              task.checklist_items.length) *
                            100
                          : 0
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
                          checked={item.is_done}
                          onChange={() => toggleChecklistItem(item)}
                          className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-gray-600"
                        />
                        <span
                          className={`text-sm ${
                            item.is_done
                              ? 'text-gray-400 line-through dark:text-gray-600'
                              : 'text-gray-800 dark:text-gray-200'
                          }`}
                        >
                          {item.title}
                        </span>
                      </label>
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
