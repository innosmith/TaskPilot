import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { marked } from 'marked';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { api } from '../../api/client';
import type { TaskDetail, ChecklistItem, TaskUpdatePayload } from '../../types';
import { RichTextEditor } from '../RichTextEditor';
import { SectionLabel, DescIcon, ChecklistIcon, GripIcon, TrashIcon } from './shared';

interface TaskDetailContentProps {
  task: TaskDetail;
  taskId: string;
  onUpdated: () => void;
  updateTask: (payload: TaskUpdatePayload) => Promise<void>;
  refreshTask: () => Promise<void>;
}

interface SortableChecklistItemProps {
  item: ChecklistItem;
  isEditing: boolean;
  editText: string;
  onToggle: () => void;
  onStartEdit: () => void;
  onEditChange: (v: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onDelete: () => void;
}

function SortableChecklistItem({
  item,
  isEditing,
  editText,
  onToggle,
  onStartEdit,
  onEditChange,
  onSaveEdit,
  onCancelEdit,
  onDelete,
}: SortableChecklistItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: item.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const editRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing && editRef.current) {
      editRef.current.focus();
      editRef.current.select();
    }
  }, [isEditing]);

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="group flex items-center gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50"
    >
      <button
        type="button"
        className="cursor-grab touch-none text-gray-300 hover:text-gray-500 dark:text-gray-600 dark:hover:text-gray-400"
        {...attributes}
        {...listeners}
      >
        <GripIcon className="h-4 w-4" />
      </button>

      <label className="flex cursor-pointer items-center">
        <input
          type="checkbox"
          checked={item.is_checked}
          onChange={onToggle}
          className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700"
        />
      </label>

      {isEditing ? (
        <input
          ref={editRef}
          type="text"
          value={editText}
          onChange={(e) => onEditChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onSaveEdit();
            if (e.key === 'Escape') onCancelEdit();
          }}
          onBlur={onSaveEdit}
          className="flex-1 rounded border border-indigo-300 bg-white px-2 py-0.5 text-sm text-gray-800 outline-none focus:ring-1 focus:ring-indigo-400 dark:border-indigo-600 dark:bg-gray-800 dark:text-gray-200"
        />
      ) : (
        <span
          onClick={onStartEdit}
          className={`flex-1 cursor-text text-sm ${
            item.is_checked
              ? 'text-gray-400 line-through dark:text-gray-500'
              : 'text-gray-700 dark:text-gray-300'
          }`}
        >
          {item.text}
        </span>
      )}

      <button
        type="button"
        onClick={onDelete}
        className="shrink-0 text-gray-300 opacity-0 transition-opacity hover:text-red-500 group-hover:opacity-100 dark:text-gray-600 dark:hover:text-red-400"
      >
        <TrashIcon className="h-4 w-4" />
      </button>
    </div>
  );
}

export default function TaskDetailContent({
  task,
  taskId,
  onUpdated,
  updateTask,
  refreshTask,
}: TaskDetailContentProps) {
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleValue, setTitleValue] = useState(task.title);
  const titleRef = useRef<HTMLInputElement>(null);

  const [editingDesc, setEditingDesc] = useState(false);
  const [descValue, setDescValue] = useState(task.description ?? '');
  const descDirtyRef = useRef(false);

  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [editItemText, setEditItemText] = useState('');
  const [newChecklistText, setNewChecklistText] = useState('');

  useEffect(() => {
    setTitleValue(task.title);
  }, [task.title]);

  useEffect(() => {
    setDescValue(task.description ?? '');
  }, [task.description]);

  useEffect(() => {
    if (editingTitle && titleRef.current) {
      titleRef.current.focus();
      titleRef.current.select();
    }
  }, [editingTitle]);

  const saveTitle = useCallback(async () => {
    const trimmed = titleValue.trim();
    if (trimmed && trimmed !== task.title) {
      await updateTask({ title: trimmed });
    } else {
      setTitleValue(task.title);
    }
    setEditingTitle(false);
  }, [titleValue, task.title, updateTask]);

  const saveDescriptionAndClose = useCallback(async () => {
    if (descDirtyRef.current) {
      await updateTask({ description: descValue });
      descDirtyRef.current = false;
    }
    setEditingDesc(false);
  }, [descValue, updateTask]);

  const descriptionHtml = useMemo(() => {
    if (!task.description) return '';
    if (/<[a-z][\s\S]*>/i.test(task.description)) return task.description;
    return marked.parse(task.description, { breaks: true }) as string;
  }, [task.description]);

  const checklist = task.checklist_items ?? [];
  const doneCount = checklist.filter((i) => i.is_checked).length;
  const totalCount = checklist.length;
  const progressPct = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

  const toggleChecklistItem = useCallback(
    async (item: ChecklistItem) => {
      await api.patch(`/api/tasks/${taskId}/checklist/${item.id}`, {
        is_checked: !item.is_checked,
      });
      await refreshTask();
      onUpdated();
    },
    [taskId, refreshTask, onUpdated],
  );

  const startEditItem = useCallback((item: ChecklistItem) => {
    setEditingItemId(item.id);
    setEditItemText(item.text);
  }, []);

  const saveEditItem = useCallback(async () => {
    if (!editingItemId) return;
    const trimmed = editItemText.trim();
    if (trimmed) {
      await api.patch(`/api/tasks/${taskId}/checklist/${editingItemId}`, {
        text: trimmed,
      });
      await refreshTask();
      onUpdated();
    }
    setEditingItemId(null);
    setEditItemText('');
  }, [editingItemId, editItemText, taskId, refreshTask, onUpdated]);

  const cancelEditItem = useCallback(() => {
    setEditingItemId(null);
    setEditItemText('');
  }, []);

  const deleteChecklistItem = useCallback(
    async (itemId: string) => {
      await api.delete(`/api/tasks/${taskId}/checklist/${itemId}`);
      await refreshTask();
      onUpdated();
    },
    [taskId, refreshTask, onUpdated],
  );

  const addChecklistItem = useCallback(async () => {
    const trimmed = newChecklistText.trim();
    if (!trimmed) return;
    await api.post(`/api/tasks/${taskId}/checklist`, { text: trimmed });
    setNewChecklistText('');
    await refreshTask();
    onUpdated();
  }, [newChecklistText, taskId, refreshTask, onUpdated]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;

      const oldIndex = checklist.findIndex((i) => i.id === active.id);
      const newIndex = checklist.findIndex((i) => i.id === over.id);
      if (oldIndex === -1 || newIndex === -1) return;

      await api.patch(`/api/tasks/${taskId}/checklist/${active.id}`, {
        position: checklist[newIndex].position,
      });
      await refreshTask();
      onUpdated();
    },
    [checklist, taskId, refreshTask, onUpdated],
  );

  return (
    <div className="space-y-6">
      {/* Titel */}
      <div>
        {editingTitle ? (
          <input
            ref={titleRef}
            type="text"
            value={titleValue}
            onChange={(e) => setTitleValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') saveTitle();
              if (e.key === 'Escape') {
                setTitleValue(task.title);
                setEditingTitle(false);
              }
            }}
            onBlur={saveTitle}
            className="w-full rounded-lg border border-indigo-300 bg-white px-3 py-1.5 text-lg font-bold text-gray-900 outline-none focus:ring-2 focus:ring-indigo-400 dark:border-indigo-600 dark:bg-gray-800 dark:text-white"
          />
        ) : (
          <h2
            onClick={() => setEditingTitle(true)}
            className="cursor-text rounded-lg px-3 py-1.5 text-lg font-bold text-gray-900 transition-colors hover:bg-gray-50 dark:text-white dark:hover:bg-gray-800/50"
          >
            {task.title}
          </h2>
        )}
      </div>

      {/* Beschreibung */}
      <div>
        <SectionLabel icon={DescIcon} text="Beschreibung" />
        {editingDesc ? (
          <div
            onBlur={(e) => {
              if (e.currentTarget.contains(e.relatedTarget as Node)) return;
              saveDescriptionAndClose();
            }}
          >
            <RichTextEditor
              content={descValue}
              onChange={(html) => { setDescValue(html); descDirtyRef.current = true; }}
              editable
              placeholder="Beschreibung eingeben…"
              minHeight="80px"
            />
          </div>
        ) : (
          <div
            onClick={() => setEditingDesc(true)}
            className="cursor-text rounded-lg transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/30"
          >
            {task.description ? (
              <div className="prose prose-sm max-w-none text-gray-700 dark:prose-invert dark:text-gray-300">
                <RichTextEditor
                  content={descriptionHtml}
                  editable={false}
                  minHeight="40px"
                />
              </div>
            ) : (
              <p className="rounded-lg px-3 py-3 text-sm text-gray-400 dark:text-gray-500">
                Beschreibung eingeben…
              </p>
            )}
          </div>
        )}
      </div>

      {/* Checkliste */}
      <div>
        <SectionLabel
          icon={ChecklistIcon}
          text="Checkliste"
          action={totalCount > 0 ? (
            <span className="text-[10px] font-normal text-gray-400 dark:text-gray-500">
              {doneCount}/{totalCount}
            </span>
          ) : undefined}
        />

        {totalCount > 0 && (
          <div className="mb-3">
            <div className="mb-1 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
              <span>
                {doneCount} / {totalCount} erledigt
              </span>
              <span>{progressPct}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
        )}

        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={checklist.map((i) => i.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-0.5">
              {checklist.map((item) => (
                <SortableChecklistItem
                  key={item.id}
                  item={item}
                  isEditing={editingItemId === item.id}
                  editText={editItemText}
                  onToggle={() => toggleChecklistItem(item)}
                  onStartEdit={() => startEditItem(item)}
                  onEditChange={setEditItemText}
                  onSaveEdit={saveEditItem}
                  onCancelEdit={cancelEditItem}
                  onDelete={() => deleteChecklistItem(item.id)}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>

        <div className="mt-2 flex gap-2">
          <input
            type="text"
            value={newChecklistText}
            onChange={(e) => setNewChecklistText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') addChecklistItem();
            }}
            placeholder="Neuer Eintrag…"
            className="flex-1 rounded-lg border border-gray-200 bg-transparent px-3 py-1.5 text-sm text-gray-700 outline-none placeholder:text-gray-400 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-300 dark:border-gray-700 dark:text-gray-300 dark:placeholder:text-gray-500 dark:focus:border-indigo-600"
          />
          <button
            type="button"
            onClick={addChecklistItem}
            disabled={!newChecklistText.trim()}
            className="shrink-0 rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Hinzufügen
          </button>
        </div>
      </div>
    </div>
  );
}
