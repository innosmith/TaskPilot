import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  DndContext,
  DragOverlay,
  closestCorners,
  PointerSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
  type DragOverEvent,
} from '@dnd-kit/core';
import { arrayMove } from '@dnd-kit/sortable';
import { api } from '../api/client';
import { KanbanColumn } from '../components/KanbanColumn';
import { TaskCard } from '../components/TaskCard';
import { TaskDetailDialog } from '../components/TaskDetailDialog';
import type { BoardData, TaskCard as TaskCardType } from '../types';

export function ProjectBoardPage() {
  const { id } = useParams<{ id: string }>();
  const [board, setBoard] = useState<BoardData | null>(null);
  const [activeTask, setActiveTask] = useState<TaskCardType | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const fetchBoard = useCallback(async () => {
    if (!id) return;
    try {
      const data = await api.get<BoardData>(`/api/projects/${id}/board`);
      setBoard(data);
    } catch {
      /* handled by api client */
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    fetchBoard();
  }, [fetchBoard]);

  const findColumnByTaskId = (taskId: string) =>
    board?.columns.find((col) => col.tasks.some((t) => t.id === taskId));

  const handleDragStart = (event: DragStartEvent) => {
    const taskId = event.active.id as string;
    if (!board) return;
    for (const col of board.columns) {
      const task = col.tasks.find((t) => t.id === taskId);
      if (task) {
        setActiveTask(task);
        break;
      }
    }
  };

  const handleDragOver = (event: DragOverEvent) => {
    const { active, over } = event;
    if (!over || !board) return;

    const activeId = active.id as string;
    const overId = over.id as string;

    const sourceCol = findColumnByTaskId(activeId);
    const overCol =
      board.columns.find((col) => col.id === overId) ||
      findColumnByTaskId(overId);

    if (!sourceCol || !overCol || sourceCol.id === overCol.id) return;

    setBoard((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        columns: prev.columns.map((col) => {
          if (col.id === sourceCol.id) {
            return {
              ...col,
              tasks: col.tasks.filter((t) => t.id !== activeId),
            };
          }
          if (col.id === overCol.id) {
            const task = sourceCol.tasks.find((t) => t.id === activeId);
            if (!task) return col;
            const overIndex = col.tasks.findIndex((t) => t.id === overId);
            const newTasks = [...col.tasks];
            if (overIndex >= 0) {
              newTasks.splice(overIndex, 0, task);
            } else {
              newTasks.push(task);
            }
            return { ...col, tasks: newTasks };
          }
          return col;
        }),
      };
    });
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveTask(null);

    if (!over || !board) return;

    const activeId = active.id as string;
    const overId = over.id as string;

    if (activeId !== overId) {
      const col = findColumnByTaskId(activeId);
      if (col) {
        const oldIndex = col.tasks.findIndex((t) => t.id === activeId);
        const newIndex = col.tasks.findIndex((t) => t.id === overId);
        if (oldIndex !== -1 && newIndex !== -1) {
          setBoard((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              columns: prev.columns.map((c) =>
                c.id === col.id
                  ? { ...c, tasks: arrayMove(c.tasks, oldIndex, newIndex) }
                  : c,
              ),
            };
          });
        }
      }
    }

    const targetCol = findColumnByTaskId(activeId);
    if (!targetCol) return;
    const newPosition = targetCol.tasks.findIndex((t) => t.id === activeId);

    try {
      await api.patch(`/api/tasks/${activeId}`, {
        board_column_id: targetCol.id,
        board_position: newPosition,
      });
    } catch {
      fetchBoard();
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-3 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  if (!board) {
    return (
      <div className="flex h-full items-center justify-center text-gray-500">
        Projekt nicht gefunden.
      </div>
    );
  }

  const hasBg = !!board.project.background_url;

  return (
    <div
      className="relative flex h-full flex-col"
      style={
        hasBg
          ? {
              backgroundImage: `url(${board.project.background_url})`,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
            }
          : undefined
      }
    >
      {hasBg && (
        <div className="absolute inset-0 bg-black/30 dark:bg-black/50" />
      )}

      <div
        className={`relative z-10 border-b px-6 py-4 ${
          hasBg
            ? 'border-white/10 bg-black/20 text-white backdrop-blur-sm'
            : 'border-gray-200 dark:border-gray-800'
        }`}
      >
        <div className="flex items-center gap-3">
          <span
            className="h-4 w-4 rounded-full"
            style={{ backgroundColor: board.project.color }}
          />
          <h1
            className={`text-xl font-bold ${
              hasBg ? 'text-white' : 'text-gray-900 dark:text-white'
            }`}
          >
            {board.project.name}
          </h1>
        </div>
      </div>

      <div className="relative z-10 flex-1 overflow-x-auto p-6">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
        >
          <div
            className="flex gap-4"
            style={{ minHeight: 'calc(100vh - 180px)' }}
          >
            {board.columns.map((col) => (
              <div
                key={col.id}
                className={
                  hasBg
                    ? 'rounded-xl bg-black/20 p-2 backdrop-blur-md'
                    : ''
                }
              >
                <KanbanColumn
                  id={col.id}
                  title={col.name}
                  tasks={col.tasks}
                  onTaskClick={(task) => setSelectedTaskId(task.id)}
                />
              </div>
            ))}
          </div>

          <DragOverlay>
            {activeTask && (
              <div className="drag-overlay">
                <TaskCard task={activeTask} onClick={() => {}} />
              </div>
            )}
          </DragOverlay>
        </DndContext>
      </div>

      <TaskDetailDialog
        taskId={selectedTaskId}
        onClose={() => setSelectedTaskId(null)}
        onUpdated={fetchBoard}
      />
    </div>
  );
}
