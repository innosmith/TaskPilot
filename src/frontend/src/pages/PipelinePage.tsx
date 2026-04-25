import { useState, useEffect, useCallback } from 'react';
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
import type {
  PipelineData,
  TaskCard as TaskCardType,
  Project,
} from '../types';

export function PipelinePage() {
  const [columns, setColumns] = useState<
    Array<{ id: string; name: string; tasks: TaskCardType[] }>
  >([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeTask, setActiveTask] = useState<TaskCardType | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const projectColorMap = Object.fromEntries(
    projects.map((p) => [p.id, p.color]),
  );

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const fetchData = useCallback(async () => {
    try {
      const [pipelineData, projectData] = await Promise.all([
        api.get<PipelineData>('/api/pipeline'),
        api.get<Project[]>('/api/projects'),
      ]);
      setColumns(pipelineData.columns);
      setProjects(projectData);
    } catch {
      /* handled by api client */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const findColumnByTaskId = (taskId: string) =>
    columns.find((col) => col.tasks.some((t) => t.id === taskId));

  const handleDragStart = (event: DragStartEvent) => {
    const taskId = event.active.id as string;
    for (const col of columns) {
      const task = col.tasks.find((t) => t.id === taskId);
      if (task) {
        setActiveTask(task);
        break;
      }
    }
  };

  const handleDragOver = (event: DragOverEvent) => {
    const { active, over } = event;
    if (!over) return;

    const activeId = active.id as string;
    const overId = over.id as string;

    const sourceCol = findColumnByTaskId(activeId);
    const overCol =
      columns.find((col) => col.id === overId) ||
      findColumnByTaskId(overId);

    if (!sourceCol || !overCol || sourceCol.id === overCol.id) return;

    setColumns((prev) =>
      prev.map((col) => {
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
    );
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveTask(null);

    if (!over) return;

    const activeId = active.id as string;
    const overId = over.id as string;

    const sourceCol = findColumnByTaskId(activeId);
    if (!sourceCol) return;

    if (activeId !== overId) {
      const col = findColumnByTaskId(activeId);
      if (col) {
        const oldIndex = col.tasks.findIndex((t) => t.id === activeId);
        const newIndex = col.tasks.findIndex((t) => t.id === overId);
        if (oldIndex !== -1 && newIndex !== -1) {
          setColumns((prev) =>
            prev.map((c) =>
              c.id === col.id
                ? { ...c, tasks: arrayMove(c.tasks, oldIndex, newIndex) }
                : c,
            ),
          );
        }
      }
    }

    const targetCol = findColumnByTaskId(activeId);
    if (!targetCol) return;
    const newPosition = targetCol.tasks.findIndex((t) => t.id === activeId);

    try {
      await api.patch(`/api/tasks/${activeId}`, {
        pipeline_column_id: targetCol.id,
        pipeline_position: newPosition,
      });
    } catch {
      fetchData();
    }
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
      <div className="border-b border-gray-200 px-6 py-4 dark:border-gray-800">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">
          Agenda
        </h1>
        <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
          Alle Aufgaben nach Zeithorizont organisiert
        </p>
      </div>

      <div className="flex-1 overflow-x-auto p-6">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
        >
          <div className="flex gap-4" style={{ minHeight: 'calc(100vh - 180px)' }}>
            {columns.map((col) => (
              <KanbanColumn
                key={col.id}
                id={col.id}
                title={col.name}
                tasks={col.tasks}
                projectColorMap={projectColorMap}
                showProjectIndicator
                onTaskClick={(task) => setSelectedTaskId(task.id)}
              />
            ))}
          </div>

          <DragOverlay>
            {activeTask && (
              <div className="drag-overlay">
                <TaskCard
                  task={activeTask}
                  projectColor={projectColorMap[activeTask.project_id]}
                  showProjectIndicator
                  onClick={() => {}}
                />
              </div>
            )}
          </DragOverlay>
        </DndContext>
      </div>

      <TaskDetailDialog
        taskId={selectedTaskId}
        onClose={() => setSelectedTaskId(null)}
        onUpdated={fetchData}
      />
    </div>
  );
}
