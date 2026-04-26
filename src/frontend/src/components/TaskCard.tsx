import { useState } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { TaskCard as TaskCardType } from '../types';

interface TaskCardProps {
  task: TaskCardType;
  projectColor?: string;
  showProjectIndicator?: boolean;
  hasBg?: boolean;
  userAvatarUrl?: string | null;
  onClick: (task: TaskCardType) => void;
  onArchive?: (taskId: string) => Promise<void>;
}

export function TaskCard({
  task,
  projectColor,
  showProjectIndicator = false,
  hasBg = false,
  userAvatarUrl,
  onClick,
  onArchive,
}: TaskCardProps) {
  const [fading, setFading] = useState(false);

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: task.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const hasChecklist = task.checklist_total > 0;
  const isOverdue =
    task.due_date && new Date(task.due_date) < new Date() && !task.is_completed;

  const handleArchive = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!onArchive) return;
    setFading(true);
    await new Promise((r) => setTimeout(r, 250));
    await onArchive(task.id);
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={() => onClick(task)}
      className={`group relative cursor-pointer rounded-xl border p-3 shadow-sm transition-all hover:shadow-md ${
        fading ? 'scale-95 opacity-0' : ''
      } ${
        isOverdue
          ? 'border-amber-200 bg-amber-50/80 dark:border-amber-900/40 dark:bg-amber-950/20'
          : hasBg
            ? 'border-white/10 bg-white/75 backdrop-blur-sm dark:bg-gray-900/75'
            : 'border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900'
      } ${isDragging ? 'z-50 rotate-2 scale-105 opacity-50 shadow-xl' : ''} ${
        task.is_completed ? 'opacity-60' : ''
      }`}
    >
      {onArchive && !task.is_completed && (
        <button
          onClick={handleArchive}
          className="absolute -right-1 -top-1 flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500 text-white opacity-0 shadow-sm transition-all hover:bg-emerald-600 group-hover:opacity-100"
          title="Archivieren"
        >
          <CheckIcon className="h-3.5 w-3.5" />
        </button>
      )}

      {showProjectIndicator && projectColor && (
        <div
          className="mb-2 h-1 w-8 rounded-full"
          style={{ backgroundColor: projectColor }}
        />
      )}

      <p
        className={`text-sm font-medium text-gray-900 dark:text-gray-100 ${
          task.is_completed ? 'line-through' : ''
        }`}
      >
        {task.title}
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {task.tags.map((tag) => (
          <span
            key={tag.id}
            className="inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium"
            style={{
              backgroundColor: tag.color + '20',
              color: tag.color,
            }}
          >
            {tag.name}
          </span>
        ))}
      </div>

      <div className="mt-2 flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
        {hasChecklist && (
          <span className="flex items-center gap-1">
            <ChecklistIcon className="h-3.5 w-3.5" />
            {task.checklist_done}/{task.checklist_total}
          </span>
        )}
        {task.due_date && (
          <span
            className={`flex items-center gap-1 ${
              isOverdue ? 'font-medium text-red-500' : ''
            }`}
          >
            <CalendarIcon className="h-3.5 w-3.5" />
            {formatDate(task.due_date)}
          </span>
        )}
        {task.is_pinned && (
          <span className="text-amber-500">
            <PinIcon className="h-3.5 w-3.5" />
          </span>
        )}
        <span className="ml-auto">
          {task.assignee === 'agent' ? (
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-violet-100 text-violet-600 dark:bg-violet-900/40 dark:text-violet-300">
              <AgentBadgeIcon className="h-3 w-3" />
            </span>
          ) : userAvatarUrl ? (
            <img
              src={userAvatarUrl}
              alt=""
              className="h-5 w-5 rounded-full object-cover"
            />
          ) : (
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-100 text-[9px] font-bold text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-300">
              Ich
            </span>
          )}
        </span>
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

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
    </svg>
  );
}

function ChecklistIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
    </svg>
  );
}

function CalendarIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
    </svg>
  );
}

function PinIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="currentColor" viewBox="0 0 24 24">
      <path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2Z" />
    </svg>
  );
}

function AgentBadgeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z" />
    </svg>
  );
}
