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
}

export function KanbanColumn({
  id,
  title,
  tasks,
  projectColorMap,
  showProjectIndicator = false,
  onTaskClick,
}: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id });

  return (
    <div className="flex w-72 shrink-0 flex-col">
      <div className="mb-3 flex items-center justify-between px-1">
        <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400">
          {title}
        </h3>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400">
          {tasks.length}
        </span>
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
