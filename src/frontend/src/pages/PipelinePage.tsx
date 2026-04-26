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
import { BackgroundPicker } from '../components/BackgroundPicker';
import type {
  PipelineData,
  TaskCard as TaskCardType,
  TaskCreatePayload,
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
  const [agendaBg, setAgendaBg] = useState<string | null>(null);
  const [bgPickerOpen, setBgPickerOpen] = useState(false);

  const projectColorMap = Object.fromEntries(
    projects.map((p) => [p.id, p.color]),
  );

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const fetchData = useCallback(async () => {
    try {
      const [pipelineData, projectData, settingsData] = await Promise.all([
        api.get<PipelineData>('/api/pipeline'),
        api.get<Project[]>('/api/projects'),
        api.get<{ agenda_background_url: string | null }>('/api/settings'),
      ]);
      setColumns(pipelineData.columns);
      setProjects(projectData);
      setAgendaBg(settingsData.agenda_background_url);
    } catch {
      /* handled by api client */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreateTask = useCallback(
    async (pipelineColumnId: string, title: string) => {
      if (projects.length === 0) return;
      const defaultProject = projects[0];
      const firstCol = defaultProject.board_columns?.[0];
      if (!firstCol) return;
      await api.post<TaskCardType>('/api/tasks', {
        title,
        project_id: defaultProject.id,
        board_column_id: firstCol.id,
        pipeline_column_id: pipelineColumnId,
      } satisfies TaskCreatePayload);
      fetchData();
    },
    [projects, fetchData],
  );

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

  const hasBg = !!agendaBg;
  const isGradient = agendaBg?.startsWith('gradient:') ?? false;
  const bgStyle = isGradient
    ? { background: agendaBg!.slice('gradient:'.length) }
    : hasBg
      ? { backgroundImage: `url(${agendaBg})`, backgroundSize: 'cover', backgroundPosition: 'center' }
      : undefined;

  const handleBgSelect = async (url: string | null) => {
    await api.patch('/api/settings', { agenda_background_url: url });
    setAgendaBg(url);
  };

  return (
    <div className="relative flex h-full flex-col" style={bgStyle}>
      {hasBg && !isGradient && <div className="absolute inset-0 bg-black/30 dark:bg-black/50" />}
      {isGradient && <div className="absolute inset-0 bg-black/10 dark:bg-black/30" />}

      <div className={`relative z-10 border-b px-6 py-4 ${hasBg ? 'border-white/10 bg-black/20 backdrop-blur-sm' : 'border-gray-200 dark:border-gray-800'}`}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className={`text-xl font-bold ${hasBg ? 'text-white' : 'text-gray-900 dark:text-white'}`}>
              Agenda
            </h1>
            <p className={`mt-0.5 text-sm ${hasBg ? 'text-white/70' : 'text-gray-500 dark:text-gray-400'}`}>
              Alle Aufgaben nach Zeithorizont organisiert
            </p>
          </div>
          <button
            onClick={() => setBgPickerOpen(true)}
            className={`rounded-lg p-2 transition-colors ${
              hasBg
                ? 'text-white/70 hover:bg-white/10 hover:text-white'
                : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300'
            }`}
            title="Hintergrundbild ändern"
          >
            <CameraIcon className="h-5 w-5" />
          </button>
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
          <div className="flex gap-4" style={{ minHeight: 'calc(100vh - 180px)' }}>
            {columns.map((col) => (
              <div key={col.id} className={hasBg ? 'rounded-xl bg-black/20 p-2 backdrop-blur-md' : ''}>
                <KanbanColumn
                  id={col.id}
                  title={col.name}
                  tasks={col.tasks}
                  projectColorMap={projectColorMap}
                  showProjectIndicator
                  onTaskClick={(task) => setSelectedTaskId(task.id)}
                  onCreateTask={handleCreateTask}
                />
              </div>
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

      <BackgroundPicker
        isOpen={bgPickerOpen}
        onClose={() => setBgPickerOpen(false)}
        currentUrl={agendaBg}
        onSelect={(url) => handleBgSelect(url)}
      />
    </div>
  );
}

function CameraIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Zm16.5-13.5h.008v.008h-.008V7.5Zm0 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" />
    </svg>
  );
}
