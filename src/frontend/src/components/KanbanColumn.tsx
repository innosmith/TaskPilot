import { useState, type KeyboardEvent } from 'react';
import { useDroppable } from '@dnd-kit/core';
import {
  SortableContext,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { TaskCard } from './TaskCard';
import type { TaskCard as TaskCardType } from '../types';

interface KanbanColumnProps {
  id: string;
  title: string;
  tasks: TaskCardType[];
  projectColorMap?: Record<string, string>;
  showProjectIndicator?: boolean;
  onTaskClick: (task: TaskCardType) => void;
  onCreateTask?: (columnId: string, title: string) => Promise<void>;
}

export function KanbanColumn({
  id,
  title,
  tasks,
  projectColorMap,
  showProjectIndicator = false,
  onTaskClick,
  onCreateTask,
}: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id });
  const [adding, setAdding] = useState(false);
  const [newTitle, setNewTitle] = useState('');

  const handleSubmit = async () => {
    const trimmed = newTitle.trim();
    if (!trimmed || !onCreateTask) return;
    await onCreateTask(id, trimmed);
    setNewTitle('');
    setAdding(false);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSubmit();
    if (e.key === 'Escape') {
      setNewTitle('');
      setAdding(false);
    }
  };

  return (
    <div className="flex w-72 shrink-0 flex-col">
      <div className="mb-3 flex items-center justify-between px-1">
        <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400">
          {title}
        </h3>
        <div className="flex items-center gap-1.5">
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400">
            {tasks.length}
          </span>
          {onCreateTask && (
            <button
              onClick={() => setAdding(true)}
              className="rounded-lg p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
              title="Neue Aufgabe"
            >
              <PlusIcon className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      <div
        ref={setNodeRef}
        className={`flex flex-1 flex-col gap-2 rounded-xl border-2 border-dashed p-2 transition-colors ${
          isOver
            ? 'border-indigo-400 bg-indigo-50/50 dark:border-indigo-500 dark:bg-indigo-950/30'
            : 'border-transparent'
        }`}
        style={{ minHeight: 100 }}
      >
        {adding && (
          <div className="rounded-xl border border-indigo-300 bg-white p-2 shadow-sm dark:border-indigo-700 dark:bg-gray-900">
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={handleKeyDown}
              onBlur={() => {
                if (!newTitle.trim()) setAdding(false);
              }}
              autoFocus
              placeholder="Titel eingeben..."
              className="w-full rounded bg-transparent px-1 py-0.5 text-sm text-gray-900 outline-none placeholder:text-gray-400 dark:text-white dark:placeholder:text-gray-600"
            />
          </div>
        )}

        <SortableContext
          items={tasks.map((t) => t.id)}
          strategy={verticalListSortingStrategy}
        >
          {tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              projectColor={projectColorMap?.[task.project_id]}
              showProjectIndicator={showProjectIndicator}
              onClick={onTaskClick}
            />
          ))}
        </SortableContext>
      </div>
    </div>
  );
}

function PlusIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
    </svg>
  );
}
