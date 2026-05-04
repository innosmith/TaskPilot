import { useState, useEffect, useCallback, useRef } from 'react';
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { api } from '../api/client';
import { RichTextEditor } from './RichTextEditor';
import type {
  TaskDetail, ChecklistItem, TaskUpdatePayload, AgentJob, Tag,
  TaskDetailMode, PipelineColumn, PipelineData, Project, BoardColumn,
} from '../types';

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

interface ActivityLogEntry {
  id: string;
  task_id: string;
  event_type: string;
  actor: string;
  details: Record<string, unknown> | null;
  created_at: string;
}

interface AttachmentEntry {
  id: string;
  task_id: string;
  filename: string;
  filepath: string;
  mime_type: string | null;
  size: number;
  uploaded_at: string;
}

export function TaskDetailDialog({ taskId, onClose, onUpdated }: TaskDetailDialogProps) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [agentJobs, setAgentJobs] = useState<AgentJob[]>([]);
  const [allTags, setAllTags] = useState<Tag[]>([]);
  const [allProjects, setAllProjects] = useState<Project[]>([]);
  const [pipelineCols, setPipelineCols] = useState<PipelineColumn[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(false);
  const [editingTitle, setEditingTitle] = useState(false);
  const [editingDesc, setEditingDesc] = useState(false);
  const [titleValue, setTitleValue] = useState('');
  const [descValue, setDescValue] = useState('');
  const [newChecklistText, setNewChecklistText] = useState('');
  const [editingChecklistId, setEditingChecklistId] = useState<string | null>(null);
  const [editingChecklistText, setEditingChecklistText] = useState('');
  const [showTagPicker, setShowTagPicker] = useState(false);
  const [mode, setMode] = useState<TaskDetailMode>('modal');
  const [models, setModels] = useState<ModelsData | null>(null);
  const [activities, setActivities] = useState<ActivityLogEntry[]>([]);
  const [attachments, setAttachments] = useState<AttachmentEntry[]>([]);
  const [commentText, setCommentText] = useState('');
  const [submittingComment, setSubmittingComment] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dateInputRef = useRef<HTMLInputElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const handleChecklistDragEnd = useCallback(async (event: DragEndEvent) => {
    if (!task || !taskId) return;
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const sorted = [...task.checklist_items].sort((a, b) => a.position - b.position);
    const oldIdx = sorted.findIndex((i) => i.id === active.id);
    const newIdx = sorted.findIndex((i) => i.id === over.id);
    if (oldIdx === -1 || newIdx === -1) return;
    const reordered = arrayMove(sorted, oldIdx, newIdx);
    setTask({ ...task, checklist_items: reordered.map((item, idx) => ({ ...item, position: idx })) });
    await api.patch(`/api/tasks/${taskId}/checklist/${active.id}`, { position: newIdx });
    const updated = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
    setTask(updated);
    onUpdated();
  }, [task, taskId, onUpdated]);

  const [defaultLocalModel, setDefaultLocalModel] = useState('');

  useEffect(() => {
    api.get<ModelsData>('/api/models').then(setModels).catch(() => {});
    api.get<Project[]>('/api/projects').then(setAllProjects).catch(() => {});
    api.get<PipelineData>('/api/pipeline').then((d) => setPipelineCols(d.columns)).catch(() => {});
    api.get<{ llm_default_local_model: string | null }>('/api/settings/llm')
      .then(s => { if (s.llm_default_local_model) setDefaultLocalModel(s.llm_default_local_model); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    api.get<{ task_detail_mode?: string }>('/api/settings')
      .then((s) => { if (s.task_detail_mode === 'panel' || s.task_detail_mode === 'fullscreen') setMode(s.task_detail_mode); })
      .catch(() => {});
  }, []);

  const persistMode = useCallback((m: TaskDetailMode) => {
    setMode(m);
    api.patch('/api/settings', { task_detail_mode: m }).catch(() => {});
  }, []);

  const loadProject = useCallback((projectId: string) => {
    api.get<Project>(`/api/projects/${projectId}`)
      .then(setCurrentProject)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!taskId) { setTask(null); setAgentJobs([]); setActivities([]); setAttachments([]); setCurrentProject(null); return; }
    setLoading(true);
    Promise.all([
      api.get<TaskDetail>(`/api/tasks/${taskId}`),
      api.get<AgentJob[]>(`/api/agent-jobs?task_id=${taskId}`),
      api.get<Tag[]>('/api/tags'),
      api.get<ActivityLogEntry[]>(`/api/tasks/${taskId}/activity`),
      api.get<AttachmentEntry[]>(`/api/tasks/${taskId}/attachments`),
    ])
      .then(([taskData, jobsData, tagsData, activityData, attachmentData]) => {
        setTask(taskData);
        setAgentJobs(jobsData);
        setAllTags(tagsData);
        setActivities(activityData);
        setAttachments(attachmentData);
        setTitleValue(taskData.title);
        setDescValue(taskData.description || '');
        loadProject(taskData.project_id);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [taskId, loadProject]);

  const updateTask = useCallback(async (payload: TaskUpdatePayload) => {
    if (!taskId) return;
    await api.patch(`/api/tasks/${taskId}`, payload);
    onUpdated();
    const updated = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
    setTask(updated);
    if (payload.project_id) loadProject(payload.project_id);
    else if (payload.board_column_id && currentProject) {
      setCurrentProject({ ...currentProject });
    }
  }, [taskId, onUpdated, loadProject, currentProject]);

  const saveTitle = useCallback(async () => {
    if (titleValue.trim() && titleValue !== task?.title) await updateTask({ title: titleValue.trim() });
    setEditingTitle(false);
  }, [titleValue, task?.title, updateTask]);

  const saveDescription = useCallback(async () => {
    if (descValue !== (task?.description || '')) await updateTask({ description: descValue });
    setEditingDesc(false);
  }, [descValue, task?.description, updateTask]);

  const toggleChecklistItem = useCallback(async (item: ChecklistItem) => {
    if (!taskId) return;
    await api.patch(`/api/tasks/${taskId}/checklist/${item.id}`, { is_checked: !item.is_checked });
    const updated = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
    setTask(updated);
    onUpdated();
  }, [taskId, onUpdated]);

  const addChecklistItem = useCallback(async (text: string) => {
    if (!taskId || !text.trim()) return;
    await api.post(`/api/tasks/${taskId}/checklist`, { text: text.trim() });
    const updated = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
    setTask(updated);
    setNewChecklistText('');
    onUpdated();
  }, [taskId, onUpdated]);

  const deleteChecklistItem = useCallback(async (itemId: string) => {
    if (!taskId) return;
    await api.delete(`/api/tasks/${taskId}/checklist/${itemId}`);
    const updated = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
    setTask(updated);
    onUpdated();
  }, [taskId, onUpdated]);

  const updateChecklistText = useCallback(async (itemId: string, text: string) => {
    if (!taskId || !text.trim()) return;
    await api.patch(`/api/tasks/${taskId}/checklist/${itemId}`, { text: text.trim() });
    const updated = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
    setTask(updated);
    setEditingChecklistId(null);
    onUpdated();
  }, [taskId, onUpdated]);

  const toggleTag = useCallback(async (tag: Tag) => {
    if (!taskId || !task) return;
    const hasTag = task.tags.some((t) => t.id === tag.id);
    if (hasTag) await api.delete(`/api/tags/tasks/${taskId}/tags/${tag.id}`);
    else await api.post(`/api/tags/tasks/${taskId}/tags/${tag.id}`);
    const updated = await api.get<TaskDetail>(`/api/tasks/${taskId}`);
    setTask(updated);
    onUpdated();
  }, [taskId, task, onUpdated]);

  const submitComment = useCallback(async () => {
    if (!taskId || !commentText.trim()) return;
    setSubmittingComment(true);
    try {
      await api.post(`/api/tasks/${taskId}/activity`, { text: commentText.trim() });
      setCommentText('');
      const updatedActivities = await api.get<ActivityLogEntry[]>(`/api/tasks/${taskId}/activity`);
      setActivities(updatedActivities);
    } finally { setSubmittingComment(false); }
  }, [taskId, commentText]);

  const uploadFiles = useCallback(async (files: FileList | File[]) => {
    if (!taskId) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append('file', file);
        await api.upload(`/api/tasks/${taskId}/attachments`, form);
      }
      const updated = await api.get<AttachmentEntry[]>(`/api/tasks/${taskId}/attachments`);
      setAttachments(updated);
    } finally { setUploading(false); }
  }, [taskId]);

  const deleteAttachment = useCallback(async (attId: string) => {
    if (!taskId) return;
    await api.delete(`/api/tasks/${taskId}/attachments/${attId}`);
    setAttachments((prev) => prev.filter((a) => a.id !== attId));
  }, [taskId]);

  const handleProjectChange = useCallback(async (newProjectId: string) => {
    if (!task || newProjectId === task.project_id) return;
    const proj = allProjects.find((p) => p.id === newProjectId);
    if (!proj) return;
    const firstCol = proj.board_columns?.sort((a, b) => a.position - b.position)[0];
    if (!firstCol) return;
    await updateTask({ project_id: newProjectId, board_column_id: firstCol.id } as TaskUpdatePayload);
  }, [task, allProjects, updateTask]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  if (!taskId) return null;

  const backdropClass =
    mode === 'fullscreen'
      ? 'fixed inset-0 z-50'
      : mode === 'modal'
        ? 'fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm'
        : 'fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm';

  const panelClass =
    mode === 'fullscreen'
      ? 'flex h-full w-full flex-col overflow-hidden bg-white pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)] dark:bg-gray-950'
      : mode === 'modal'
        ? 'flex w-full max-w-4xl max-h-[90dvh] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-gray-950'
        : 'flex h-full w-full max-w-2xl flex-col overflow-hidden bg-white shadow-2xl dark:bg-gray-950';

  const boardColumns: BoardColumn[] = currentProject?.board_columns?.sort((a, b) => a.position - b.position) || [];
  const dueDateFormatted = task?.due_date
    ? new Date(task.due_date + 'T00:00:00').toLocaleDateString('de-CH', { day: 'numeric', month: 'short', year: 'numeric' })
    : null;
  const isDueOverdue = task?.due_date ? new Date(task.due_date) < new Date(new Date().toISOString().split('T')[0]) : false;

  return (
    <div ref={backdropRef} className={backdropClass} onClick={(e) => { if (e.target === backdropRef.current) onClose(); }}>
      <div className={panelClass}>
        {/* ─── Header ─── */}
        <div className="flex items-center justify-between border-b border-gray-100 bg-gray-50/60 px-5 py-2.5 dark:border-gray-800 dark:bg-gray-900/40">
          <div className="flex items-center gap-3">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={task?.is_completed ?? false}
                onChange={() => task && updateTask({ is_completed: !task.is_completed })}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-gray-600"
              />
              <span className={`text-sm font-medium ${task?.is_completed ? 'text-green-600 dark:text-green-400' : 'text-gray-500 dark:text-gray-400'}`}>
                {task?.is_completed ? 'Erledigt' : 'Offen'}
              </span>
            </label>
            {currentProject && (
              <span className="rounded-md bg-white/80 px-2 py-0.5 text-[11px] font-medium text-gray-500 shadow-sm ring-1 ring-gray-200/60 dark:bg-gray-800 dark:text-gray-400 dark:ring-gray-700">
                {currentProject.name}
              </span>
            )}
          </div>
          <div className="flex items-center gap-0.5">
            {([['modal', 'Modal', ModalIcon], ['panel', 'Seitenpanel', PanelIcon], ['fullscreen', 'Vollbild', FullscreenIcon]] as const).map(([m, title, Icon]) => (
              <button key={m} onClick={() => persistMode(m as TaskDetailMode)} className={`rounded-md p-1.5 transition-colors ${mode === m ? 'bg-indigo-100 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400' : 'text-gray-400 hover:bg-gray-200/60 dark:hover:bg-gray-800'}`} title={title}>
                <Icon className="h-4 w-4" />
              </button>
            ))}
            <div className="mx-1 h-4 w-px bg-gray-200 dark:bg-gray-700" />
            <button onClick={onClose} className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-gray-200/60 dark:hover:bg-gray-800">
              <CloseIcon className="h-5 w-5" />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex flex-1 items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
          </div>
        ) : task ? (
          <div className="flex-1 overflow-y-auto">
            <div className="grid grid-cols-1 md:grid-cols-[1fr_280px]">
              {/* ═══════════ Linke Spalte: Inhalt ═══════════ */}
              <div className="space-y-6 p-6 md:border-r md:border-gray-100 md:dark:border-gray-800">
                {/* Titel */}
                {editingTitle ? (
                  <input
                    value={titleValue}
                    onChange={(e) => setTitleValue(e.target.value)}
                    onBlur={saveTitle}
                    onKeyDown={(e) => { if (e.key === 'Enter') saveTitle(); if (e.key === 'Escape') { setTitleValue(task.title); setEditingTitle(false); } }}
                    autoFocus
                    className="w-full rounded-lg border border-indigo-300 bg-transparent px-3 py-2 text-lg font-bold text-gray-900 outline-none focus:ring-2 focus:ring-indigo-400/40 dark:border-indigo-700 dark:text-white"
                  />
                ) : (
                  <h1 onClick={() => setEditingTitle(true)} className="cursor-pointer rounded-lg px-3 py-2 text-lg font-bold text-gray-900 transition-colors hover:bg-indigo-50/50 dark:text-white dark:hover:bg-gray-900">
                    {task.title}
                  </h1>
                )}

                {/* Beschreibung */}
                <section>
                  <SectionLabel icon={DescIcon} text="Beschreibung" />
                  {editingDesc ? (
                    <div>
                      <RichTextEditor
                        content={descValue}
                        onChange={setDescValue}
                        editable
                        minHeight="120px"
                      />
                      <div className="mt-2 flex gap-2">
                        <button onClick={saveDescription} className="rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-indigo-700">Speichern</button>
                        <button onClick={() => { setDescValue(task.description || ''); setEditingDesc(false); }} className="rounded-lg px-3 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800">Abbrechen</button>
                      </div>
                    </div>
                  ) : (
                    <div onClick={() => setEditingDesc(true)} className="min-h-[48px] cursor-pointer rounded-lg border border-transparent px-3 py-2.5 text-sm text-gray-700 transition-colors hover:border-gray-200 hover:bg-gray-50/60 dark:text-gray-300 dark:hover:border-gray-700 dark:hover:bg-gray-900/60">
                      {task.description
                        ? <div className="prose prose-sm max-w-none dark:prose-invert" dangerouslySetInnerHTML={{ __html: task.description }} />
                        : <span className="italic text-gray-400 dark:text-gray-600">Klicken um Beschreibung hinzuzufügen…</span>
                      }
                    </div>
                  )}
                </section>

                {/* Checkliste */}
                <section>
                  <SectionLabel icon={ChecklistIcon} text={`Checkliste${task.checklist_items.length > 0 ? ` (${task.checklist_items.filter((i) => i.is_checked).length}/${task.checklist_items.length})` : ''}`} />
                  {task.checklist_items.length > 0 && (
                    <>
                      <div className="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
                        <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all" style={{ width: `${(task.checklist_items.filter((i) => i.is_checked).length / task.checklist_items.length) * 100}%` }} />
                      </div>
                      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleChecklistDragEnd}>
                        <SortableContext items={task.checklist_items.sort((a, b) => a.position - b.position).map((i) => i.id)} strategy={verticalListSortingStrategy}>
                          {task.checklist_items.sort((a, b) => a.position - b.position).map((item) => (
                            <SortableChecklistItem
                              key={item.id} item={item}
                              isEditing={editingChecklistId === item.id} editText={editingChecklistText}
                              onToggle={() => toggleChecklistItem(item)}
                              onStartEdit={() => { setEditingChecklistId(item.id); setEditingChecklistText(item.text); }}
                              onEditChange={setEditingChecklistText}
                              onSaveEdit={() => updateChecklistText(item.id, editingChecklistText)}
                              onCancelEdit={() => setEditingChecklistId(null)}
                              onDelete={() => deleteChecklistItem(item.id)}
                            />
                          ))}
                        </SortableContext>
                      </DndContext>
                    </>
                  )}
                  <div className="mt-2 flex gap-2">
                    <input value={newChecklistText} onChange={(e) => setNewChecklistText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && newChecklistText.trim()) addChecklistItem(newChecklistText); }} placeholder="Neuer Eintrag…" className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-900 outline-none placeholder:text-gray-400 focus:border-indigo-300 dark:border-gray-700 dark:bg-gray-900 dark:text-white" />
                    <button onClick={() => addChecklistItem(newChecklistText)} disabled={!newChecklistText.trim()} className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-40">+</button>
                  </div>
                </section>

                {/* Dokumente */}
                <section>
                  <SectionLabel icon={PaperclipIcon} text={`Dokumente${attachments.length > 0 ? ` (${attachments.length})` : ''}`} />
                  <div
                    onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={(e) => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files); }}
                    className={`rounded-xl border-2 border-dashed p-3 transition-colors ${dragOver ? 'border-indigo-400 bg-indigo-50/50 dark:border-indigo-600 dark:bg-indigo-950/30' : 'border-gray-200 bg-gray-50/30 dark:border-gray-700 dark:bg-gray-900/20'}`}
                  >
                    {attachments.length > 0 && (
                      <div className="mb-2 space-y-1">
                        {attachments.map((att) => (
                          <div key={att.id} className="group flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-white dark:hover:bg-gray-800">
                            <PaperclipIcon className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                            <a href={att.filepath} target="_blank" rel="noopener noreferrer" className="flex-1 truncate text-indigo-600 hover:underline dark:text-indigo-400">{att.filename}</a>
                            <span className="shrink-0 text-[10px] text-gray-400">{formatFileSize(att.size)}</span>
                            <button onClick={() => deleteAttachment(att.id)} className="shrink-0 rounded p-0.5 text-gray-300 opacity-0 hover:text-red-500 group-hover:opacity-100 dark:text-gray-600" title="Löschen">
                              <TrashIcon className="h-3 w-3" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="flex items-center justify-center gap-2">
                      <input ref={fileInputRef} type="file" multiple className="hidden" onChange={(e) => { if (e.target.files?.length) uploadFiles(e.target.files); e.target.value = ''; }} />
                      <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 shadow-sm hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-400">
                        {uploading ? 'Wird hochgeladen…' : 'Datei auswählen'}
                      </button>
                      <span className="text-[10px] text-gray-400">oder per Drag & Drop</span>
                    </div>
                  </div>
                </section>

                {/* Agent-Aufträge */}
                {agentJobs.length > 0 && (
                  <section>
                    <SectionLabel icon={AgentSmallIcon} text="Agent-Aufträge" />
                    <div className="space-y-2">
                      {agentJobs.map((job) => (
                        <div key={job.id} className="rounded-xl border border-gray-100 bg-gray-50/40 p-3 dark:border-gray-800 dark:bg-gray-900/30">
                          <div className="flex items-center justify-between">
                            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                              job.status === 'completed' ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' :
                              job.status === 'running' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300' :
                              job.status === 'failed' ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' :
                              job.status === 'awaiting_approval' ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300' :
                              'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
                            }`}>{job.status}</span>
                            <span className="text-[10px] text-gray-400">{new Date(job.created_at).toLocaleString('de-CH')}</span>
                          </div>
                          {job.output && <div className="mt-2 max-h-36 overflow-y-auto whitespace-pre-wrap rounded-lg bg-white p-2 text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300">{job.output}</div>}
                          {job.error_message && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{job.error_message}</p>}
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {/* Aktivitäten */}
                <section>
                  <SectionLabel icon={ActivityIcon} text="Aktivitäten" />
                  <div className="mb-3 flex gap-2">
                    <input value={commentText} onChange={(e) => setCommentText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && commentText.trim()) submitComment(); }} placeholder="Kommentar hinzufügen…" className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-none placeholder:text-gray-400 focus:border-indigo-300 dark:border-gray-700 dark:bg-gray-900 dark:text-white" />
                    <button onClick={submitComment} disabled={!commentText.trim() || submittingComment} className="rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-40">Senden</button>
                  </div>
                  {activities.length > 0 ? (
                    <div className="space-y-3">
                      {activities.map((log) => (
                        <div key={log.id} className="flex gap-2.5 text-xs">
                          <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-gray-100 text-gray-400 dark:bg-gray-800">
                            {log.event_type === 'comment' ? <CommentDotIcon className="h-3 w-3" /> : <HistoryIcon className="h-3 w-3" />}
                          </div>
                          <div className="flex-1">
                            <div className="text-gray-700 dark:text-gray-300">
                              {log.event_type === 'comment' && log.details ? String(log.details.text ?? '') : formatActivityEvent(log.event_type, log.details)}
                            </div>
                            <div className="mt-0.5 text-[10px] text-gray-400 dark:text-gray-600">
                              {log.actor} · {new Date(log.created_at).toLocaleString('de-CH', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs italic text-gray-400 dark:text-gray-600">Noch keine Aktivitäten</p>
                  )}
                </section>
              </div>

              {/* ═══════════ Rechte Spalte: Attribute ═══════════ */}
              <div className="space-y-1 bg-gray-50/40 p-5 dark:bg-gray-900/20">
                {/* Agenda */}
                <AttrRow icon={AgendaIcon} label="Agenda">
                  <select value={task.pipeline_column_id || ''} onChange={(e) => updateTask({ pipeline_column_id: e.target.value || null })} className={ATTR_SELECT}>
                    <option value="">Nicht in Agenda</option>
                    {pipelineCols.map((col) => <option key={col.id} value={col.id}>{col.icon_emoji ? `${col.icon_emoji} ` : ''}{col.name}</option>)}
                  </select>
                </AttrRow>

                {/* Fällig am */}
                <AttrRow icon={CalendarIcon} label="Fällig am">
                  <input ref={dateInputRef} type="date" value={task.due_date || ''} onChange={(e) => updateTask({ due_date: e.target.value || null })} className="sr-only" tabIndex={-1} />
                  <button onClick={() => dateInputRef.current?.showPicker()} className={`flex w-full items-center justify-between rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${task.due_date ? (isDueOverdue ? 'border-red-200 bg-red-50/60 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400' : 'border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300') : 'border-dashed border-gray-300 bg-white text-gray-400 hover:border-gray-400 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-500'}`}>
                    <span>{dueDateFormatted || 'Datum wählen…'}</span>
                    <span className="flex items-center gap-1">
                      {task.due_date && <button onClick={(e) => { e.stopPropagation(); updateTask({ due_date: null }); }} className="rounded p-0.5 text-gray-400 hover:text-red-500"><CloseIcon className="h-3 w-3" /></button>}
                      <CalendarIcon className="h-3.5 w-3.5 text-gray-400" />
                    </span>
                  </button>
                </AttrRow>

                {/* Projekt */}
                <AttrRow icon={FolderIcon} label="Projekt">
                  <select value={task.project_id} onChange={(e) => handleProjectChange(e.target.value)} className={ATTR_SELECT}>
                    {allProjects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </AttrRow>

                {/* Board-Spalte */}
                <AttrRow icon={ColumnsIcon} label="Board-Spalte">
                  <select value={task.board_column_id} onChange={(e) => updateTask({ board_column_id: e.target.value })} className={ATTR_SELECT}>
                    {boardColumns.map((col) => <option key={col.id} value={col.id}>{col.icon_emoji ? `${col.icon_emoji} ` : ''}{col.name}</option>)}
                  </select>
                </AttrRow>

                {/* Zuständig */}
                <AttrRow icon={UserIcon} label="Zuständig">
                  <button
                    onClick={() => updateTask({ assignee: task.assignee === 'agent' ? 'me' : 'agent' })}
                    className={`flex w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors ${
                      task.assignee === 'agent'
                        ? 'border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-300'
                        : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300'
                    }`}
                  >
                    {task.assignee === 'agent' ? <><AgentSmallIcon className="h-3.5 w-3.5" /> AI Agent</> : <><UserIcon className="h-3.5 w-3.5" /> Ich</>}
                  </button>
                </AttrRow>

                {/* Tags */}
                <AttrRow icon={TagIcon} label="Tags">
                  <div className="flex flex-wrap gap-1.5">
                    {task.tags.map((tag) => (
                      <button key={tag.id} onClick={() => toggleTag(tag)} className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium shadow-sm transition-opacity hover:opacity-70" style={{ backgroundColor: tag.color + '20', color: tag.color, border: `1px solid ${tag.color}30` }} title="Tag entfernen">
                        {tag.name} <span className="text-[9px] opacity-60">×</span>
                      </button>
                    ))}
                    <div className="relative">
                      <button onClick={() => setShowTagPicker(!showTagPicker)} className="rounded-full border border-dashed border-gray-300 px-2 py-0.5 text-[11px] text-gray-400 hover:border-gray-400 hover:text-gray-600 dark:border-gray-600 dark:hover:border-gray-500">+ Tag</button>
                      {showTagPicker && (
                        <div className="absolute right-0 top-7 z-10 w-44 rounded-xl border border-gray-200 bg-white p-1.5 shadow-lg dark:border-gray-700 dark:bg-gray-900">
                          {allTags.filter((t) => !task.tags.some((tt) => tt.id === t.id)).map((tag) => (
                            <button key={tag.id} onClick={() => { toggleTag(tag); setShowTagPicker(false); }} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-gray-50 dark:hover:bg-gray-800">
                              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: tag.color }} />
                              {tag.name}
                            </button>
                          ))}
                          {allTags.filter((t) => !task.tags.some((tt) => tt.id === t.id)).length === 0 && (
                            <p className="px-2 py-1.5 text-xs text-gray-400">Keine weiteren Tags</p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </AttrRow>

                {/* Wiederholung */}
                <AttrRow icon={RepeatIcon} label="Wiederholung">
                  <RecurrenceSelector value={task.recurrence_rule} isInstance={!!task.template_id} onChange={(rule) => updateTask({ recurrence_rule: rule } as TaskUpdatePayload)} />
                </AttrRow>

                {task.recurrence_rule && !task.template_id && (
                  <>
                    <AttrRow icon={ClockIcon} label="Kalender-Dauer">
                      <select value={task.calendar_duration_minutes ?? ''} onChange={(e) => updateTask({ calendar_duration_minutes: e.target.value ? Number(e.target.value) : null } as TaskUpdatePayload)} className={ATTR_SELECT}>
                        <option value="">Kein Blocker</option>
                        <option value="15">15 Min</option>
                        <option value="30">30 Min</option>
                        <option value="60">1 Std</option>
                        <option value="90">1.5 Std</option>
                        <option value="120">2 Std</option>
                      </select>
                    </AttrRow>
                    {(task.calendar_duration_minutes ?? 0) > 0 && (
                      <AttrRow icon={ClockIcon} label="Bevorzugte Zeit">
                        <select value={task.calendar_preferred_time ?? 'morning_after_1030'} onChange={(e) => updateTask({ calendar_preferred_time: e.target.value } as TaskUpdatePayload)} className={ATTR_SELECT}>
                          <option value="morning_after_1030">Vormittag (ab 10:30)</option>
                          <option value="afternoon">Nachmittag</option>
                          <option value="any">Ganzer Tag</option>
                        </select>
                      </AttrRow>
                    )}
                  </>
                )}

                {/* Agent-Konfiguration */}
                {task.assignee === 'agent' && (
                  <div className="!mt-3 space-y-2 rounded-xl border border-violet-200/60 bg-violet-50/40 p-3 dark:border-violet-900/40 dark:bg-violet-950/20">
                    <h4 className="text-[11px] font-semibold uppercase tracking-wider text-violet-600 dark:text-violet-400">Agent-Konfiguration</h4>
                    <AttrRow icon={AgentSmallIcon} label="LLM-Modell">
                      <select value={task.llm_override || ''} onChange={(e) => updateTask({ llm_override: e.target.value || undefined } as TaskUpdatePayload)} className={ATTR_SELECT}>
                        <option value="">{defaultLocalModel ? `Standard (${defaultLocalModel.replace('ollama/', '')})` : 'Standard (lokal)'}</option>
                        {models && (
                          <>
                            <optgroup label="Lokal (Datenschutz)">
                              {models.local.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                            </optgroup>
                            <optgroup label="Cloud">
                              {models.cloud.map((m) => <option key={m.id} value={m.id} disabled={task.data_class === 'highly_confidential'}>{m.name}{task.data_class === 'highly_confidential' ? ' (gesperrt)' : ''}</option>)}
                            </optgroup>
                          </>
                        )}
                      </select>
                    </AttrRow>
                    <AttrRow icon={ShieldIcon} label="Autonomie">
                      <select value={task.autonomy_level} onChange={(e) => updateTask({ autonomy_level: e.target.value } as TaskUpdatePayload)} className={ATTR_SELECT}>
                        <option value="L0">L0 — Blockieren</option>
                        <option value="L1">L1 — Genehmigen</option>
                        <option value="L2">L2 — Benachrichtigen</option>
                        <option value="L3">L3 — Vollautonom</option>
                      </select>
                    </AttrRow>
                    <AttrRow icon={LockIcon} label="Datenklasse">
                      <div className="flex gap-1">
                        {(['internal', 'confidential', 'highly_confidential'] as const).map((dc) => (
                          <button key={dc} onClick={() => updateTask({ data_class: dc } as TaskUpdatePayload)} className={`flex-1 rounded-lg px-1.5 py-1 text-[10px] font-medium transition-colors ${
                            task.data_class === dc
                              ? dc === 'highly_confidential' ? 'bg-red-100 text-red-700 ring-1 ring-red-200 dark:bg-red-900/40 dark:text-red-300 dark:ring-red-800'
                                : dc === 'confidential' ? 'bg-amber-100 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-800'
                                : 'bg-green-100 text-green-700 ring-1 ring-green-200 dark:bg-green-900/40 dark:text-green-300 dark:ring-green-800'
                              : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'
                          }`}>
                            {{ internal: 'Intern', confidential: 'Vertraul.', highly_confidential: 'Streng v.' }[dc]}
                          </button>
                        ))}
                      </div>
                    </AttrRow>
                  </div>
                )}

                {/* Pipedrive CRM */}
                {(task.pipedrive_deal_id || task.pipedrive_person_id) && (
                  <div className="!mt-3 rounded-lg border border-green-200 bg-green-50/50 p-3 dark:border-green-900 dark:bg-green-950/30">
                    <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-green-700 dark:text-green-400">
                      <CrmLinkIcon className="h-3.5 w-3.5" />
                      Pipedrive
                    </div>
                    <div className="space-y-1 text-xs text-gray-600 dark:text-gray-400">
                      {task.pipedrive_deal_id && (
                        <div>
                          <span className="font-medium">Deal:</span>{' '}
                          <a
                            href={`https://innosmith.pipedrive.com/deal/${task.pipedrive_deal_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-green-600 hover:underline dark:text-green-400"
                          >
                            #{task.pipedrive_deal_id} →
                          </a>
                        </div>
                      )}
                      {task.pipedrive_person_id && (
                        <div>
                          <span className="font-medium">Kontakt:</span>{' '}
                          <a
                            href={`https://innosmith.pipedrive.com/person/${task.pipedrive_person_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-green-600 hover:underline dark:text-green-400"
                          >
                            #{task.pipedrive_person_id} →
                          </a>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Metadaten */}
                <div className="!mt-4 space-y-0.5 border-t border-gray-100 pt-3 text-[10px] text-gray-400 dark:border-gray-800 dark:text-gray-600">
                  <div>Erstellt: {new Date(task.created_at).toLocaleString('de-CH')}</div>
                  <div>Aktualisiert: {new Date(task.updated_at).toLocaleString('de-CH')}</div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center text-gray-500">Task nicht gefunden.</div>
        )}
      </div>
    </div>
  );
}

/* ═══════════ Sub-Komponenten ═══════════ */

const ATTR_SELECT = 'w-full cursor-pointer rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-700 outline-none transition-colors hover:border-gray-300 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-300 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:border-gray-600';

function SectionLabel({ icon: Icon, text }: { icon: React.FC<{ className?: string }>; text: string }) {
  return (
    <h3 className="mb-2.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
      <Icon className="h-3.5 w-3.5" /> {text}
    </h3>
  );
}

function AttrRow({ icon: Icon, label, children }: { icon: React.FC<{ className?: string }>; label: string; children: React.ReactNode }) {
  return (
    <div className="py-2">
      <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
        <Icon className="h-3 w-3" /> {label}
      </div>
      {children}
    </div>
  );
}

/* ── Sortable Checklist ── */

interface SortableChecklistItemProps {
  item: ChecklistItem; isEditing: boolean; editText: string;
  onToggle: () => void; onStartEdit: () => void; onEditChange: (v: string) => void;
  onSaveEdit: () => void; onCancelEdit: () => void; onDelete: () => void;
}

function SortableChecklistItem({ item, isEditing, editText, onToggle, onStartEdit, onEditChange, onSaveEdit, onCancelEdit, onDelete }: SortableChecklistItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.id });
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 };

  return (
    <div ref={setNodeRef} style={style} className="group flex items-center gap-2 rounded-lg px-1 py-1.5 transition-colors hover:bg-gray-50 dark:hover:bg-gray-900">
      <button {...attributes} {...listeners} className="shrink-0 cursor-grab touch-none rounded p-0.5 text-gray-300 opacity-0 transition-opacity group-hover:opacity-100 dark:text-gray-600" title="Verschieben">
        <GripIcon className="h-3.5 w-3.5" />
      </button>
      <input type="checkbox" checked={item.is_checked} onChange={onToggle} className="h-4 w-4 shrink-0 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-gray-600" />
      {isEditing ? (
        <input value={editText} onChange={(e) => onEditChange(e.target.value)} onBlur={onSaveEdit} onKeyDown={(e) => { if (e.key === 'Enter') onSaveEdit(); if (e.key === 'Escape') onCancelEdit(); }} autoFocus className="flex-1 rounded border border-indigo-300 bg-transparent px-2 py-0.5 text-sm text-gray-900 outline-none dark:text-white" />
      ) : (
        <span onClick={onStartEdit} className={`flex-1 cursor-pointer text-sm ${item.is_checked ? 'text-gray-400 line-through dark:text-gray-600' : 'text-gray-800 dark:text-gray-200'}`}>{item.text}</span>
      )}
      <button onClick={onDelete} className="shrink-0 rounded p-1 text-gray-300 opacity-0 transition-all hover:bg-red-50 hover:text-red-500 group-hover:opacity-100 dark:text-gray-600 dark:hover:bg-red-950 dark:hover:text-red-400" title="Löschen">
        <TrashIcon className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

/* ═══════════ Icons ═══════════ */

function CloseIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" /></svg>;
}
function TrashIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" /></svg>;
}
function GripIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 9h16.5m-16.5 6.75h16.5" /></svg>;
}
function PaperclipIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="m18.375 12.739-7.693 7.693a4.5 4.5 0 0 1-6.364-6.364l10.94-10.94A3 3 0 1 1 19.5 7.372L8.552 18.32m.009-.01-.01.01m5.699-9.941-7.81 7.81a1.5 1.5 0 0 0 2.112 2.13" /></svg>;
}
function DescIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25H12" /></svg>;
}
function ChecklistIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>;
}
function AgentSmallIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" /></svg>;
}
function UserIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" /></svg>;
}
function CalendarIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" /></svg>;
}
function FolderIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z" /></svg>;
}
function ColumnsIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9 4.5v15m6-15v15m-10.875 0h15.75c.621 0 1.125-.504 1.125-1.125V5.625c0-.621-.504-1.125-1.125-1.125H4.125C3.504 4.5 3 5.004 3 5.625v12.75c0 .621.504 1.125 1.125 1.125Z" /></svg>;
}
function TagIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z" /><path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6Z" /></svg>;
}
function AgendaIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25A2.25 2.25 0 0 1 13.5 18v-2.25Z" /></svg>;
}
function RepeatIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182M21.015 4.356v4.992" /></svg>;
}
function ClockIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>;
}
function ShieldIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" /></svg>;
}
function LockIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" /></svg>;
}
function ModalIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h12A2.25 2.25 0 0 1 20.25 6v12A2.25 2.25 0 0 1 18 20.25H6A2.25 2.25 0 0 1 3.75 18V6Z" /><path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9M7.5 12h9M7.5 15.75h5.25" /></svg>;
}
function PanelIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h12A2.25 2.25 0 0 1 20.25 6v12A2.25 2.25 0 0 1 18 20.25H6A2.25 2.25 0 0 1 3.75 18V6Z" /><path strokeLinecap="round" strokeLinejoin="round" d="M15 3.75v16.5" /></svg>;
}
function FullscreenIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9m11.25-5.25v4.5m0-4.5h-4.5m4.5 0L15 9m5.25 11.25v-4.5m0 4.5h-4.5m4.5 0L15 15m-11.25 5.25v-4.5m0 4.5h4.5m-4.5 0L9 15" /></svg>;
}
function ActivityIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>;
}
function CommentDotIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" /></svg>;
}
function HistoryIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182M21.015 4.356v4.992" /></svg>;
}
function CrmLinkIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18.75a60.07 60.07 0 0 1 15.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 0 1 3 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 0 0-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 0 1-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 0 0 3 15h-.75M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm3 0h.008v.008H18V10.5Zm-12 0h.008v.008H6V10.5Z" /></svg>;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatActivityEvent(eventType: string, details: Record<string, unknown> | null): string {
  const EVENT_LABELS: Record<string, string> = {
    created: 'Task erstellt', title_changed: 'Titel geändert', status_changed: 'Status geändert',
    column_changed: 'Spalte verschoben', assigned: 'Zuweisung geändert', due_date_changed: 'Fälligkeit geändert',
    completed: 'Als erledigt markiert', reopened: 'Wieder geöffnet',
  };
  let label = EVENT_LABELS[eventType] || eventType;
  if (details) {
    if (details.from && details.to) label += `: ${details.from} → ${details.to}`;
    else if (details.value) label += `: ${details.value}`;
  }
  return label;
}

/* ── Recurrence ── */

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
  const m: Record<string, string> = {
    '0 9 * * *': 'Täglich um 09:00', '0 9 * * 1-5': 'Werktags um 09:00',
    '0 7 * * MON': 'Jeden Montag um 07:00', '0 9 * * MON': 'Jeden Montag um 09:00',
    '0 8 1 * *': 'Monatlich am 1. um 08:00', '0 8 15 * *': 'Monatlich am 15. um 08:00',
    '0 8 20 * *': 'Monatlich am 20. um 08:00', '0 8 25 * *': 'Monatlich am 25. um 08:00',
  };
  return m[cron] || cron;
}

function RecurrenceSelector({ value, isInstance, onChange }: { value: string | null; isInstance: boolean; onChange: (rule: string | null) => void }) {
  const [showCustom, setShowCustom] = useState(false);
  const [customValue, setCustomValue] = useState('');

  if (isInstance) {
    return <div className="flex items-center gap-1.5 rounded-lg bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"><RepeatIcon className="h-3.5 w-3.5" />Instanz einer Vorlage</div>;
  }

  return (
    <div>
      <select
        value={showCustom ? '__custom__' : value && RECURRENCE_PRESETS.some((p) => p.value === value) ? value : value ? '__custom__' : ''}
        onChange={(e) => {
          const v = e.target.value;
          if (v === '__custom__') { setShowCustom(true); setCustomValue(value || ''); }
          else if (v === '') { setShowCustom(false); onChange(null); }
          else { setShowCustom(false); onChange(v); }
        }}
        className={ATTR_SELECT}
      >
        {RECURRENCE_PRESETS.map((p) => <option key={p.label} value={p.value ?? ''}>{p.label}</option>)}
        <option value="__custom__">Benutzerdefiniert (Cron)…</option>
      </select>
      {showCustom && (
        <div className="mt-1.5 flex gap-1.5">
          <input value={customValue} onChange={(e) => setCustomValue(e.target.value)} placeholder="z.B. 0 7 * * MON" className="flex-1 rounded-lg border border-gray-200 bg-transparent px-2 py-1 text-xs outline-none focus:border-indigo-300 dark:border-gray-700 dark:text-white" />
          <button onClick={() => { if (customValue.trim()) { onChange(customValue.trim()); setShowCustom(false); } }} className="rounded-lg bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-700">OK</button>
        </div>
      )}
      {value && <p className="mt-1 text-[10px] text-gray-400 dark:text-gray-500">{cronToHumanDE(value)}</p>}
    </div>
  );
}
